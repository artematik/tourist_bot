import re
import asyncio
import logging
import time
import datetime
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from handlers.start import cmd_start, cmd_help
from states import UserState
from services.geocoder import Geocoder
from services.ai_service import ai_service
from services.route_formatter import RouteFormatter

router = Router()
logger = logging.getLogger(__name__)

# === КЛАВИАТУРЫ ===
def _time_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="1"), KeyboardButton(text="2")],
                  [KeyboardButton(text="3"), KeyboardButton(text="4")]],
        resize_keyboard=True
    )

def _transport_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚶 Пешком"), KeyboardButton(text="🚗 Авто")],
            [KeyboardButton(text="🚲 Велосипед/самокат"), KeyboardButton(text="🚌 Общественный транспорт")],
        ],
        resize_keyboard=True
    )

def _location_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геопозицию", request_location=True)],
        ],
        resize_keyboard=True
    )

def _finish_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔁 Сгенерировать ещё")],
            [KeyboardButton(text="🔄 Сбросить настройки"), KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True
    )

# === СЕРВИСНЫЕ КНОПКИ ===
@router.message(F.text.in_({"🔄 Сбросить настройки", "/start", "start"}))
async def reset_questionnaire(message: Message, state: FSMContext):
    await state.clear()
    await cmd_start(message, state)

@router.message(F.text.in_({"ℹ️ Помощь", "/help", "help"}))
async def show_help(message: Message, state: FSMContext):
    await cmd_help(message, state)

# === ПОВТОРНАЯ ГЕНЕРАЦИЯ ===
@router.message(F.text == "🔁 Сгенерировать ещё")
async def regenerate_route(message: Message, state: FSMContext):
    data = await state.get_data()
    interests = data.get("interests")
    time_hours = data.get("time_hours", 2.0)
    transport = data.get("transport", "walk")
    start_time = data.get("start_time")

    lat = data.get("data_last_lat") or data.get("latitude")
    lon = data.get("data_last_lon") or data.get("longitude")
    start_label = data.get("data_last_loc") or data.get("location_text")

    if not (interests and lat is not None and lon is not None):
        await message.answer("Не удалось восстановить данные маршрута. Начни заново — /start")
        return

    import time as _t
    diversity_seed = int(_t.time() * 1000) % 2_000_000_000

    await message.answer(
        f"🔁 Генерирую новый маршрут по твоим интересам...\n"
        f"📍 Старт: {start_label or 'текущая точка'}\n"
        f"⏱ Время прогулки: {time_hours} ч\n"
        f"🚶‍♂️ Транспорт: {transport}"
    )

    try:
        route_data = await asyncio.wait_for(
            ai_service.generate_route(
                lat=lat,
                lon=lon,
                interests=interests,
                time_hours=time_hours,
                transport=transport,
                diversity_seed=diversity_seed,
                start_time=datetime.datetime.fromisoformat(start_time) if start_time else None
            ),
            timeout=60,
        )
        route_msg = RouteFormatter.format_route(route_data, interests, time_hours)
        await message.answer(route_msg, parse_mode="Markdown", disable_web_page_preview=True)
    except asyncio.TimeoutError:
        await message.answer("Сервис точек задерживается. Попробуйте ещё раз через минуту.")
    except Exception as e:
        logger.exception("💥 Ошибка при повторной генерации маршрута")
        await message.answer(f"Не удалось сгенерировать маршрут: {e}")

# === АНКЕТА ===
def _normalize_transport(txt: str) -> str:
    t = (txt or "").lower()
    if "авто" in t or "маш" in t:
        return "car"
    if "вел" in t or "самокат" in t:
        return "bike"
    if "обще" in t or "автобус" in t or "метро" in t:
        return "transit"
    return "walk"

# --- Проверка валидности интересов ---
def _valid_interests(text: str) -> bool:
    if not text:
        return False
    text = text.strip().lower()
    # слишком короткая строка
    if len(text) < 3:
        return False
    # не содержит букв
    if not re.search(r"[a-zа-я]", text):
        return False
    # только повторяющиеся символы
    if len(set(text)) < 2:
        return False
    # выглядит как мусор (одно короткое слово)
    if re.fullmatch(r"[a-zа-я]{1,3}", text):
        return False
    return True

@router.message(UserState.interest, F.text)
async def process_interests(message: Message, state: FSMContext):
    interests = message.text.strip()

    # 🔍 Проверяем корректность ввода
    if not _valid_interests(interests):
        await message.answer(
            "⚠️ Пожалуйста, опиши свои интересы понятнее.\n"
            "Например:\n"
            "• музеи и архитектура\n"
            "• прогулки по паркам\n"
            "• кофе и уютные места\n\n"
            "Попробуй ещё раз 👇"
        )
        await state.set_state(UserState.interest)
        return

    await state.update_data(interests=interests)
    await state.set_state(UserState.time)
    await message.answer("Вопрос 2 из 5:\nСколько часов у тебя есть на прогулку?", reply_markup=_time_kb())

@router.message(UserState.time, F.text)
async def process_time(message: Message, state: FSMContext):
    time_text = message.text.strip()
    try:
        time_hours = float(time_text)
        if time_hours < 0.5 or time_hours > 8:
            raise ValueError
    except ValueError:
        await message.answer("Пожалуйста, введи число от 0.5 до 8 часов:")
        return
    await state.update_data(time_hours=time_hours)
    await state.set_state(UserState.start_time)
    await message.answer(
        "Хочешь указать время начала прогулки?\n"
        "⏰ Например: 15:30 или 'сейчас'\n\n"
        "Если не важно — просто напиши 'сейчас'."
    )

@router.message(UserState.start_time, F.text)
async def process_start_time(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    now = datetime.datetime.now()

    if text in {"сейчас", "now"}:
        start_dt = now
    else:
        try:
            parsed = datetime.datetime.strptime(text, "%H:%M").time()
            start_dt = now.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
            if start_dt < now:
                start_dt += datetime.timedelta(days=1)
        except ValueError:
            await message.answer("Введи время в формате ЧЧ:ММ (например, 16:30) или 'сейчас'.")
            return

    await state.update_data(start_time=start_dt.isoformat())
    await state.set_state(UserState.transport)
    await message.answer("Как планируешь передвигаться?", reply_markup=_transport_kb())

@router.message(UserState.transport, F.text)
async def process_transport(message: Message, state: FSMContext):
    tr = _normalize_transport(message.text)
    await state.update_data(transport=tr)
    await state.set_state(UserState.location)
    await message.answer(
        "Откуда начнём прогулку?\n\n"
        "• Нажми кнопку, чтобы отправить геопозицию\n"
        "• Или отправь адрес текстом",
        reply_markup=_location_kb(),
    )

@router.message(
    UserState.location,
    F.text & ~F.text.in_({
        "🔁 Сгенерировать ещё", "🔄 Сбросить настройки", "ℹ️ Помощь",
        "/start", "start", "/help", "help", "🚀 Начать"
    })
)
async def process_location_text(message: Message, state: FSMContext):
    location_text = message.text.strip()
    coords = await Geocoder.get_coordinates(location_text)
    if not coords:
        await message.answer("Не удалось распознать адрес. Попробуй ещё раз или отправь геопозицию.")
        return
    lat, lon = coords
    display = await Geocoder.get_address_from_coords(lat, lon) or location_text
    await state.update_data(location_text=display, latitude=lat, longitude=lon)
    await generate_and_send_route(message, state, reuse=False)

@router.message(UserState.location, F.location)
async def process_location_geo(message: Message, state: FSMContext):
    lat = message.location.latitude
    lon = message.location.longitude
    display = await Geocoder.get_address_from_coords(lat, lon) or f"{lat:.5f}, {lon:.5f}"
    await state.update_data(location_text=display, latitude=lat, longitude=lon)
    await generate_and_send_route(message, state, reuse=False)

# === ГЕНЕРАЦИЯ МАРШРУТА ===
async def generate_and_send_route(message: Message, state: FSMContext, reuse: bool):
    data = await state.get_data()

    interests = data["interests"]
    time_hours = data["time_hours"]
    start_time_str = data.get("start_time")
    transport = data.get("transport", "walk")
    lat = data.get("latitude")
    lon = data.get("longitude")
    start_label = data.get("location_text", "")

    diversity_seed = int(time.time() * 1000) % 2_000_000_000
    start_dt = datetime.datetime.fromisoformat(start_time_str) if start_time_str else datetime.datetime.now()

    await message.answer(
        f"Собираю маршрут из точки: {start_label}\n"
        f"Интересы: {interests}\n"
        f"Транспорт: {transport}",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        route_data = await asyncio.wait_for(
            ai_service.generate_route(
                interests=interests,
                time_hours=time_hours,
                location=start_label,
                lat=lat,
                lon=lon,
                transport=transport,
                start_time=start_dt,
                diversity_seed=diversity_seed,
            ),
            timeout=60,
        )

        text = RouteFormatter.format_route(route_data, interests, time_hours)
        await message.answer(
            text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=_finish_kb(),
        )

        await state.update_data(
            data_last_interests=interests,
            data_last_time=time_hours,
            data_last_transport=transport,
            data_last_lat=lat,
            data_last_lon=lon,
            data_last_loc=start_label,
        )

    except asyncio.TimeoutError:
        await message.answer(
            "Сервис точек задерживается. Попробуйте ещё раз через минуту.",
            reply_markup=_finish_kb(),
        )
    except Exception:
        logger.exception("Ошибка генерации маршрута")
        await message.answer(
            "Не получилось построить маршрут. Попробуй поменять запрос или отправить геопозицию заново.",
            reply_markup=_finish_kb(),
        )

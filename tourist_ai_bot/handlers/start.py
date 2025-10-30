# handlers/start.py
import logging
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, Command
from states import UserState

router = Router()
logger = logging.getLogger(__name__)


def main_menu() -> ReplyKeyboardMarkup:
    """Кнопки по умолчанию, когда анкета не запущена."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Начать")],
            [KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True
    )
    
async def _start_questionnaire(message: Message, state: FSMContext) -> None:
    # Полный сброс FSM и данных, чтобы начать опрос "с нуля"
    try:
        await state.clear()
    except Exception:
        logger.exception("Не удалось очистить состояние FSM")

    await state.set_state(UserState.interest)
    await message.answer(
        "Привет! Я соберу для тебя персональный маршрут.\n\n"
        "Вопрос 1 из 4:\n"
        "Опиши свои интересы (например: «стрит-арт, панорамы» или «история, кофейни»).",
        reply_markup=ReplyKeyboardRemove(),   # никаких лишних кнопок на первом шаге
    )

@router.message(F.text.in_({"/start", "start", "🚀 Начать"}))
async def cmd_start(message: Message, state: FSMContext) -> None:
    """
    Старт: показываем меню. Если нажали «🚀 Начать», сразу переводим в состояние ввода интересов.
    """
    # если это именно кнопка/команда "Начать" — запускаем анкету
    if message.text == "🚀 Начать":
        await state.clear()
        await state.set_state(UserState.interest)
        await message.answer(
            "Вопрос 1 из 4: опиши интересы (например: «стрит-арт, панорамы» или «музеи, архитектура»).",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # просто /start — показываем главное меню
    await state.clear()
    await message.answer(
        "Привет! Я соберу персональный маршрут рядом с тобой — по твоим интересам, времени и способу передвижения.\n\n"
        "Нажми «🚀 Начать», чтобы ввести интересы.",
        reply_markup=main_menu(),
    )


@router.message(F.text.in_({"/help", "help", "ℹ️ Помощь"}))
async def cmd_help(message: Message, state: FSMContext) -> None:
    """Краткая инструкция."""
    await message.answer(
        "Как пользоваться:\n"
        "1) «🚀 Начать» → укажи интересы\n"
        "2) Задай время прогулки\n"
        "3) Выбери способ передвижения (пешком/авто/вел/ОТ)\n"
        "4) Отправь геопозицию или введи адрес текстом\n\n"
        "Если результат не зашёл — жми «🔁 Сгенерировать ещё», чтобы получить другой вариант.",
        reply_markup=main_menu(),
    )


# ВАЖНО: этот обработчик не должен блокировать другие!
@router.message(flags={"block": False})
async def any_message_show_menu(message: Message, state: FSMContext) -> None:
    """
    Любое сообщение вне анкеты: показываем меню.
    Если анкета уже идёт (есть состояние FSM) — ничего не отвечаем,
    чтобы не мешать хендлерам состояний.
    """
    st = await state.get_state()
    if not st:
        await message.answer("Нажми «🚀 Начать», чтобы подобрать маршрут.", reply_markup=main_menu())
    # если st установлен — даём событию пройти дальше к FSM-хендлерам

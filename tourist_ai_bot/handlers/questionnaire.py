from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from states import UserState
from services.geocoder import Geocoder
from services.ai_service import AIService
from services.route_formatter import RouteFormatter

router = Router()

import logging

@router.message(UserState.interest, F.text)
async def process_interests(message: Message, state: FSMContext):
    interests = message.text.strip()
    
    if len(interests) < 3:
        await message.answer("Пожалуйста, введите интересы текстом (минимум 3 символа). Попробуйте еще раз:")
        return
    
    await state.update_data(interests=interests)
    await state.set_state(UserState.time)
    
    time_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2")],
            [KeyboardButton(text="3"), KeyboardButton(text="4")],
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "✅ Отлично! Запомнил твои интересы.\n\n"
        "Вопрос 2 из 3:\nСколько часов у тебя есть на прогулку?",
        reply_markup=time_keyboard
    )

@router.message(UserState.time, F.text)
async def process_time(message: Message, state: FSMContext):
    time_text = message.text.strip()
    
    try:
        time_hours = float(time_text)
        if time_hours < 0.5 or time_hours > 8:
            raise ValueError
    except ValueError:
        await message.answer("Пожалуйста, введите число от 0.5 до 8 часов:")
        return
    
    await state.update_data(time_hours=time_hours)
    await state.set_state(UserState.location)
    
    location_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить местоположение", request_location=True)],
            [KeyboardButton(text="Ввести адрес вручную")],
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "✅ Отлично! Запомнил время.\n\n"
        "Вопрос 3 из 3:\n"
        "Откуда начнем прогулку?\n\n"
        "• Нажми кнопку ниже чтобы отправить геолокацию\n"
        "• Или напиши адрес текстом (например: 'Площадь Горького' или 'ул. Большая Покровская, 1')",
        reply_markup=location_keyboard
    )

@router.message(UserState.location, F.text)
async def process_location_text(message: Message, state: FSMContext):
    location_text = message.text.strip()
    
    if len(location_text) < 3:
        await message.answer("Пожалуйста, введите корректный адрес (минимум 3 символа):")
        return
    
    coordinates = await Geocoder.get_coordinates(location_text)
    
    if coordinates:
        lat, lon = coordinates
        location_display = await Geocoder.get_address_from_coords(lat, lon) or f"📍 {location_text}"
    else:
        lat, lon = None, None
        location_display = f"📍 {location_text}"
        await message.answer("⚠️ Использую текстовый адрес для построения маршрута")
    
    await state.update_data(
        location_text=location_display,
        latitude=lat,
        longitude=lon
    )
    
    await generate_and_send_route(message, state)

@router.message(UserState.location, F.location)
async def process_location_geo(message: Message, state: FSMContext):
    location = message.location
    lat, lon = location.latitude, location.longitude
    
    location_display = await Geocoder.get_address_from_coords(lat, lon)
    
    await state.update_data(
        location_text=location_display,
        latitude=lat,
        longitude=lon
    )
    
    await generate_and_send_route(message, state)

async def generate_and_send_route(message: Message, state: FSMContext):
    """Генерирует и отправляет маршрут пользователю"""
    
    user_data = await state.get_data()
    
    summary = (
        "🎉 Отлично! Собрал все данные!\n\n"
        "Вот что у нас получилось:\n"
        f"• 🎯 Интересы: {user_data['interests']}\n"
        f"• ⏱ Время: {user_data['time_hours']} часа(ов)\n"
        f"• 📍 Старт: {user_data['location_text']}\n\n"
        "Сейчас создам твой маршрут... 🗺️"
    )
    
    await message.answer(summary, reply_markup=ReplyKeyboardRemove())
    
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    try:
        # Используем наш умный fallback
        ai_service = AIService()
        route_data = await ai_service.generate_route(
            interests=user_data['interests'],
            time_hours=user_data['time_hours'],
            location=user_data['location_text'],
            lat=user_data.get('latitude'),
            lon=user_data.get('longitude')
        )
        
        # Форматируем ответ
        route_message = RouteFormatter.format_route(
            route_data, 
            user_data['interests'], 
            user_data['time_hours']
        )
        
        await message.answer(route_message, parse_mode="Markdown")
        
    except Exception as e:
        logging.error(f"Ошибка генерации маршрута: {e}")
        error_message = RouteFormatter.format_error_message()
        await message.answer(error_message)
    
    await state.clear()
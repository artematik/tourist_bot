from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

router = Router()

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    
    if current_state is None:
        await message.answer("Нет активного диалога для отмены.")
        return
        
    await state.clear()
    await message.answer(
        "❌ Диалог отменен. Чтобы начать заново, отправьте /start",
        reply_markup=None
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🤖 Помощь по боту «Гуляй-НН»\n\n"
        "Доступные команды:\n"
        "/start - начать создание маршрута\n"
        "/cancel - отменить текущий диалог\n"
        "/help - показать эту справку\n\n"
        "Бот задаст вам 3 вопроса для создания персонализированного маршрута по Нижнему Новгороду."
    )

# Обработчик для любых сообщений не в FSM
@router.message()
async def handle_other_messages(message: Message):
    await message.answer(
        "Отправьте /start чтобы начать создание маршрута\n"
        "Или /help для справки"
    )
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from handlers import start, questionnaire, common

async def main():
    logging.basicConfig(level=logging.INFO)
    logging.info("Бот запускается...")
    
    storage = MemoryStorage()
    
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=storage)
    
    dp.include_router(start.router)
    dp.include_router(questionnaire.router)
    dp.include_router(common.router)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
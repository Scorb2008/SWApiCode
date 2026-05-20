import asyncio
import logging

from aiogram import Bot, Dispatcher

from src.bot.bot import bot
from src.bot.handlers import admin, documents, start, user
from src.db.database import init_db

logging.basicConfig(level=logging.INFO)


async def start_polling():
    await init_db()

    dp = Dispatcher()

    dp.include_router(documents.router)
    dp.include_router(start.router)
    dp.include_router(user.router)
    dp.include_router(admin.router)

    await dp.start_polling(bot)


def main():
    asyncio.run(start_polling())


if __name__ == "__main__":
    main()

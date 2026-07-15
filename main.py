"""
Taxi Bot — asosiy kirish nuqtasi.
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database.engine import init_db
from handlers import common, driver, passenger, admin
from middlewares.role_middleware import RoleMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Ma'lumotlar bazasi tayyorlanmoqda...")
    await init_db()
    logger.info("Ma'lumotlar bazasi tayyor.")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Middleware — har bir xabarda rolni aniqlaydi
    dp.message.middleware(RoleMiddleware())
    dp.callback_query.middleware(RoleMiddleware())

    # Router tartib muhim:
    # 1. Admin — eng avval (admin tugmalari boshqalar bilan to'qnashmasin)
    # 2. Driver
    # 3. Passenger
    # 4. Common (/start)
    dp.include_router(admin.router)
    dp.include_router(driver.router)
    dp.include_router(passenger.router)
    dp.include_router(common.router)

    logger.info("Bot ishga tushirilmoqda...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("Bot to'xtatildi.")


if __name__ == "__main__":
    asyncio.run(main())

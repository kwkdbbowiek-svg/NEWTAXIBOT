import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# Railway PostgreSQL URL ni asyncpg formatiga o'tkazish
_raw_db_url: str = os.getenv("DATABASE_URL", "")
if _raw_db_url.startswith("postgres://"):
    # Railway eski format beradi — asyncpg uchun to'g'irlaymiz
    _raw_db_url = _raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw_db_url.startswith("postgresql://") and "+asyncpg" not in _raw_db_url:
    _raw_db_url = _raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
DATABASE_URL: str = _raw_db_url

ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
DRIVERS_CHANNEL_ID: int = int(os.getenv("DRIVERS_CHANNEL_ID", "0"))
ORDERS_CHANNEL_ID: int = int(os.getenv("ORDERS_CHANNEL_ID", "0"))

# @ belgisi bo'lsa olib tashlaymiz — kod ichida @{ADMIN_USERNAME} ishlatiladi
_admin_username_raw: str = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_USERNAME: str = _admin_username_raw.lstrip("@")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN muhit o'zgaruvchisi topilmadi!")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL muhit o'zgaruvchisi topilmadi!")

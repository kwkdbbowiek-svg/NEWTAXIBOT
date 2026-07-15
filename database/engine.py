from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import DATABASE_URL
from database.models import Base

_is_sqlite = DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        # 10 000 foydalanuvchi uchun yetarli pool
        pool_size=20,
        max_overflow=40,
        pool_pre_ping=True,           # o'lik konneksiyalarni avtomatik tekshiradi
        pool_recycle=1800,            # 30 daqiqada konneksiyani yangilaydi
        pool_timeout=30,              # konneksiya olishga 30 sek kutadi
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """
    Jadvallarni yaratadi va yetishmayotgan ustunlarni qo'shadi.
    Eski baza strukturasidagi barcha nomuvofiqliklarni tuzatadi.
    """
    async with engine.begin() as conn:
        # Jadvallarni yaratish (mavjud bo'lmasa)
        await conn.run_sync(Base.metadata.create_all)

        if not _is_sqlite:
            # PostgreSQL: eski baza bilan muvofiqlik uchun safe migration
            migrations = [
                # users.role
                """
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='users' AND column_name='role'
                    ) THEN
                        ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT NULL;
                    END IF;
                END $$;
                """,
                # users.created_at
                """
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='users' AND column_name='created_at'
                    ) THEN
                        ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT NOW() NOT NULL;
                    END IF;
                END $$;
                """,
                # users.last_active
                """
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='users' AND column_name='last_active'
                    ) THEN
                        ALTER TABLE users ADD COLUMN last_active TIMESTAMP DEFAULT NOW();
                    END IF;
                    UPDATE users SET last_active = NOW() WHERE last_active IS NULL;
                END $$;
                """,
                # drivers.is_active
                """
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='drivers' AND column_name='is_active'
                    ) THEN
                        ALTER TABLE drivers ADD COLUMN is_active BOOLEAN DEFAULT TRUE;
                    END IF;
                END $$;
                """,
                # drivers.balance
                """
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='drivers' AND column_name='balance'
                    ) THEN
                        ALTER TABLE drivers ADD COLUMN balance FLOAT DEFAULT 0.0;
                    END IF;
                END $$;
                """,
                # orders.commission_charged
                """
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='orders' AND column_name='commission_charged'
                    ) THEN
                        ALTER TABLE orders ADD COLUMN commission_charged FLOAT DEFAULT 0.0;
                    END IF;
                END $$;
                """,
                # orders.channel_message_id
                """
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='orders' AND column_name='channel_message_id'
                    ) THEN
                        ALTER TABLE orders ADD COLUMN channel_message_id BIGINT DEFAULT NULL;
                    END IF;
                END $$;
                """,
                # orders.updated_at
                """
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='orders' AND column_name='updated_at'
                    ) THEN
                        ALTER TABLE orders ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();
                    END IF;
                END $$;
                """,
                # orders.cargo_description
                """
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='orders' AND column_name='cargo_description'
                    ) THEN
                        ALTER TABLE orders ADD COLUMN cargo_description TEXT DEFAULT NULL;
                    END IF;
                END $$;
                """,
            ]
            for sql in migrations:
                await conn.execute(text(sql))


async def get_session() -> AsyncSession:  # type: ignore[return]
    async with AsyncSessionLocal() as session:
        yield session

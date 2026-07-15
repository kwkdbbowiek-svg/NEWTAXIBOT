"""
Ma'lumotlar bazasi so'rovlari (CRUD).

PostgreSQL bazasida role/status ustunlari VARCHAR sifatida saqlangan.
Barcha taqqoslashlar raw SQL text() orqali amalga oshiriladi.
"""
from __future__ import annotations

import logging
from datetime import datetime, date

from sqlalchemy import select, update, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from config import DATABASE_URL
from database.models import User, Driver, Order, Settings, UserRole

logger = logging.getLogger(__name__)

_USE_FOR_UPDATE = not DATABASE_URL.startswith("sqlite")
_IS_SQLITE = DATABASE_URL.startswith("sqlite")


# ─────────────────────────────────────────────
# FOYDALANUVCHI
# ─────────────────────────────────────────────

async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: str | None,
    full_name: str,
) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        return user
    try:
        user = User(id=user_id, username=username, full_name=full_name)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
    except IntegrityError:
        await session.rollback()
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one()


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def set_user_role(session: AsyncSession, user_id: int, role: UserRole) -> None:
    # role.value = "driver" yoki "passenger" — VARCHAR ga saqlash
    await session.execute(
        text("UPDATE users SET role = :role WHERE id = :uid"),
        {"role": role.value, "uid": user_id},
    )
    await session.commit()


async def get_all_users_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(select(User.id))
    return list(result.scalars().all())


# ─────────────────────────────────────────────
# HAYDOVCHI
# ─────────────────────────────────────────────

async def create_driver(
    session: AsyncSession,
    user_id: int,
    full_name: str,
    phone: str,
    car_model: str,
    car_number: str,
) -> Driver:
    driver = Driver(
        user_id=user_id,
        full_name=full_name,
        phone=phone,
        car_model=car_model,
        car_number=car_number,
    )
    session.add(driver)
    await session.commit()
    await session.refresh(driver)
    return driver


async def get_driver_by_user_id(session: AsyncSession, user_id: int) -> Driver | None:
    result = await session.execute(select(Driver).where(Driver.user_id == user_id))
    return result.scalar_one_or_none()


async def approve_driver(session: AsyncSession, user_id: int) -> Driver | None:
    await session.execute(
        text("UPDATE drivers SET status = 'approved' WHERE user_id = :uid"),
        {"uid": user_id},
    )
    await session.commit()
    result = await session.execute(select(Driver).where(Driver.user_id == user_id))
    return result.scalar_one_or_none()


async def reject_driver(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        text("UPDATE drivers SET status = 'rejected' WHERE user_id = :uid"),
        {"uid": user_id},
    )
    await session.commit()


async def get_all_approved_driver_ids(session: AsyncSession) -> list[int]:
    """Tasdiqlangan haydovchilarning user_id larini raw SQL bilan oladi."""
    result = await session.execute(
        text("""
            SELECT user_id FROM drivers
            WHERE status::text ILIKE '%approved%'
              AND is_active = true
        """)
    )
    ids = [row[0] for row in result.fetchall()]
    logger.info(f"Tasdiqlangan haydovchilar: {len(ids)} ta")
    return ids


async def top_up_balance(session: AsyncSession, user_id: int, amount: float) -> Driver | None:
    result = await session.execute(select(Driver).where(Driver.user_id == user_id))
    driver = result.scalar_one_or_none()
    if driver:
        driver.balance = round(driver.balance + amount)
        await session.commit()
        await session.refresh(driver)
    return driver


async def deduct_balance(session: AsyncSession, user_id: int, amount: float) -> Driver | None:
    result = await session.execute(select(Driver).where(Driver.user_id == user_id))
    driver = result.scalar_one_or_none()
    if driver:
        driver.balance = round(max(driver.balance - amount, 0.0))
        await session.commit()
        await session.refresh(driver)
    return driver


# ─────────────────────────────────────────────
# BUYURTMA
# ─────────────────────────────────────────────

async def create_order(
    session: AsyncSession,
    passenger_id: int,
    from_location: str,
    to_location: str,
    passenger_phone: str,
    passenger_count: int,
    cargo_description: str | None = None,
) -> Order:
    order = Order(
        passenger_id=passenger_id,
        from_location=from_location,
        to_location=to_location,
        passenger_phone=passenger_phone,
        passenger_count=passenger_count,
        cargo_description=cargo_description,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    result = await session.execute(select(Order).where(Order.id == order_id))
    return result.scalar_one_or_none()


async def claim_order_atomic(
    order_id: int,
    driver_user_id: int,
    commission: float,
) -> tuple[bool, str]:
    """
    Atomic tranzaksiya — faqat bitta haydovchi zakaz oladi.
    Raw SQL ishlatiladi chunki PostgreSQL da enum cast muammosi bor.
    """
    from database.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            async with session.begin():
                # 1. Buyurtmani qulflash va tekshirish
                lock = "FOR UPDATE" if _USE_FOR_UPDATE else ""
                order_row = (await session.execute(
                    text(f"SELECT id, status, passenger_count FROM orders WHERE id = :oid {lock}"),
                    {"oid": order_id},
                )).fetchone()

                if not order_row:
                    return False, "order_not_found"
                order_status = str(order_row[1]).lower()
                if "pending" not in order_status:
                    return False, "already_claimed"

                # 2. Haydovchini qulflash va tekshirish
                driver_row = (await session.execute(
                    text(f"SELECT user_id, status, balance FROM drivers WHERE user_id = :uid {lock}"),
                    {"uid": driver_user_id},
                )).fetchone()

                if not driver_row:
                    return False, "driver_not_found"
                driver_status = str(driver_row[1]).lower()
                if "approved" not in driver_status:
                    return False, "driver_not_approved"
                if float(driver_row[2]) < commission:
                    return False, "insufficient_balance"

                # 3. Atomic yangilash
                new_balance = round(float(driver_row[2]) - commission)
                await session.execute(
                    text("UPDATE drivers SET balance = :bal WHERE user_id = :uid"),
                    {"bal": new_balance, "uid": driver_user_id},
                )
                await session.execute(
                    text("""
                        UPDATE orders
                        SET status = 'claimed',
                            driver_id = :did,
                            commission_charged = :comm,
                            updated_at = NOW()
                        WHERE id = :oid
                    """),
                    {"did": driver_user_id, "comm": commission, "oid": order_id},
                )
                return True, "success"

        except Exception as e:
            logger.error(f"claim_order_atomic xatosi: {e}")
            return False, "error"


async def cancel_order(
    session: AsyncSession,
    order_id: int,
    passenger_id: int,
) -> tuple[bool, str]:
    try:
        async with session.begin():
            lock = "FOR UPDATE" if _USE_FOR_UPDATE else ""
            row = (await session.execute(
                text(f"SELECT status FROM orders WHERE id = :oid AND passenger_id = :pid {lock}"),
                {"oid": order_id, "pid": passenger_id},
            )).fetchone()

            if not row:
                return False, "not_found"
            status = str(row[0]).lower()
            if "claimed" in status:
                return False, "already_claimed"
            if "cancelled" in status:
                return False, "already_cancelled"

            await session.execute(
                text("UPDATE orders SET status = 'cancelled', updated_at = NOW() WHERE id = :oid"),
                {"oid": order_id},
            )
            return True, "success"

    except Exception as e:
        logger.error(f"cancel_order xatosi: {e}")
        return False, "error"


# ─────────────────────────────────────────────
# SOZLAMALAR
# ─────────────────────────────────────────────

async def get_setting(session: AsyncSession, key: str, default: str = "0") -> str:
    result = await session.execute(select(Settings).where(Settings.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else default


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    if _IS_SQLITE:
        result = await session.execute(select(Settings).where(Settings.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            session.add(Settings(key=key, value=value))
        await session.commit()
    else:
        stmt = (
            pg_insert(Settings)
            .values(key=key, value=value)
            .on_conflict_do_update(index_elements=["key"], set_={"value": value})
        )
        await session.execute(stmt)
        await session.commit()


async def get_commission(session: AsyncSession) -> float:
    value = await get_setting(session, "commission_per_passenger", "1000")
    return float(value)


# ─────────────────────────────────────────────
# STATISTIKA — to'liq raw SQL
# ─────────────────────────────────────────────

async def get_statistics(session: AsyncSession) -> dict:
    today_start = datetime.combine(date.today(), datetime.min.time())

    rows = (await session.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM users)                                          AS total_users,
            (SELECT COUNT(*) FROM users WHERE role::text ILIKE '%passenger%')     AS total_passengers,
            (SELECT COUNT(*) FROM drivers WHERE status::text ILIKE '%approved%')  AS drivers_approved,
            (SELECT COUNT(*) FROM drivers WHERE status::text ILIKE '%pending%')   AS drivers_pending,
            (SELECT COUNT(*) FROM orders WHERE status::text ILIKE '%claimed%')    AS orders_done,
            (SELECT COUNT(*) FROM orders WHERE status::text ILIKE '%pending%')    AS orders_pending,
            (SELECT COUNT(*) FROM orders WHERE status::text ILIKE '%cancelled%')  AS orders_cancelled,
            (SELECT COUNT(*) FROM orders
             WHERE status::text ILIKE '%claimed%'
               AND updated_at >= :today)                                          AS orders_today,
            (SELECT COALESCE(SUM(commission_charged), 0)
             FROM orders WHERE status::text ILIKE '%claimed%')                    AS total_commission
    """), {"today": today_start})).fetchone()

    return {
        "total_users":           int(rows[0] or 0),
        "total_passengers":      int(rows[1] or 0),
        "total_drivers_approved": int(rows[2] or 0),
        "total_drivers_pending":  int(rows[3] or 0),
        "total_orders_done":     int(rows[4] or 0),
        "total_orders_pending":  int(rows[5] or 0),
        "total_orders_cancelled": int(rows[6] or 0),
        "total_orders_today":    int(rows[7] or 0),
        "total_commission":      int(rows[8] or 0),
    }

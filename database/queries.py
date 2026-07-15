"""
Ma'lumotlar bazasi so'rovlari (CRUD).

SQLite (test):    FOR UPDATE ishlatilmaydi (aiosqlite serialized).
PostgreSQL (prod): FOR UPDATE (Pessimistic Lock) to'liq ishlaydi.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from config import DATABASE_URL
from database.models import User, Driver, Order, Settings, UserRole, DriverStatus, OrderStatus

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
    """
    Foydalanuvchini oladi yoki yaratadi.
    Race condition (parallel /start) uchun IntegrityError ushlaydi.
    """
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
        # Parallel so'rov allaqachon yaratib qo'ygan — qayta o'qiymiz
        await session.rollback()
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one()


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def set_user_role(session: AsyncSession, user_id: int, role: UserRole) -> None:
    await session.execute(update(User).where(User.id == user_id).values(role=role))
    await session.commit()


async def get_all_users_ids(session: AsyncSession) -> list[int]:
    """Faqat ID larni qaytaradi — katta bazada xotira tejaladi."""
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
        update(Driver).where(Driver.user_id == user_id).values(status=DriverStatus.APPROVED)
    )
    await session.commit()
    result = await session.execute(select(Driver).where(Driver.user_id == user_id))
    return result.scalar_one_or_none()


async def reject_driver(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        update(Driver).where(Driver.user_id == user_id).values(status=DriverStatus.REJECTED)
    )
    await session.commit()


async def get_all_approved_driver_ids(session: AsyncSession) -> list[int]:
    """Faqat tasdiqlangan haydovchilarning user_id larini qaytaradi."""
    result = await session.execute(
        select(Driver.user_id).where(
            Driver.status == DriverStatus.APPROVED,
            Driver.is_active == True,
        )
    )
    return list(result.scalars().all())


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
    XAVFSIZ ATOMIC TRANZAKSIYA.
    O'zi yangi session ochadi — tashqaridan session uzatilmaydi.

    PostgreSQL: SELECT ... FOR UPDATE (pessimistic lock) — 10 000 haydovchi
                bir vaqtda bosganida ham faqat bittasi buyurtmani oladi.
    SQLite:     lock yo'q, aiosqlite serialized — test uchun yetarli.

    Qaytaradi: (muvaffaqiyat: bool, sabab: str)
    """
    from database.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            async with session.begin():
                # 1. Buyurtmani qulflash
                order_q = select(Order).where(Order.id == order_id)
                if _USE_FOR_UPDATE:
                    order_q = order_q.with_for_update(nowait=False)
                order = (await session.execute(order_q)).scalar_one_or_none()

                if not order:
                    return False, "order_not_found"
                if order.status != OrderStatus.PENDING:
                    return False, "already_claimed"

                # 2. Haydovchini qulflash
                driver_q = select(Driver).where(Driver.user_id == driver_user_id)
                if _USE_FOR_UPDATE:
                    driver_q = driver_q.with_for_update(nowait=False)
                driver = (await session.execute(driver_q)).scalar_one_or_none()

                if not driver:
                    return False, "driver_not_found"
                if driver.status != DriverStatus.APPROVED:
                    return False, "driver_not_approved"
                if driver.balance < commission:
                    return False, "insufficient_balance"

                # 3. Atomic o'zgarishlar
                driver.balance = round(driver.balance - commission)
                order.status = OrderStatus.CLAIMED
                order.driver_id = driver_user_id
                order.commission_charged = commission

                return True, "success"

        except Exception as e:
            logger.error(f"claim_order_atomic xatosi: {e}")
            return False, "error"


async def cancel_order(
    session: AsyncSession,
    order_id: int,
    passenger_id: int,
) -> tuple[bool, str]:
    """Buyurtmani bekor qilish — tranzaksiya ichida."""
    try:
        async with session.begin():
            order_q = select(Order).where(
                Order.id == order_id,
                Order.passenger_id == passenger_id,
            )
            if _USE_FOR_UPDATE:
                order_q = order_q.with_for_update(nowait=False)

            order = (await session.execute(order_q)).scalar_one_or_none()

            if not order:
                return False, "not_found"
            if order.status == OrderStatus.CLAIMED:
                return False, "already_claimed"
            if order.status == OrderStatus.CANCELLED:
                return False, "already_cancelled"

            order.status = OrderStatus.CANCELLED
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
# STATISTIKA
# ─────────────────────────────────────────────

async def get_statistics(session: AsyncSession) -> dict:
    from datetime import datetime, date

    # Jami foydalanuvchilar
    total_users = await session.scalar(
        select(func.count()).select_from(User)
    ) or 0

    # Yo'lovchilar
    total_passengers = await session.scalar(
        select(func.count()).select_from(User).where(User.role == UserRole.PASSENGER)
    ) or 0

    # Tasdiqlangan haydovchilar
    total_drivers_approved = await session.scalar(
        select(func.count()).select_from(Driver).where(Driver.status == DriverStatus.APPROVED)
    ) or 0

    # Kutayotgan (tasdiqlash kerak) haydovchilar
    total_drivers_pending = await session.scalar(
        select(func.count()).select_from(Driver).where(Driver.status == DriverStatus.PENDING)
    ) or 0

    # Jami bajarilgan zakazlar
    total_orders_done = await session.scalar(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.CLAIMED)
    ) or 0

    # Aktiv (kutayotgan) zakazlar
    total_orders_pending = await session.scalar(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.PENDING)
    ) or 0

    # Bekor qilingan zakazlar
    total_orders_cancelled = await session.scalar(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.CANCELLED)
    ) or 0

    # Bugungi zakazlar (CLAIMED)
    today_start = datetime.combine(date.today(), datetime.min.time())
    total_orders_today = await session.scalar(
        select(func.count()).select_from(Order).where(
            Order.status == OrderStatus.CLAIMED,
            Order.updated_at >= today_start,
        )
    ) or 0

    # Jami yig'ilgan komissiya (so'mda)
    total_commission = await session.scalar(
        select(func.coalesce(func.sum(Order.commission_charged), 0)).select_from(Order).where(
            Order.status == OrderStatus.CLAIMED
        )
    ) or 0

    return {
        "total_users": total_users,
        "total_passengers": total_passengers,
        "total_drivers_approved": total_drivers_approved,
        "total_drivers_pending": total_drivers_pending,
        "total_orders_done": total_orders_done,
        "total_orders_pending": total_orders_pending,
        "total_orders_cancelled": total_orders_cancelled,
        "total_orders_today": total_orders_today,
        "total_commission": int(total_commission),
    }

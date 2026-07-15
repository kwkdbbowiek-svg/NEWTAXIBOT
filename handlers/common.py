"""
Umumiy handlerlar: /start — rolga qarab menyuni ko'rsatadi.
"""
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config import ADMIN_ID
from database.engine import AsyncSessionLocal
from database.queries import get_or_create_user, get_driver_by_user_id
from keyboards.common import role_select_keyboard
from keyboards.driver import driver_menu_keyboard
from keyboards.passenger import passenger_menu_keyboard
from keyboards.admin import admin_menu_keyboard

router = Router()


def _status_is(obj_status, value: str) -> bool:
    """
    PostgreSQL bazasida ustun VARCHAR bo'lishi mumkin (enum type yo'q).
    str() orqali taqqoslaymiz — har ikki holatda ham ishlaydi.
    """
    return str(obj_status).lower() in (value, f"driverstatus.{value}", f"orderstatus.{value}")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()

    user_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            user_id=user_id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )

    # Admin
    if user_id == ADMIN_ID:
        await message.answer(
            "⚙️ Salom, Admin!",
            reply_markup=admin_menu_keyboard(),
        )
        return

    # Rol tanlangan bo'lsa — to'g'ri menyuga yuboramiz
    if user and user.role:
        role_val = str(user.role).lower()
        is_driver = role_val in ("driver", "userrole.driver")
        is_passenger = role_val in ("passenger", "userrole.passenger")

        if is_driver:
            async with AsyncSessionLocal() as session:
                driver = await get_driver_by_user_id(session, user_id)

            if driver and _status_is(driver.status, "approved"):
                await message.answer(
                    "✅ Xush kelibsiz, haydovchi!",
                    reply_markup=driver_menu_keyboard(),
                )
            elif driver and _status_is(driver.status, "pending"):
                await message.answer(
                    "⏳ Arizangiz ko'rib chiqilmoqda. Admin tasdiqlashini kuting.",
                    reply_markup=driver_menu_keyboard(),
                )
            else:
                await message.answer(
                    "👋 Salom! Qaysi sifatda davom etmoqchisiz?",
                    reply_markup=role_select_keyboard(),
                )
            return

        if is_passenger:
            await message.answer(
                "🧍 Xush kelibsiz!",
                reply_markup=passenger_menu_keyboard(),
            )
            return

    # Hali rol tanlanmagan
    await message.answer(
        "👋 Salom! Taxi botga xush kelibsiz!\n\n"
        "Qaysi sifatda davom etmoqchisiz?",
        reply_markup=role_select_keyboard(),
    )

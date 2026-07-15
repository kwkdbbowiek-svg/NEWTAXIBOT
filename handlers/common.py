"""
Umumiy handlerlar: /start — rolga qarab menyuni ko'rsatadi.
"""
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config import ADMIN_ID
from database.engine import AsyncSessionLocal
from database.models import DriverStatus
from database.queries import get_or_create_user, get_driver_by_user_id
from keyboards.common import role_select_keyboard
from keyboards.driver import driver_menu_keyboard
from keyboards.passenger import passenger_menu_keyboard
from keyboards.admin import admin_menu_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    # Davom etayotgan FSM ni tozalaymiz
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
        if user.role.value == "driver":
            async with AsyncSessionLocal() as session:
                driver = await get_driver_by_user_id(session, user_id)

            if driver and driver.status == DriverStatus.APPROVED:
                await message.answer(
                    "✅ Xush kelibsiz, haydovchi!",
                    reply_markup=driver_menu_keyboard(),
                )
            elif driver and driver.status == DriverStatus.PENDING:
                await message.answer(
                    "⏳ Arizangiz ko'rib chiqilmoqda. Admin tasdiqlashini kuting.",
                    reply_markup=driver_menu_keyboard(),
                )
            else:
                # Rad etilgan yoki driver yo'q — qayta rol tanlash
                await message.answer(
                    "👋 Salom! Qaysi sifatda davom etmoqchisiz?",
                    reply_markup=role_select_keyboard(),
                )
            return

        if user.role.value == "passenger":
            await message.answer(
                "🧍 Xush kelibsiz!",
                reply_markup=passenger_menu_keyboard(),
            )
            return

    # Hali rol tanlanmagan — rol tanlash
    await message.answer(
        "👋 Salom! Taxi botga xush kelibsiz!\n\n"
        "Qaysi sifatda davom etmoqchisiz?",
        reply_markup=role_select_keyboard(),
    )

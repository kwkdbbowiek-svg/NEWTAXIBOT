"""
Yo'lovchi handlerlari.
Faqat rol="passenger" yoki rol=None (yangi) foydalanuvchilarga ishlaydi.
Admin va haydovchilar bu handlerlarga kirmaydi.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import ADMIN_ID, ORDERS_CHANNEL_ID
from database.engine import AsyncSessionLocal
from database.models import UserRole
from database.queries import (
    set_user_role,
    create_order,
    cancel_order,
    get_order,
    get_all_approved_drivers,
)
from keyboards.common import (
    role_select_keyboard,
    share_contact_keyboard,
    cancel_keyboard,
)
from keyboards.passenger import passenger_menu_keyboard, confirm_order_keyboard, location_keyboard
from keyboards.driver import order_action_keyboard
from states.passenger_states import OrderCreation

logger = logging.getLogger(__name__)
router = Router()


# ─── Admin ni bu routerdan chiqarib yuborish ───
class NotAdmin(Filter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id != ADMIN_ID


router.message.filter(NotAdmin())


# ─────────────────────────────────────────────
# YO'LOVCHI SIFATIDA KIRISH
# ─────────────────────────────────────────────

@router.message(F.text == "🧍 Yo'lovchi")
async def passenger_entry(message: Message, user_role: str | None) -> None:
    # Haydovchi yo'lovchi bo'la olmaydi
    if user_role == "driver":
        await message.answer("❌ Siz haydovchi sifatida ro'yxatdansiz.")
        return

    async with AsyncSessionLocal() as session:
        await set_user_role(session, message.from_user.id, UserRole.PASSENGER)

    await message.answer(
        "🧍 Yo'lovchi menyusi:",
        reply_markup=passenger_menu_keyboard(),
    )


# ─────────────────────────────────────────────
# BUYURTMA BERISH — faqat passenger uchun
# ─────────────────────────────────────────────

@router.message(F.text == "📦 Buyurtma berish")
async def start_order(message: Message, state: FSMContext, user_role: str | None) -> None:
    if user_role != "passenger":
        return  # Haydovchi yoki boshqalar uchun javob yo'q

    await message.answer(
        "📍 <b>Qayerdan?</b>\nManzilni tanlang:",
        reply_markup=location_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(OrderCreation.from_location)


@router.message(OrderCreation.from_location, F.text)
async def order_from_location(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=passenger_menu_keyboard())
        return

    if message.text not in ("🏙 Shirin", "🏘 Bekobod"):
        await message.answer("Iltimos, quyidagi tugmalardan birini tanlang! ⬇️",
                             reply_markup=location_keyboard())
        return

    await state.update_data(from_location=message.text.strip())
    await message.answer(
        "📍 <b>Qayerga?</b>\nManzilni tanlang:",
        reply_markup=location_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(OrderCreation.to_location)


@router.message(OrderCreation.to_location, F.text)
async def order_to_location(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=passenger_menu_keyboard())
        return

    if message.text not in ("🏙 Shirin", "🏘 Bekobod"):
        await message.answer("Iltimos, quyidagi tugmalardan birini tanlang! ⬇️",
                             reply_markup=location_keyboard())
        return

    await state.update_data(to_location=message.text.strip())
    await message.answer(
        "📱 Telefon raqamingizni ulashing:",
        reply_markup=share_contact_keyboard(),
    )
    await state.set_state(OrderCreation.phone)


@router.message(OrderCreation.phone, F.contact)
async def order_phone_contact(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=message.contact.phone_number)
    await message.answer(
        "👥 <b>Necha kishi ketasiz?</b>\nRaqam kiriting:",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(OrderCreation.passenger_count)


@router.message(OrderCreation.phone, F.text)
async def order_phone_text(message: Message) -> None:
    await message.answer("Iltimos, tugma orqali raqamingizni ulashing! ⬇️")


@router.message(OrderCreation.passenger_count, F.text)
async def order_passenger_count(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=passenger_menu_keyboard())
        return

    if not message.text.isdigit() or int(message.text) < 1:
        await message.answer("❗ To'g'ri raqam kiriting (masalan: 1, 2, 3).")
        return

    count = int(message.text)
    data = await state.get_data()
    await state.clear()

    async with AsyncSessionLocal() as session:
        order = await create_order(
            session=session,
            passenger_id=message.from_user.id,
            from_location=data["from_location"],
            to_location=data["to_location"],
            passenger_phone=data["phone"],
            passenger_count=count,
        )

    summary = (
        f"📋 <b>Buyurtma ma'lumotlari:</b>\n\n"
        f"📍 Qayerdan: {data['from_location']}\n"
        f"📍 Qayerga: {data['to_location']}\n"
        f"📱 Telefon: {data['phone']}\n"
        f"👥 Yo'lovchilar: {count} kishi\n\n"
        f"Tasdiqlaysizmi?"
    )
    await message.answer(
        summary,
        reply_markup=confirm_order_keyboard(order.id),
        parse_mode="HTML",
    )


@router.message(F.text == "🔙 Bosh menyu")
async def back_to_main_passenger(message: Message, user_role: str | None) -> None:
    if user_role != "passenger":
        return
    await message.answer("🧍 Yo'lovchi menyusi:", reply_markup=passenger_menu_keyboard())


# ─────────────────────────────────────────────
# BUYURTMANI TASDIQLASH
# ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("confirm_order:"))
async def confirm_order_callback(callback: CallbackQuery, bot: Bot) -> None:
    order_id = int(callback.data.split(":")[1])
    await callback.answer()

    async with AsyncSessionLocal() as session:
        order = await get_order(session, order_id)

    if not order or order.passenger_id != callback.from_user.id:
        await callback.message.edit_text("❌ Buyurtma topilmadi.")
        return

    await callback.message.edit_text("✅ Buyurtmangiz yuborildi! Haydovchi qidirilmoqda...")

    await _broadcast_order(bot=bot, order=order)


async def _broadcast_order(bot: Bot, order) -> None:
    """
    Buyurtmani tarqatish:
    - ORDERS_CHANNEL_ID → admin hisobot (to'liq ma'lumot)
    - Barcha tasdiqlangan haydovchilarga SHAXSAN (kontakt yashirin)
    """
    # Admin hisobot kanaliga
    try:
        await bot.send_message(
            chat_id=ORDERS_CHANNEL_ID,
            text=(
                f"🆕 <b>YANGI BUYURTMA #{order.id}</b>\n\n"
                f"📍 Qayerdan: {order.from_location}\n"
                f"📍 Qayerga: {order.to_location}\n"
                f"👥 {order.passenger_count} kishi\n"
                f"📱 Telefon: <code>{order.passenger_phone}</code>\n"
                f"🆔 Yo'lovchi ID: <code>{order.passenger_id}</code>"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Hisobot kanaliga yuborishda xato: {e}")

    # Haydovchilarga shaxsan — kontakt ko'rsatilmaydi
    driver_text = (
        f"🆕 <b>YANGI BUYURTMA #{order.id}</b>\n\n"
        f"📍 Qayerdan: {order.from_location}\n"
        f"📍 Qayerga: {order.to_location}\n"
        f"👥 {order.passenger_count} kishi"
    )

    async with AsyncSessionLocal() as session:
        drivers = await get_all_approved_drivers(session)

    sent = 0
    for driver in drivers:
        try:
            await bot.send_message(
                chat_id=driver.user_id,
                text=driver_text,
                reply_markup=order_action_keyboard(order.id),
                parse_mode="HTML",
            )
            sent += 1
        except Exception as e:
            logger.warning(f"Haydovchi {driver.user_id}: {e}")

    logger.info(f"Buyurtma #{order.id} → {sent} haydovchiga yuborildi.")


# ─────────────────────────────────────────────
# BUYURTMANI BEKOR QILISH
# ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("cancel_order:"))
async def cancel_order_callback(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[1])
    await callback.answer()

    async with AsyncSessionLocal() as session:
        success, reason = await cancel_order(
            session=session,
            order_id=order_id,
            passenger_id=callback.from_user.id,
        )

    if success:
        await callback.message.edit_text("✅ Buyurtmangiz bekor qilindi.")
    elif reason == "already_claimed":
        await callback.message.edit_text(
            "⚠️ Haydovchi allaqachon qabul qilgan — bekor qilib bo'lmaydi.\n"
            "Haydovchi bilan to'g'ridan-to'g'ri bog'laning."
        )
    elif reason == "already_cancelled":
        await callback.message.edit_text("ℹ️ Buyurtma allaqachon bekor qilingan.")
    else:
        await callback.message.edit_text("❌ Xatolik yuz berdi.")

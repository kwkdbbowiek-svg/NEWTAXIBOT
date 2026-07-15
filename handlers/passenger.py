"""
Yo'lovchi handlerlari.
"""
import asyncio
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
    get_all_approved_driver_ids,
)
from keyboards.common import cancel_keyboard
from keyboards.passenger import (
    passenger_menu_keyboard,
    confirm_order_keyboard,
    route_keyboard,
    passenger_count_keyboard,
)
from keyboards.driver import order_action_keyboard
from states.passenger_states import OrderCreation

logger = logging.getLogger(__name__)
router = Router()

# Yo'nalish → settings key xaritasi
ROUTE_KEYS = {
    "🚕 Toshkentdan → Bekobodga": "price_tashkent_bekobod",
    "🚕 Bekoboddan → Toshkentga": "price_bekobod_tashkent",
}

COUNT_BUTTONS = {
    "1️⃣ 1 ta": 1,
    "2️⃣ 2 ta": 2,
    "3️⃣ 3 ta": 3,
    "4️⃣ 4 ta": 4,
}


class NotAdmin(Filter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id != ADMIN_ID


router.message.filter(NotAdmin())


# ─────────────────────────────────────────────
# YO'LOVCHI SIFATIDA KIRISH
# ─────────────────────────────────────────────

@router.message(F.text == "🧍 Yo'lovchi")
async def passenger_entry(message: Message, user_role: str | None) -> None:
    if user_role == "driver":
        await message.answer("❌ Siz haydovchi sifatida ro'yxatdansiz.")
        return
    async with AsyncSessionLocal() as session:
        await set_user_role(session, message.from_user.id, UserRole.PASSENGER)
    await message.answer("🧍 Yo'lovchi menyusi:", reply_markup=passenger_menu_keyboard())


# ─────────────────────────────────────────────
# BUYURTMA BERISH
# ─────────────────────────────────────────────

@router.message(F.text == "📦 Buyurtma berish")
async def start_order(message: Message, state: FSMContext, user_role: str | None) -> None:
    if user_role != "passenger":
        return
    await message.answer(
        "🚕 <b>Qayerdan qayerga borishingizni tanlang:</b>",
        reply_markup=route_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(OrderCreation.route)


@router.message(OrderCreation.route, F.text)
async def order_route(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=passenger_menu_keyboard())
        return

    if message.text not in ROUTE_KEYS:
        await message.answer(
            "Iltimos, quyidagi tugmalardan birini tanlang! ⬇️",
            reply_markup=route_keyboard(),
        )
        return

    await state.update_data(route=message.text.strip())
    await message.answer(
        "📱 Telefon raqamingizni kiriting:\n(Masalan: +998901234567)",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(OrderCreation.phone)


@router.message(OrderCreation.phone, F.text)
async def order_phone(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=passenger_menu_keyboard())
        return

    phone = message.text.strip()
    if len(phone) < 7:
        await message.answer("❗ To'g'ri telefon raqam kiriting (masalan: +998901234567).")
        return

    await state.update_data(phone=phone)
    await message.answer(
        "👥 <b>Necha kishi yoki pochta?</b>\nTanlang:",
        reply_markup=passenger_count_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(OrderCreation.passenger_count)


@router.message(OrderCreation.passenger_count, F.text)
async def order_passenger_count(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=passenger_menu_keyboard())
        return

    if message.text == "📮 Pochta":
        await state.update_data(passenger_count=0, is_cargo=True)
        await message.answer(
            "📮 <b>Pochtaning tavsifini yozing:</b>\n"
            "(Nima yuboriladi, og'irligi, o'lchami va h.k.)",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        await state.set_state(OrderCreation.cargo_description)
        return

    if message.text not in COUNT_BUTTONS:
        await message.answer(
            "Iltimos, quyidagi tugmalardan birini tanlang! ⬇️",
            reply_markup=passenger_count_keyboard(),
        )
        return

    count = COUNT_BUTTONS[message.text]
    await _finish_order(message, state, count=count, cargo=None)


@router.message(OrderCreation.cargo_description, F.text)
async def order_cargo_description(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=passenger_menu_keyboard())
        return

    cargo = message.text.strip()
    if not cargo:
        await message.answer("❗ Tavsif bo'sh bo'lmasin, iltimos qayta yozing.")
        return

    await _finish_order(message, state, count=0, cargo=cargo)


async def _finish_order(
    message: Message,
    state: FSMContext,
    count: int,
    cargo: str | None,
) -> None:
    data = await state.get_data()
    await state.clear()

    route = data["route"]           # "🚌 Toshkent → Bekobod"
    phone = data["phone"]
    route_key = ROUTE_KEYS[route]   # "price_tashkent_bekobod"

    # Yo'lkira narxini bazadan olish
    async with AsyncSessionLocal() as session:
        price = await get_route_price(session, route_key)

    # Yo'nalishdan qayerdan/qayerga ajratamiz
    parts = route.replace("🚌 ", "").split(" → ")
    from_loc = parts[0].strip()
    to_loc = parts[1].strip()

    if cargo:
        count_label = f"📮 Pochta: {cargo}"
        passenger_count_db = 0
    else:
        count_label = f"👥 {count} kishi"
        passenger_count_db = count

    # Yo'lkira qatori — har doim "kelishuv asosida"
    price_label = "💵 Yo'lkira: <b>Kelishuv asosida</b>"

    async with AsyncSessionLocal() as session:
        order = await create_order(
            session=session,
            passenger_id=message.from_user.id,
            from_location=from_loc,
            to_location=to_loc,
            passenger_phone=phone,
            passenger_count=passenger_count_db,
            cargo_description=cargo,
        )

    summary = (
        f"📋 <b>Buyurtma ma'lumotlari:</b>\n\n"
        f"🚌 Yo'nalish: {route.replace('🚌 ', '')}\n"
        f"📱 Telefon: {phone}\n"
        f"{count_label}\n"
        f"{price_label}\n\n"
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
    asyncio.create_task(_broadcast_order(bot=bot, order=order))


async def _broadcast_order(bot: Bot, order) -> None:
    if order.cargo_description:
        count_line = f"📮 Pochta: {order.cargo_description}"
    else:
        count_line = f"👥 {order.passenger_count} kishi"

    # Yo'lkira — kelishuv asosida
    route_label = f"{order.from_location} → {order.to_location}"
    price_line = "\n💵 Yo'lkira: Kelishuv asosida"

    # Admin kanaliga
    try:
        await bot.send_message(
            chat_id=ORDERS_CHANNEL_ID,
            text=(
                f"🆕 <b>YANGI BUYURTMA #{order.id}</b>\n\n"
                f"🚌 {route_label}\n"
                f"{count_line}{price_line}\n"
                f"📱 Telefon: <code>{order.passenger_phone}</code>\n"
                f"🆔 Yo'lovchi ID: <code>{order.passenger_id}</code>"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Admin kanaliga yuborishda xato: {e}")

    # Haydovchilarga
    async with AsyncSessionLocal() as session:
        driver_ids = await get_all_approved_driver_ids(session)

    driver_text = (
        f"🆕 <b>YANGI BUYURTMA #{order.id}</b>\n\n"
        f"🚌 {route_label}\n"
        f"{count_line}{price_line}"
    )

    sent = 0
    failed = 0
    for i, driver_id in enumerate(driver_ids):
        try:
            await bot.send_message(
                chat_id=driver_id,
                text=driver_text,
                reply_markup=order_action_keyboard(order.id),
                parse_mode="HTML",
            )
            sent += 1
        except Exception as e:
            logger.warning(f"Haydovchi {driver_id}: {e}")
            failed += 1

        if (i + 1) % 25 == 0:
            await asyncio.sleep(1.0)

    logger.info(f"Buyurtma #{order.id} → {sent} haydovchiga yuborildi, {failed} xato.")


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

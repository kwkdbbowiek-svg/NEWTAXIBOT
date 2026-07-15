"""
Admin handlerlari — FAQAT ADMIN_ID uchun ishlaydi.
Boshqa foydalanuvchilar bu handlerlarga kirа olmaydi.
"""
import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import ADMIN_ID, DRIVERS_CHANNEL_ID
from database.engine import AsyncSessionLocal
from database.models import DriverStatus
from database.queries import (
    approve_driver,
    reject_driver,
    top_up_balance,
    deduct_balance,
    get_commission,
    set_setting,
    get_statistics,
    get_all_users_ids,
    get_driver_by_user_id,
)
from keyboards.admin import admin_menu_keyboard, driver_approval_keyboard
from keyboards.common import cancel_keyboard
from states.admin_states import AdminTopUp, AdminDeduct, AdminCommission, AdminBroadcast

logger = logging.getLogger(__name__)
router = Router()


# ─── Faqat admin kirsin ───
class AdminOnly(Filter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return event.from_user.id == ADMIN_ID


router.message.filter(AdminOnly())
# callback_query larga global filter qo'ymaymiz —
# har bir callback handler ichida alohida tekshiriladi


# ─────────────────────────────────────────────
# ADMIN PANELI
# ─────────────────────────────────────────────

@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with AsyncSessionLocal() as session:
        commission = await get_commission(session)

    await message.answer(
        f"⚙️ <b>Admin panel</b>\n\nJoriy komissiya: {commission:,.0f} so'm / yo'lovchi",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────
# HAYDOVCHINI TASDIQLASH / RAD ETISH
# ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("approve_driver:"))
async def approve_driver_callback(callback: CallbackQuery, bot: Bot) -> None:
    driver_user_id = int(callback.data.split(":")[1])
    await callback.answer()

    async with AsyncSessionLocal() as session:
        driver = await approve_driver(session, driver_user_id)

    if not driver:
        await callback.message.answer("❌ Haydovchi topilmadi.")
        return

    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>TASDIQLANDI</b>",
        parse_mode="HTML",
    )

    # Haydovchiga xabar
    try:
        await bot.send_message(
            chat_id=driver_user_id,
            text=(
                "🎉 <b>Tabriklaymiz!</b>\n\n"
                "Admin sizni tasdiqladi. Endi buyurtmalarni olishingiz mumkin.\n"
                "Davom etish uchun /start bosing."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Haydovchiga xabar yuborilmadi: {e}")

    # Admin hisobot kanaliga
    try:
        await bot.send_message(
            chat_id=DRIVERS_CHANNEL_ID,
            text=(
                f"✅ <b>Yangi haydovchi tasdiqlandi</b>\n\n"
                f"👤 {driver.full_name}\n"
                f"📱 {driver.phone}\n"
                f"🚗 {driver.car_model} | {driver.car_number}\n"
                f"🆔 <code>{driver_user_id}</code>"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Hisobot kanaliga yuborilmadi: {e}")


@router.callback_query(F.data.startswith("reject_driver:"))
async def reject_driver_callback(callback: CallbackQuery, bot: Bot) -> None:
    driver_user_id = int(callback.data.split(":")[1])
    await callback.answer()

    async with AsyncSessionLocal() as session:
        await reject_driver(session, driver_user_id)

    await callback.message.edit_text(
        callback.message.text + "\n\n❌ <b>RAD ETILDI</b>",
        parse_mode="HTML",
    )

    try:
        await bot.send_message(
            chat_id=driver_user_id,
            text="❌ Arizangiz rad etildi. Admin bilan bog'laning.",
        )
    except Exception as e:
        logger.warning(f"Haydovchiga rad xabari yuborilmadi: {e}")


# ─────────────────────────────────────────────
# BALANSNI TO'LDIRISH
# ─────────────────────────────────────────────

@router.message(F.text == "➕ Balansni to'ldirish")
async def admin_top_up_start(message: Message, state: FSMContext) -> None:
    await message.answer(
        "👤 Haydovchining Telegram ID sini kiriting:",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(AdminTopUp.user_id)


@router.message(AdminTopUp.user_id, F.text)
async def admin_top_up_user_id(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard())
        return

    if not message.text.isdigit():
        await message.answer("❗ Faqat raqam kiriting!")
        return

    await state.update_data(target_user_id=int(message.text))
    await message.answer("💵 To'ldiriladigan summani kiriting (so'mda):")
    await state.set_state(AdminTopUp.amount)


@router.message(AdminTopUp.amount, F.text)
async def admin_top_up_amount(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard())
        return

    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❗ To'g'ri summa kiriting (masalan: 10.50)!")
        return

    data = await state.get_data()
    await state.clear()

    async with AsyncSessionLocal() as session:
        driver = await top_up_balance(session, data["target_user_id"], amount)

    if not driver:
        await message.answer("❌ Bu ID li haydovchi topilmadi.", reply_markup=admin_menu_keyboard())
        return

    await message.answer(
        f"✅ <b>Muvaffaqiyatli!</b>\n\n"
        f"👤 {driver.full_name}\n"
        f"➕ To'ldirildi: {amount:,.0f} so'm\n"
        f"💰 Yangi balans: {driver.balance:,.0f} so'm",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────
# BALANSDAN AYIRISH
# ─────────────────────────────────────────────

@router.message(F.text == "➖ Balansni ayirish")
async def admin_deduct_start(message: Message, state: FSMContext) -> None:
    await message.answer(
        "👤 Haydovchining Telegram ID sini kiriting:",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(AdminDeduct.user_id)


@router.message(AdminDeduct.user_id, F.text)
async def admin_deduct_user_id(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard())
        return

    if not message.text.isdigit():
        await message.answer("❗ Faqat raqam kiriting!")
        return

    await state.update_data(target_user_id=int(message.text))
    await message.answer("💵 Ayiriladigan summani kiriting (so'mda):")
    await state.set_state(AdminDeduct.amount)


@router.message(AdminDeduct.amount, F.text)
async def admin_deduct_amount(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard())
        return

    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❗ To'g'ri summa kiriting!")
        return

    data = await state.get_data()
    await state.clear()

    async with AsyncSessionLocal() as session:
        driver = await deduct_balance(session, data["target_user_id"], amount)

    if not driver:
        await message.answer("❌ Bu ID li haydovchi topilmadi.", reply_markup=admin_menu_keyboard())
        return

    await message.answer(
        f"✅ <b>Muvaffaqiyatli!</b>\n\n"
        f"👤 {driver.full_name}\n"
        f"➖ Ayirildi: {amount:,.0f} so'm\n"
        f"💰 Yangi balans: {driver.balance:,.0f} so'm",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────
# KOMISSIYA TAHRIRLASH
# ─────────────────────────────────────────────

@router.message(F.text == "💱 Komissiyani tahrirlash")
async def admin_commission_start(message: Message, state: FSMContext) -> None:
    async with AsyncSessionLocal() as session:
        current = await get_commission(session)

    await message.answer(
        f"💱 Joriy komissiya: <b>{current:,.0f} so'm</b> / yo'lovchi\n\n"
        f"Yangi qiymatni kiriting (so'mda):",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(AdminCommission.new_value)


@router.message(AdminCommission.new_value, F.text)
async def admin_commission_set(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard())
        return

    try:
        value = float(message.text.replace(",", "."))
        if value < 0:
            raise ValueError
    except ValueError:
        await message.answer("❗ To'g'ri raqam kiriting (masalan: 1.5)!")
        return

    await state.clear()

    async with AsyncSessionLocal() as session:
        await set_setting(session, "commission_per_passenger", str(value))

    await message.answer(
        f"✅ Komissiya: <b>{value:,.0f} so'm</b> / yo'lovchi",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────
# STATISTIKA
# ─────────────────────────────────────────────

@router.message(F.text == "📊 Statistika")
async def admin_statistics(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        stats = await get_statistics(session)

    await message.answer(
        f"📊 <b>Statistika:</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{stats['total_users']}</b>\n"
        f"🚕 Tasdiqlangan haydovchilar: <b>{stats['total_drivers']}</b>\n"
        f"📦 Bajarilgan zakazlar: <b>{stats['total_orders']}</b>",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────
# REKLAMA YUBORISH
# ─────────────────────────────────────────────

@router.message(F.text == "📣 Reklama yuborish")
async def admin_broadcast_start(message: Message, state: FSMContext) -> None:
    await message.answer(
        "📣 Yuboriladigan xabarni yuboring (matn, rasm, video, audio):",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(AdminBroadcast.message)


@router.message(AdminBroadcast.message)
async def admin_broadcast_send(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=admin_menu_keyboard())
        return

    await state.clear()

    async with AsyncSessionLocal() as session:
        user_ids = await get_all_users_ids(session)

    # Admin o'zini o'zi chiqarib tashlaydi
    user_ids = [uid for uid in user_ids if uid != ADMIN_ID]

    await message.answer(f"⏳ Yuborilmoqda... ({len(user_ids)} ta foydalanuvchi)")

    ok, fail = 0, 0
    for i, user_id in enumerate(user_ids):
        try:
            await _send_broadcast(bot, message, user_id)
            ok += 1
        except Exception as e:
            logger.warning(f"User {user_id}: {e}")
            fail += 1

        # Telegram rate limit: 30 msg/sek — har 25 tadan keyin 1 sek pause
        if (i + 1) % 25 == 0:
            await asyncio.sleep(1.0)

    await message.answer(
        f"✅ <b>Reklama yuborildi!</b>\n\n✔️ {ok} | ❌ {fail}",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )


async def _send_broadcast(bot: Bot, message: Message, chat_id: int) -> None:
    if message.photo:
        await bot.send_photo(chat_id, message.photo[-1].file_id,
                             caption=message.caption or "", parse_mode="HTML")
    elif message.video:
        await bot.send_video(chat_id, message.video.file_id,
                             caption=message.caption or "", parse_mode="HTML")
    elif message.audio:
        await bot.send_audio(chat_id, message.audio.file_id,
                             caption=message.caption or "", parse_mode="HTML")
    elif message.voice:
        await bot.send_voice(chat_id, message.voice.file_id)
    elif message.text:
        await bot.send_message(chat_id, message.text, parse_mode="HTML")

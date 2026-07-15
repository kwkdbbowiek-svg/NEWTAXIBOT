"""
Haydovchi handlerlari.
Faqat rol="driver" yoki rol=None (yangi) foydalanuvchilarga ishlaydi.
Admin bu handlerlarga kirmaydi.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import ADMIN_ID, DRIVERS_CHANNEL_ID, ADMIN_USERNAME
from database.engine import AsyncSessionLocal
from database.models import UserRole, DriverStatus
from database.queries import (
    get_driver_by_user_id,
    create_driver,
    set_user_role,
    claim_order_atomic,
    get_commission,
    get_order,
    get_user,
)
from keyboards.common import (
    role_select_keyboard,
    share_contact_keyboard,
    confirm_keyboard,
    cancel_keyboard,
)
from keyboards.admin import driver_approval_keyboard
from keyboards.driver import driver_menu_keyboard, order_action_keyboard
from states.driver_states import DriverRegistration

logger = logging.getLogger(__name__)
router = Router()


# ─── Admin ni bu routerdan butunlay chiqarib yuborish ───
class NotAdmin(Filter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id != ADMIN_ID


router.message.filter(NotAdmin())


# ─────────────────────────────────────────────
# HAYDOVCHI SIFATIDA KIRISH
# ─────────────────────────────────────────────

@router.message(F.text == "🚕 Haydovchi")
async def driver_entry(message: Message, state: FSMContext, user_role: str | None) -> None:
    # Agar bu foydalanuvchi yo'lovchi sifatida ro'yxatdan o'tgan bo'lsa — yo'q
    if user_role == "passenger":
        await message.answer("❌ Siz yo'lovchi sifatida ro'yxatdansiz.")
        return

    async with AsyncSessionLocal() as session:
        driver = await get_driver_by_user_id(session, message.from_user.id)

    if driver:
        if driver.status == DriverStatus.APPROVED:
            await message.answer("✅ Xush kelibsiz, haydovchi!", reply_markup=driver_menu_keyboard())
        elif driver.status == DriverStatus.PENDING:
            await message.answer(
                "⏳ Ma'lumotlaringiz admin tomonidan ko'rib chiqilmoqda.\n"
                "Natija haqida xabardor qilinasiz.",
                reply_markup=driver_menu_keyboard(),
            )
        else:
            await message.answer(
                "❌ Arizangiz rad etilgan. Admin bilan bog'laning.",
                reply_markup=role_select_keyboard(),
            )
        return

    # Yangi haydovchi — ro'yxatdan o'tish
    await message.answer(
        "📝 Ro'yxatdan o'tish uchun ismingizni kiriting:\n(Ism va Familiya)",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(DriverRegistration.full_name)


# ─────────────────────────────────────────────
# RO'YXATDAN O'TISH — FSM BOSQICHLARI
# ─────────────────────────────────────────────

@router.message(DriverRegistration.full_name, F.text)
async def driver_full_name(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=role_select_keyboard())
        return

    await state.update_data(full_name=message.text.strip())
    await message.answer(
        "📱 Telefon raqamingizni kiriting:\n(Masalan: +998901234567)",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(DriverRegistration.phone)


@router.message(DriverRegistration.phone, F.text)
async def driver_phone_contact(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=role_select_keyboard())
        return

    phone = message.text.strip()
    if len(phone) < 7:
        await message.answer("❗ To'g'ri telefon raqam kiriting (masalan: +998901234567).")
        return

    await state.update_data(phone=phone)
    await message.answer(
        "🚗 Mashina rusumini kiriting (masalan: Chevrolet Cobalt):",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(DriverRegistration.car_model)


@router.message(DriverRegistration.car_model, F.text)
async def driver_car_model(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=role_select_keyboard())
        return

    await state.update_data(car_model=message.text.strip())
    await message.answer(
        "🔢 Mashina davlat raqamini kiriting (masalan: 01 A 777 AA):",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(DriverRegistration.car_number)


@router.message(DriverRegistration.car_number, F.text)
async def driver_car_number(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=role_select_keyboard())
        return

    await state.update_data(car_number=message.text.strip().upper())
    data = await state.get_data()

    summary = (
        f"📋 <b>Ma'lumotlaringiz:</b>\n\n"
        f"👤 Ism: {data['full_name']}\n"
        f"📱 Telefon: {data['phone']}\n"
        f"🚗 Mashina: {data['car_model']}\n"
        f"🔢 Raqam: {data['car_number']}\n\n"
        f"Ma'lumotlar to'g'rimi?"
    )
    await message.answer(summary, reply_markup=confirm_keyboard(), parse_mode="HTML")
    await state.set_state(DriverRegistration.confirm)


@router.message(DriverRegistration.confirm, F.text == "✅ Ha, to'g'ri")
async def driver_confirm_yes(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()

    async with AsyncSessionLocal() as session:
        await set_user_role(session, message.from_user.id, UserRole.DRIVER)
        driver = await create_driver(
            session=session,
            user_id=message.from_user.id,
            full_name=data["full_name"],
            phone=data["phone"],
            car_model=data["car_model"],
            car_number=data["car_number"],
        )

    # Adminga tasdiqlash so'rovi
    admin_text = (
        f"🆕 <b>Yangi haydovchi ro'yxatdan o'tdi!</b>\n\n"
        f"👤 Ism: {data['full_name']}\n"
        f"📱 Telefon: {data['phone']}\n"
        f"🚗 Mashina: {data['car_model']}\n"
        f"🔢 Raqam: {data['car_number']}\n"
        f"🆔 Telegram ID: <code>{message.from_user.id}</code>\n"
        f"👤 Username: @{message.from_user.username or 'yoq'}"
    )
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=driver_approval_keyboard(message.from_user.id),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Adminga xabar yuborishda xato: {e}")

    await message.answer(
        "✅ Ma'lumotlaringiz yuborildi!\n"
        "⏳ Admin tasdiqlashini kuting. Xabardor qilinasiz.",
        reply_markup=driver_menu_keyboard(),
    )


@router.message(DriverRegistration.confirm, F.text == "❌ Yo'q, qayta")
async def driver_confirm_no(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🔄 Qayta boshlash. Ismingizni kiriting:",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(DriverRegistration.full_name)


# ─────────────────────────────────────────────
# HAYDOVCHI MENYUSI — faqat rol="driver" uchun
# ─────────────────────────────────────────────

@router.message(F.text == "💰 Balansni ko'rish")
async def show_balance(message: Message, user_role: str | None) -> None:
    if user_role != "driver":
        return  # Boshqa rollar uchun javob yo'q

    async with AsyncSessionLocal() as session:
        driver = await get_driver_by_user_id(session, message.from_user.id)

    if not driver or driver.status != DriverStatus.APPROVED:
        await message.answer("❌ Haydovchi sifatida tasdiqlanmagansiz.")
        return

    await message.answer(
        f"💰 <b>Balansingiz:</b> {driver.balance:,.0f} so'm",
        parse_mode="HTML",
    )


@router.message(F.text == "💳 Balansni to'ldirish")
async def request_top_up(message: Message, user_role: str | None) -> None:
    if user_role != "driver":
        return

    await message.answer(
        f"💳 Balansni to'ldirish uchun admin bilan bog'laning:\n"
        f"👤 @{ADMIN_USERNAME}",
    )


@router.message(F.text == "🔙 Bosh menyu")
async def back_to_main_driver(message: Message, user_role: str | None) -> None:
    if user_role != "driver":
        return
    from keyboards.common import role_select_keyboard
    # Haydovchi uchun "bosh menyu" = haydovchi menyusi (rol o'zgarmaydi)
    async with AsyncSessionLocal() as session:
        driver = await get_driver_by_user_id(session, message.from_user.id)
    if driver:
        await message.answer("🚕 Haydovchi menyusi:", reply_markup=driver_menu_keyboard())
    else:
        await message.answer("Asosiy menyu:", reply_markup=role_select_keyboard())


# ─────────────────────────────────────────────
# BUYURTMANI OLISH — XAVFSIZ TRANZAKSIYA
# ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("take_order:"))
async def take_order(callback: CallbackQuery, bot: Bot) -> None:
    order_id = int(callback.data.split(":")[1])
    driver_user_id = callback.from_user.id

    await callback.answer()

    async with AsyncSessionLocal() as session:
        commission_per_person = await get_commission(session)
        order = await get_order(session, order_id)

    if not order:
        await callback.message.answer("❌ Buyurtma topilmadi.")
        return

    total_commission = round(order.passenger_count * commission_per_person)

    # claim_order_atomic o'zi mustaqil session ochadi
    success, reason = await claim_order_atomic(
        order_id=order_id,
        driver_user_id=driver_user_id,
        commission=total_commission,
    )

    if not success:
        error_texts = {
            "already_claimed": "⚠️ Bu buyurtmani boshqa haydovchi allaqachon oldi!",
            "insufficient_balance": (
                f"❌ Balansingiz yetarli emas!\n"
                f"Kerakli summa: {total_commission:,.0f} so'm\n"
                f"To'ldirish uchun: @{ADMIN_USERNAME}"
            ),
            "driver_not_approved": "❌ Hisobingiz hali tasdiqlanmagan.",
            "driver_not_found": "❌ Haydovchi topilmadi.",
            "order_not_found": "❌ Buyurtma topilmadi.",
        }
        await callback.message.answer(error_texts.get(reason, "❌ Xatolik yuz berdi."))
        return

    # Yangilangan ma'lumotlarni yuklab olamiz
    async with AsyncSessionLocal() as session:
        order = await get_order(session, order_id)
        driver = await get_driver_by_user_id(session, driver_user_id)
        passenger = await get_user(session, order.passenger_id)

    # G'olib haydovchiga — yo'lovchi kontakti ochiladi
    await callback.message.answer(
        f"🎉 <b>Buyurtma olindi!</b>\n\n"
        f"📍 Qayerdan: {order.from_location}\n"
        f"📍 Qayerga: {order.to_location}\n"
        f"👥 Yo'lovchilar: {order.passenger_count} kishi\n\n"
        f"📱 Telefon: <code>{order.passenger_phone}</code>\n"
        f"👤 Username: @{passenger.username or 'yoq'}\n\n"
        f"💸 Yechildi: {total_commission:,.0f} so'm | 💰 Qoldi: {driver.balance:,.0f} so'm",
        parse_mode="HTML",
    )

    # Yo'lovchiga haydovchi ma'lumotlari
    try:
        await bot.send_message(
            chat_id=order.passenger_id,
            text=(
                f"🚕 <b>Haydovchi topildi!</b>\n\n"
                f"👤 Ism: {driver.full_name}\n"
                f"📱 Telefon: <code>{driver.phone}</code>\n"
                f"🚗 {driver.car_model} | 🔢 {driver.car_number}\n\n"
                f"Yaxshi sayohat! 🙂"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Yo'lovchiga xabar yuborilmadi: {e}")

    # Admin hisobot kanaliga
    try:
        await bot.send_message(
            chat_id=DRIVERS_CHANNEL_ID,
            text=(
                f"✅ <b>BUYURTMA #{order.id} OLINDI</b>\n\n"
                f"📍 {order.from_location} → {order.to_location}\n"
                f"👥 {order.passenger_count} kishi\n"
                f"🚕 {driver.full_name} | {driver.car_number}\n"
                f"💸 Komissiya: {total_commission:,.0f} so'm"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Hisobot kanaliga yuborilmadi: {e}")


@router.callback_query(F.data.startswith("driver_skip:"))
async def driver_skip_order(callback: CallbackQuery) -> None:
    await callback.answer("O'tkazib yuborildi.", show_alert=False)

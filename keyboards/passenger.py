from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


def passenger_menu_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📦 Buyurtma berish"))
    builder.row(KeyboardButton(text="🔙 Bosh menyu"))
    return builder.as_markup(resize_keyboard=True)


def location_keyboard() -> ReplyKeyboardMarkup:
    """Qayerdan / Qayerga tanlash uchun 2 ta tugma."""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="🏙 Shirin"),
        KeyboardButton(text="🏘 Bekobod"),
    )
    builder.row(KeyboardButton(text="❌ Bekor qilish"))
    return builder.as_markup(resize_keyboard=True)


def confirm_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Zakazni tasdiqlash",
            callback_data=f"confirm_order:{order_id}",
        ),
        InlineKeyboardButton(
            text="❌ Bekor qilish",
            callback_data=f"cancel_order:{order_id}",
        ),
    )
    return builder.as_markup()

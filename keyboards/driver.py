from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


def driver_menu_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="💰 Balansni ko'rish"))
    builder.row(KeyboardButton(text="💳 Balansni to'ldirish"))
    builder.row(KeyboardButton(text="🔙 Bosh menyu"))
    return builder.as_markup(resize_keyboard=True)


def order_action_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Haydovchiga buyurtma kelganda tugmalar."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Buyurtmani olish",
            callback_data=f"take_order:{order_id}",
        ),
        InlineKeyboardButton(
            text="❌ Bekor qilish",
            callback_data=f"driver_skip:{order_id}",
        ),
    )
    return builder.as_markup()

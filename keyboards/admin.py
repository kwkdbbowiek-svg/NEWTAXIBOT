from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="➕ Balansni to'ldirish"),
        KeyboardButton(text="➖ Balansni ayirish"),
    )
    builder.row(
        KeyboardButton(text="💱 Komissiyani tahrirlash"),
        KeyboardButton(text="📊 Statistika"),
    )
    builder.row(KeyboardButton(text="📣 Reklama yuborish"))
    return builder.as_markup(resize_keyboard=True)


def driver_approval_keyboard(driver_user_id: int) -> InlineKeyboardMarkup:
    """Admin panel: yangi haydovchini tasdiqlash yoki rad etish."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Tasdiqlash",
            callback_data=f"approve_driver:{driver_user_id}",
        ),
        InlineKeyboardButton(
            text="❌ Rad etish",
            callback_data=f"reject_driver:{driver_user_id}",
        ),
    )
    return builder.as_markup()

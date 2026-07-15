from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def role_select_keyboard() -> ReplyKeyboardMarkup:
    """Faqat yangi foydalanuvchilar uchun — rol tanlash."""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="🚕 Haydovchi"),
        KeyboardButton(text="🧍 Yo'lovchi"),
    )
    return builder.as_markup(resize_keyboard=True)


def confirm_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="✅ Ha, to'g'ri"),
        KeyboardButton(text="❌ Yo'q, qayta"),
    )
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def cancel_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="❌ Bekor qilish"))
    return builder.as_markup(resize_keyboard=True)

"""
Rol middleware — har bir xabarda foydalanuvchi rolini aniqlaydi
va handler larga `user_role` sifatida uzatadi.
"""
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from config import ADMIN_ID
from database.engine import AsyncSessionLocal
from database.queries import get_user
from database.models import UserRole


class RoleMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # user_id ni aniqlash
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        else:
            return await handler(event, data)

        # Admin har doim admin
        if user_id == ADMIN_ID:
            data["user_role"] = "admin"
            return await handler(event, data)

        # Bazadan rol o'qish
        async with AsyncSessionLocal() as session:
            user = await get_user(session, user_id)

        role = user.role.value if (user and user.role) else None
        data["user_role"] = role  # "driver", "passenger", None

        return await handler(event, data)

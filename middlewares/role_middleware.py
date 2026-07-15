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


class RoleMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, (Message, CallbackQuery)):
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

        if user and user.role:
            # PostgreSQL: VARCHAR bo'lsa str() — enum bo'lsa .value
            raw = str(user.role)
            if raw.lower() in ("driver", "userrole.driver"):
                role = "driver"
            elif raw.lower() in ("passenger", "userrole.passenger"):
                role = "passenger"
            else:
                # enum.value usuli bilan urinib ko'ramiz
                try:
                    role = user.role.value
                except AttributeError:
                    role = raw.lower()
        else:
            role = None

        data["user_role"] = role  # "driver", "passenger", None
        return await handler(event, data)

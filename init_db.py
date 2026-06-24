"""
Database initialization — creates tables and seeds default data.
Run once on first startup.
"""

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base, engine, async_session_factory
from app.models import User, Setting, Contractor
from app.utils import hash_password

DEFAULT_SETTINGS = [
    ("notification_days_before_1", "5", "Первое уведомление за N дней"),
    ("notification_days_before_2", "1", "Второе уведомление за N дней"),
    ("notification_on_due_date", "true", "Уведомление в день срока"),
    ("notification_overdue_daily", "true", "Ежедневные уведомления при просрочке"),
    ("notification_time", "09:00", "Время проверки уведомлений"),
    ("notification_timezone", "Europe/Moscow", "Часовой пояс"),
    ("notification_channel_telegram", "true", "Канал: Telegram"),
    ("notification_channel_web", "true", "Канал: Веб-интерфейс"),
    ("generation_day", "1", "День генерации платежей"),
    ("generation_time", "00:05", "Время генерации платежей"),
    ("generation_enabled", "true", "Авто-генерация включена"),
    ("ui_theme", "dark", "Тема интерфейса"),
    ("ui_date_format", "DD.MM.YYYY", "Формат даты"),
    ("ui_currency", "RUB", "Валюта"),
    ("ui_currency_symbol", "\u20bd", "Символ валюты"),
    ("ui_language", "ru", "Язык интерфейса"),
]


async def seed_data(session: AsyncSession):
    """Insert default users and settings if they don't exist."""
    for username, password, role in [
        ("admin", os.getenv("ADMIN_PASSWORD", "admin"), "admin"),
        ("user", os.getenv("USER_PASSWORD", "user"), "user"),
    ]:
        result = await session.execute(select(User).where(User.username == username))
        if not result.scalar_one_or_none():
            session.add(
                User(
                    username=username,
                    password_hash=hash_password(password),
                    role=role,
                )
            )

    for key, value, desc in DEFAULT_SETTINGS:
        result = await session.execute(select(Setting).where(Setting.key == key))
        if not result.scalar_one_or_none():
            session.add(Setting(key=key, value=value, description=desc))


async def main():
    """Create tables and seed default data."""
    print("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        await seed_data(session)
        await session.commit()

    print("Database initialized successfully.")


if __name__ == "__main__":
    asyncio.run(main())

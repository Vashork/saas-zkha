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

DEFAULT_CONTRACTORS = [
    ("Мосэнергосбыт", "мосэнергосбыт", "fixed", 3200, 10, "1001001001"),
    ("Мосводоканал", "мосводоканал", "fixed", 2800, 15, "2002002002"),
    ("Мосгаз", "мосгаз", "variable", None, 20, None),
    ("УК Наш Дом", "ук_наш_дом", "fixed", 4500, 25, None),
    ("Интернет Ростелеком", "интернет", "fixed", 750, 5, None),
]


async def seed_data(session: AsyncSession):
    """Insert default users, contractors, and settings if they don't exist."""
    from app.utils import generate_uuid

    # Default users
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

    # Default contractors
    for name, slug, ptype, fixed_amt, due_day, acct in DEFAULT_CONTRACTORS:
        result = await session.execute(select(Contractor).where(Contractor.slug == slug))
        if not result.scalar_one_or_none():
            session.add(
                Contractor(
                    id=generate_uuid(),
                    name=name,
                    slug=slug,
                    payment_type=ptype,
                    fixed_amount=fixed_amt,
                    due_day=due_day,
                    account_number=acct,
                    is_active=True,
                )
            )

    # Default settings
    for key, value, desc in DEFAULT_SETTINGS:
        result = await session.execute(select(Setting).where(Setting.key == key))
        if not result.scalar_one_or_none():
            session.add(Setting(key=key, value=value, description=desc))


async def main():
    """Create tables and seed default data."""
    # Ensure the data directory exists (volume mount may have wrong perms)
    data_dir = os.path.dirname(os.path.abspath("/app/data/zhkh.db"))
    os.makedirs(data_dir, exist_ok=True)
    print(f"Ensuring data directory exists: {data_dir}")

    print("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        await seed_data(session)
        await session.commit()

    print("Database initialized successfully.")


if __name__ == "__main__":
    asyncio.run(main())

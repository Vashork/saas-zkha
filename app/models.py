"""
SQLAlchemy 2.0 models for the zhkh-bot application.
"""

import uuid
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date, Numeric, ForeignKey, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    telegram_user_id = Column(Integer, unique=True, nullable=True)
    role = Column(String, nullable=False, default="user")
    page_permissions = Column(String, nullable=True)  # comma-separated page slugs
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<User(username={self.username}, role={self.role})>"


class Contractor(Base):
    __tablename__ = "contractors"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    payment_type = Column(String, nullable=False)  # 'fixed' | 'variable'
    fixed_amount = Column(Numeric(10, 2), nullable=True)
    due_day = Column(Integer, nullable=False)
    account_number = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    payments = relationship("Payment", back_populates="contractor")

    __table_args__ = (
        CheckConstraint("payment_type IN ('fixed', 'variable')", name="ck_payment_type"),
        CheckConstraint("due_day BETWEEN 1 AND 31", name="ck_due_day"),
    )

    def __repr__(self):
        return f"<Contractor(name={self.name}, slug={self.slug})>"


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True)
    contractor_id = Column(String, ForeignKey("contractors.id"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    amount = Column(Numeric(10, 2), nullable=True)
    paid_amount = Column(Numeric(10, 2), nullable=True)
    due_date = Column(Date, nullable=False)
    paid_date = Column(Date, nullable=True)
    status = Column(String, nullable=False, default="pending")
    receipt_file = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    contractor = relationship("Contractor", back_populates="payments")

    __table_args__ = (
        UniqueConstraint("contractor_id", "year", "month", name="uq_contractor_period"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_month"),
        CheckConstraint("status IN ('pending', 'paid', 'overdue')", name="ck_status"),
    )

    def __repr__(self):
        return f"<Payment(contractor_id={self.contractor_id}, {self.year}-{self.month}, status={self.status})>"


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Setting(key={self.key}, value={self.value})>"


class BackupHistory(Base):
    __tablename__ = "backup_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, server_default=func.now())
    mode = Column(String, nullable=False)  # 'A' | 'B' | 'C'
    backup_type = Column(String, nullable=False)  # 'full' | 'incr' | 'bundle'
    size_bytes = Column(Integer, nullable=False)
    storage = Column(String, nullable=False)  # 'synology' | 'local'
    status = Column(String, nullable=False)  # 'success' | 'failed'
    error_message = Column(Text, nullable=True)
    file_path = Column(String, nullable=True)

    __table_args__ = (
        CheckConstraint("mode IN ('A', 'B', 'C')", name="ck_backup_mode"),
        CheckConstraint("backup_type IN ('full', 'incr', 'bundle')", name="ck_backup_type"),
        CheckConstraint("storage IN ('synology', 'local')", name="ck_storage"),
        CheckConstraint("status IN ('success', 'failed')", name="ck_backup_status"),
    )

    def __repr__(self):
        return f"<BackupHistory(mode={self.mode}, status={self.status})>"

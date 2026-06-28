"""
SQLAlchemy 2.0 models for the zhkh-bot application.
"""

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
    transactions = relationship(
        "PaymentTransaction",
        back_populates="payment",
        cascade="all, delete-orphan",
        order_by="PaymentTransaction.paid_date",
    )

    __table_args__ = (
        UniqueConstraint("contractor_id", "year", "month", name="uq_contractor_period"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_month"),
        CheckConstraint("status IN ('pending', 'paid', 'overdue')", name="ck_status"),
    )

    def __repr__(self):
        return f"<Payment(contractor_id={self.contractor_id}, {self.year}-{self.month}, status={self.status})>"


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(String, primary_key=True)
    payment_id = Column(String, ForeignKey("payments.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    paid_date = Column(Date, nullable=False)
    receipt_file = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    payment = relationship("Payment", back_populates="transactions")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_transaction_amount_positive"),
    )

    def __repr__(self):
        return f"<PaymentTransaction(payment_id={self.payment_id}, amount={self.amount})>"


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


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, server_default=func.now())
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    actor_username = Column(String, nullable=True)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    client_ip = Column(String, nullable=True)

    actor = relationship("User")

    def __repr__(self):
        return f"<AuditLog(action={self.action}, entity_type={self.entity_type}, entity_id={self.entity_id})>"


class TelegramMessageLog(Base):
    __tablename__ = "telegram_message_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, server_default=func.now())
    telegram_user_id = Column(Integer, nullable=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    chat_id = Column(Integer, nullable=True)
    message_type = Column(String, nullable=False, default="message")
    text = Column(Text, nullable=True)
    is_allowed = Column(Boolean, nullable=False, default=False)
    is_admin = Column(Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"<TelegramMessageLog(telegram_user_id={self.telegram_user_id}, is_allowed={self.is_allowed})>"

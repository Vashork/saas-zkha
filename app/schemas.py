"""
Pydantic schemas for request/response validation.
"""

from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


# --- Contractor ---

class ContractorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=2, max_length=50)
    payment_type: str = Field(..., pattern="^(fixed|variable)$")
    fixed_amount: Optional[Decimal] = None
    due_day: int = Field(..., ge=1, le=31)
    account_number: Optional[str] = None
    description: Optional[str] = None


class ContractorUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    payment_type: Optional[str] = None
    fixed_amount: Optional[Decimal] = None
    due_day: Optional[int] = None
    account_number: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


# --- Payment ---

class PaymentCreate(BaseModel):
    contractor_id: str
    year: int
    month: int
    amount: Optional[Decimal] = None
    paid_amount: Optional[Decimal] = None
    due_date: date
    status: str = "pending"
    receipt_file: Optional[str] = None
    notes: Optional[str] = None


class PaymentUpdate(BaseModel):
    amount: Optional[Decimal] = None
    paid_amount: Optional[Decimal] = None
    paid_date: Optional[date] = None
    status: Optional[str] = None
    receipt_file: Optional[str] = None
    notes: Optional[str] = None


# --- User ---

class UserLogin(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4)
    role: str = Field(default="user", pattern="^(admin|user)$")
    telegram_user_id: Optional[int] = None

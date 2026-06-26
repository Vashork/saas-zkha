"""Compatibility patch for the legacy parent payment edit route.

The main payments module is large and this follow-up branch keeps the fix small:
replace only POST /payments/{payment_id}/edit so parent aggregate fields stay
consistent with child PaymentTransaction rows.
"""

import uuid
from datetime import date
from decimal import InvalidOperation

from fastapi import Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.database import get_db
from app.models import Payment, PaymentTransaction
from app.web.routes import payments as _payments
from app.web.template_engine import templates


async def edit_payment(
    payment_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    amount: str = Form(""),
    status: str = Form(""),
    paid_date_str: str = Form(""),
    receipt: UploadFile = File(None),
):
    current_user, redirect = await _payments._require_admin_user(request, db)
    if redirect:
        return redirect

    result = await db.execute(
        select(Payment)
        .options(joinedload(Payment.contractor), selectinload(Payment.transactions))
        .where(Payment.id == payment_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        return RedirectResponse(url="/payments", status_code=303)

    old_total = _payments._transaction_total(payment)

    if amount.strip():
        try:
            payment.amount = _payments._parse_amount(amount)
        except (InvalidOperation, ValueError):
            ctx = await _payments._page_context(
                request,
                db,
                current_user,
                year=payment.year,
                month=payment.month,
                extra={"error": "Некорректная сумма"},
            )
            return templates.TemplateResponse("payments.html", ctx)

    if _payments._fixed_total_exceeds_planned(payment, old_total):
        ctx = await _payments._page_context(
            request,
            db,
            current_user,
            year=payment.year,
            month=payment.month,
            extra={"error": "Сумма оплат больше начисления"},
        )
        return templates.TemplateResponse("payments.html", ctx)

    if status:
        if status not in {"pending", "paid", "overdue"}:
            ctx = await _payments._page_context(
                request,
                db,
                current_user,
                year=payment.year,
                month=payment.month,
                extra={"error": "Некорректный статус"},
            )
            return templates.TemplateResponse("payments.html", ctx)
        payment.status = status

    parsed_paid_date: date | None = None
    if paid_date_str:
        try:
            parsed_paid_date = date.fromisoformat(paid_date_str)
        except ValueError:
            ctx = await _payments._page_context(
                request,
                db,
                current_user,
                year=payment.year,
                month=payment.month,
                extra={"error": "Некорректная дата оплаты"},
            )
            return templates.TemplateResponse("payments.html", ctx)

    new_receipt_path = None
    if receipt and receipt.filename:
        new_receipt_path, upload_err = await _payments._upload_receipt(receipt, payment.year, payment.month)
        if upload_err:
            ctx = await _payments._page_context(
                request,
                db,
                current_user,
                year=payment.year,
                month=payment.month,
                extra={"error": upload_err},
            )
            return templates.TemplateResponse("payments.html", ctx)

    if status == "paid":
        planned = _payments._planned_amount(payment)
        if payment.amount is None or planned <= 0:
            ctx = await _payments._page_context(
                request,
                db,
                current_user,
                year=payment.year,
                month=payment.month,
                extra={"error": "Для оплаты нужно указать сумму начисления"},
            )
            return templates.TemplateResponse("payments.html", ctx)

        paid_date = parsed_paid_date or payment.paid_date or date.today()
        remaining = planned - old_total
        if remaining > 0:
            receipt_for_transaction = new_receipt_path or payment.receipt_file
            tx = PaymentTransaction(
                id=f"tx-{payment.id}-{uuid.uuid4().hex[:8]}",
                payment_id=payment.id,
                amount=remaining,
                paid_date=paid_date,
                receipt_file=receipt_for_transaction,
                notes="Created from legacy edit flow",
            )
            db.add(tx)
            payment.transactions.append(tx)
        elif new_receipt_path:
            if payment.transactions:
                target_tx = next((tx for tx in payment.transactions if not tx.receipt_file), payment.transactions[0])
                _payments._remove_receipt_file(target_tx.receipt_file)
                target_tx.receipt_file = new_receipt_path
            else:
                _payments._remove_receipt_file(payment.receipt_file)
                payment.receipt_file = new_receipt_path

        _payments._refresh_payment_from_transactions(payment, old_total=old_total)
    elif status in {"pending", "overdue"}:
        if new_receipt_path:
            _payments._remove_receipt_file(payment.receipt_file)
            payment.receipt_file = new_receipt_path
        if payment.transactions:
            _payments._refresh_payment_from_transactions(payment, old_total=old_total)
            if status == "overdue" and _payments._remaining_amount(payment) > 0:
                payment.status = "overdue"
        else:
            payment.paid_date = None
            payment.paid_amount = None
    else:
        if parsed_paid_date and not payment.transactions:
            payment.paid_date = parsed_paid_date
        if new_receipt_path:
            _payments._remove_receipt_file(payment.receipt_file)
            payment.receipt_file = new_receipt_path
        if payment.transactions:
            _payments._refresh_payment_from_transactions(payment, old_total=old_total)

    await db.commit()
    return _payments._redirect_to_period(payment.year, payment.month)


# Replace the original APIRoute before app.web.main includes payments.router.
_payments.router.routes = [
    route
    for route in _payments.router.routes
    if not (
        getattr(route, "path", None) == "/payments/{payment_id}/edit"
        and "POST" in getattr(route, "methods", set())
    )
]
_payments.router.post("/payments/{payment_id}/edit")(edit_payment)
_payments.edit_payment = edit_payment

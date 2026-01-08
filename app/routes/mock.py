from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(prefix="/mock", tags=["mock-external"])


CRM_CUSTOMERS: dict[str, dict] = {
    "c_1001": {"id": "c_1001", "email": "alex@example.com", "name": "Alex Johnson"},
    "c_1002": {"id": "c_1002", "email": "sam@example.com", "name": "Sam Patel"},
    "c_flaky": {"id": "c_flaky", "email": "flaky@example.com", "name": "Flaky Customer"},
}


CRM_INVOICES: dict[str, dict] = {
    "i_2001": {"id": "i_2001", "customer_id": "c_1001", "amount_cents": 12500, "currency": "USD", "status": "open"},
    "i_2002": {"id": "i_2002", "customer_id": "c_1002", "amount_cents": 9900, "currency": "USD", "status": "open"},
    "i_flaky": {"id": "i_flaky", "customer_id": "c_flaky", "amount_cents": 1999, "currency": "USD", "status": "open"},
}

BILLING_CUSTOMERS: dict[str, dict] = {}
 
 
BILLING_INVOICES: dict[str, dict] = {}

_flaky_counter: dict[str, int] = {"c_flaky": 0}
_flaky_invoice_counter: dict[str, int] = {"i_flaky": 0}


@router.get("/crm/customers/{customer_id}")
def crm_get_customer(customer_id: str) -> dict:
    if customer_id == "c_flaky":
        _flaky_counter["c_flaky"] += 1
        if _flaky_counter["c_flaky"] % 2 == 1:
            raise HTTPException(status_code=503, detail="temporary upstream outage")

    customer = CRM_CUSTOMERS.get(customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="not found")

    return {**customer, "updated_at": datetime.now(timezone.utc).isoformat()}


@router.get("/crm/invoices/{invoice_id}")
def crm_get_invoice(invoice_id: str) -> dict:
    if invoice_id == "i_flaky":
        _flaky_invoice_counter["i_flaky"] += 1
        if _flaky_invoice_counter["i_flaky"] % 2 == 1:
            raise HTTPException(status_code=503, detail="temporary upstream outage")

    invoice = CRM_INVOICES.get(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="not found")

    return {**invoice, "updated_at": datetime.now(timezone.utc).isoformat()}


class BillingCustomerUpsertRequest(BaseModel):
    external_id: str
    email: str | None = None
    name: str | None = None


@router.post("/billing/customers")
def billing_upsert_customer(body: BillingCustomerUpsertRequest) -> dict:
    if body.external_id == "c_1002":
        raise HTTPException(status_code=429, detail="rate limited")

    record = {
        "id": f"b_{body.external_id}",
        "external_id": body.external_id,
        "email": body.email,
        "name": body.name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    BILLING_CUSTOMERS[body.external_id] = record
    return record


class BillingInvoiceUpsertRequest(BaseModel):
    external_id: str
    customer_external_id: str | None = None
    amount_cents: int | None = None
    currency: str | None = None
    status: str | None = None


@router.post("/billing/invoices")
def billing_upsert_invoice(body: BillingInvoiceUpsertRequest) -> dict:
    if body.external_id == "i_2002":
        raise HTTPException(status_code=429, detail="rate limited")

    record = {
        "id": f"bi_{body.external_id}",
        "external_id": body.external_id,
        "customer_external_id": body.customer_external_id,
        "amount_cents": body.amount_cents,
        "currency": body.currency,
        "status": body.status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    BILLING_INVOICES[body.external_id] = record
    return record

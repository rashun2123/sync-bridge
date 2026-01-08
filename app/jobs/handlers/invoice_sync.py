from __future__ import annotations

from app.core.config import settings
from app.integrations.billing.client import BillingClient
from app.integrations.crm.client import CrmClient
from app.jobs.types import JobContext


def handle_invoice_sync(ctx: JobContext) -> None:
    crm = CrmClient(base_url=settings.crm_base_url, correlation_id=ctx.job.correlation_id)
    billing = BillingClient(base_url=settings.billing_base_url, correlation_id=ctx.job.correlation_id)

    try:
        invoice = crm.get_invoice(ctx.job.entity_id)
        payload = {
            "external_id": invoice["id"],
            "customer_external_id": invoice.get("customer_id"),
            "amount_cents": invoice.get("amount_cents"),
            "currency": invoice.get("currency"),
            "status": invoice.get("status"),
        }
        billing.upsert_invoice(payload)
    finally:
        crm.close()
        billing.close()

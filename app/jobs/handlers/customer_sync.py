from __future__ import annotations

from app.core.config import settings
from app.integrations.billing.client import BillingClient
from app.integrations.crm.client import CrmClient
from app.jobs.types import JobContext


def handle_customer_sync(ctx: JobContext) -> None:
    crm = CrmClient(base_url=settings.crm_base_url, correlation_id=ctx.job.correlation_id)
    billing = BillingClient(base_url=settings.billing_base_url, correlation_id=ctx.job.correlation_id)

    try:
        customer = crm.get_customer(ctx.job.entity_id)
        payload = {
            "external_id": customer["id"],
            "email": customer.get("email"),
            "name": customer.get("name"),
        }
        billing.upsert_customer(payload)
    finally:
        crm.close()
        billing.close()

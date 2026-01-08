from __future__ import annotations

from typing import Any

import httpx

from app.integrations.errors import ExternalAPIError


class CrmClient:
    def __init__(self, *, base_url: str, timeout_seconds: float = 10.0, correlation_id: str | None = None):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base_url, timeout=timeout_seconds)
        self._correlation_id = correlation_id

    def _headers(self) -> dict[str, str]:
        if not self._correlation_id:
            return {}
        return {"X-Correlation-ID": self._correlation_id}

    def get_customer(self, customer_id: str) -> dict[str, Any]:
        try:
            resp = self._client.get(f"/customers/{customer_id}", headers=self._headers())
        except httpx.RequestError as exc:
            raise ExternalAPIError(system="crm", status_code=None, message=str(exc)) from exc

        if resp.status_code == 404:
            raise ExternalAPIError(system="crm", status_code=404, message="customer not found")
        if resp.status_code >= 400:
            raise ExternalAPIError(system="crm", status_code=resp.status_code, message=resp.text)

        data = resp.json()
        if not isinstance(data, dict) or "id" not in data:
            raise ExternalAPIError(system="crm", status_code=resp.status_code, message="invalid response")
        return data

    def get_invoice(self, invoice_id: str) -> dict[str, Any]:
        try:
            resp = self._client.get(f"/invoices/{invoice_id}", headers=self._headers())
        except httpx.RequestError as exc:
            raise ExternalAPIError(system="crm", status_code=None, message=str(exc)) from exc

        if resp.status_code == 404:
            raise ExternalAPIError(system="crm", status_code=404, message="invoice not found")
        if resp.status_code >= 400:
            raise ExternalAPIError(system="crm", status_code=resp.status_code, message=resp.text)

        data = resp.json()
        if not isinstance(data, dict) or "id" not in data:
            raise ExternalAPIError(system="crm", status_code=resp.status_code, message="invalid response")
        return data

    def close(self) -> None:
        self._client.close()

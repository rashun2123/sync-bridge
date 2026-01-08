from __future__ import annotations

from typing import Any

import httpx

from app.integrations.errors import ExternalAPIError


class BillingClient:
    def __init__(self, *, base_url: str, timeout_seconds: float = 10.0, correlation_id: str | None = None):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base_url, timeout=timeout_seconds)
        self._correlation_id = correlation_id

    def _headers(self) -> dict[str, str]:
        if not self._correlation_id:
            return {}
        return {"X-Correlation-ID": self._correlation_id}

    def upsert_customer(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = self._client.post("/customers", json=payload, headers=self._headers())
        except httpx.RequestError as exc:
            raise ExternalAPIError(system="billing", status_code=None, message=str(exc)) from exc

        if resp.status_code >= 400:
            raise ExternalAPIError(system="billing", status_code=resp.status_code, message=resp.text)

        data = resp.json()
        if not isinstance(data, dict) or "id" not in data:
            raise ExternalAPIError(system="billing", status_code=resp.status_code, message="invalid response")
        return data

    def upsert_invoice(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = self._client.post("/invoices", json=payload, headers=self._headers())
        except httpx.RequestError as exc:
            raise ExternalAPIError(system="billing", status_code=None, message=str(exc)) from exc

        if resp.status_code >= 400:
            raise ExternalAPIError(system="billing", status_code=resp.status_code, message=resp.text)

        data = resp.json()
        if not isinstance(data, dict) or "id" not in data:
            raise ExternalAPIError(system="billing", status_code=resp.status_code, message="invalid response")
        return data

    def close(self) -> None:
        self._client.close()

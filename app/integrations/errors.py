from __future__ import annotations


class IntegrationError(Exception):
    pass


class ExternalAPIError(IntegrationError):
    def __init__(self, *, system: str, status_code: int | None, message: str):
        self.system = system
        self.status_code = status_code
        self.message = message
        super().__init__(f"{system} error: {message}")

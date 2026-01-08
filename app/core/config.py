import os


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


class Settings:
    environment: str = os.getenv("SYNCBRIDGE_ENV", "local")

    database_url: str = os.getenv("SYNCBRIDGE_DATABASE_URL", "sqlite:///./syncbridge.db")

    crm_base_url: str = os.getenv("SYNCBRIDGE_CRM_BASE_URL", "http://127.0.0.1:8000/mock/crm")
    billing_base_url: str = os.getenv("SYNCBRIDGE_BILLING_BASE_URL", "http://127.0.0.1:8000/mock/billing")

    job_max_retries_default: int = _get_int("SYNCBRIDGE_JOB_MAX_RETRIES_DEFAULT", 3)
    job_backoff_seconds_base: int = _get_int("SYNCBRIDGE_JOB_BACKOFF_SECONDS_BASE", 2)

    job_lease_seconds: int = _get_int("SYNCBRIDGE_JOB_LEASE_SECONDS", 60)


settings = Settings()

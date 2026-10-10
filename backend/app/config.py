import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    postgres_host: str = os.getenv("POSTGRES_HOST", "db")
    postgres_password: str = os.environ["POSTGRES_PASSWORD"]
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    minio_user: str = os.environ["MINIO_ROOT_USER"]
    minio_password: str = os.environ["MINIO_ROOT_PASSWORD"]
    jwt_secret: str = os.environ["JWT_SECRET"]
    max_requests_per_minute: int = int(os.getenv("MAX_REQUESTS_PER_MINUTE", "20"))
    max_request_cost_usd: float = float(os.getenv("MAX_REQUEST_COST_USD", "0.02"))
    max_daily_cost_usd: float = float(os.getenv("MAX_DAILY_COST_USD", "1"))
    usd_per_1k_tokens: float = float(os.getenv("ESTIMATED_USD_PER_1K_TOKENS", "0"))
    otlp_endpoint: str = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")


settings = Settings()
BUCKET = "synthetic-documents"
ROLES = ("admin", "hr", "finance", "employee")

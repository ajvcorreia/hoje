"""Application settings, read from the environment (PLAN section 6)."""

import base64
import binascii
from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DEV_PUBLIC_URL = "http://localhost:8080"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        populate_by_name=True,
        env_ignore_empty=True,
        case_sensitive=False,
    )

    env: Literal["production", "test", "development"] = Field(
        default="production", validation_alias="HOJE_ENV"
    )
    database_url: str = Field(validation_alias="HOJE_DATABASE_URL")
    secret_key: SecretStr = Field(validation_alias="HOJE_SECRET_KEY")
    public_url: str | None = Field(default=None, validation_alias="HOJE_PUBLIC_URL")
    allow_registration: bool = Field(default=False, validation_alias="HOJE_ALLOW_REGISTRATION")
    insecure_cookies: bool = Field(default=False, validation_alias="HOJE_INSECURE_COOKIES")
    log_level: str = Field(default="INFO", validation_alias="HOJE_LOG_LEVEL")
    # Trust the X-Real-IP header set by hoje-web (Caddy). Only safe while the API is reachable
    # exclusively through hoje-web; set false when anything else can reach the API port.
    trust_real_ip_header: bool = Field(default=True, validation_alias="HOJE_TRUST_REAL_IP_HEADER")
    worker_interval_seconds: int = Field(
        default=60, ge=1, validation_alias="HOJE_WORKER_INTERVAL_SECONDS"
    )

    smtp_host: str | None = Field(default=None, validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, validation_alias="SMTP_USERNAME")
    smtp_password: SecretStr | None = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_starttls: bool = Field(default=True, validation_alias="SMTP_STARTTLS")
    smtp_tls: bool = Field(default=False, validation_alias="SMTP_TLS")
    smtp_from: str | None = Field(default=None, validation_alias="SMTP_FROM")

    @field_validator("secret_key")
    @classmethod
    def _check_secret_key(cls, value: SecretStr) -> SecretStr:
        try:
            raw = base64.b64decode(value.get_secret_value(), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("HOJE_SECRET_KEY must be valid base64") from exc
        if len(raw) != 32:
            raise ValueError("HOJE_SECRET_KEY must decode to exactly 32 bytes")
        return value

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError("HOJE_LOG_LEVEL must be one of CRITICAL, ERROR, WARNING, INFO, DEBUG")
        return level

    @model_validator(mode="after")
    def _check_environment(self) -> Self:
        if self.env == "production" and self.insecure_cookies:
            raise ValueError("HOJE_INSECURE_COOKIES=true is not allowed when HOJE_ENV=production")
        if self.public_url is None:
            if self.env == "production":
                raise ValueError("HOJE_PUBLIC_URL is required when HOJE_ENV=production")
            self.public_url = DEFAULT_DEV_PUBLIC_URL
        self.public_url = self.public_url.rstrip("/")
        return self

    @property
    def secret_key_bytes(self) -> bytes:
        return base64.b64decode(self.secret_key.get_secret_value())

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # required values come from the environment

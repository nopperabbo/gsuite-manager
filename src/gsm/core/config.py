from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
VALID_LOG_FORMATS = {"console", "json"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="GSM_",
        extra="ignore",
        case_sensitive=False,
    )

    cf_api_token: SecretStr
    cf_account_id: str = Field(min_length=32, max_length=32)

    google_oauth_client_path: Path = Path("./credentials.json")
    google_oauth_token_path: Path = Path("./token.json")

    delay_per_domain_sec: float = Field(default=3.0, ge=0)
    delay_per_user_sec: float = Field(default=1.0, ge=0)

    dns_check_resolvers: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["8.8.8.8", "1.1.1.1"])
    dns_check_timeout_sec: float = Field(default=5.0, gt=0)
    dns_check_max_attempts: int = Field(default=6, ge=1)
    dns_check_backoff_sec: Annotated[list[int], NoDecode] = Field(default_factory=lambda: [10, 20, 30, 60, 120, 180])

    ledger_path: Path = Path("./gsm_state.json")

    log_level: str = "INFO"
    log_format: str = "console"

    @field_validator("cf_account_id")
    @classmethod
    def _hex32(cls, v: str) -> str:
        if not all(c in "0123456789abcdef" for c in v.lower()):
            raise ValueError("cf_account_id must be 32-char hexadecimal")
        return v.lower()

    @field_validator("log_level", mode="before")
    @classmethod
    def _level(cls, v: str) -> str:
        upper = str(v).upper()
        if upper not in VALID_LOG_LEVELS:
            raise ValueError(f"log_level must be one of {sorted(VALID_LOG_LEVELS)}")
        return upper

    @field_validator("log_format", mode="before")
    @classmethod
    def _fmt(cls, v: str) -> str:
        lower = str(v).lower()
        if lower not in VALID_LOG_FORMATS:
            raise ValueError(f"log_format must be one of {sorted(VALID_LOG_FORMATS)}")
        return lower

    @field_validator("dns_check_resolvers", mode="before")
    @classmethod
    def _split_csv_resolvers(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("dns_check_backoff_sec", mode="before")
    @classmethod
    def _split_csv_backoff(cls, v: object) -> object:
        if isinstance(v, str):
            return [int(item.strip()) for item in v.split(",") if item.strip()]
        return v

    @field_validator("dns_check_backoff_sec")
    @classmethod
    def _backoff_positive(cls, v: list[int]) -> list[int]:
        if not v or any(x <= 0 for x in v):
            raise ValueError("dns_check_backoff_sec must be non-empty list of positive ints")
        return v


def load_settings(env_file: Path | None = None) -> Settings:
    if env_file is not None:
        return Settings(_env_file=str(env_file))  # type: ignore[call-arg]
    return Settings()  # type: ignore[call-arg]

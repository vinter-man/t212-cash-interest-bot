"""Settings from the environment (and `.env` for local runs)."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from cash_interest.sources import Region


class Settings(BaseSettings):
    # A local .env may hold other projects' variables: unknown ones are ignored, and an empty
    # `OWNER_ID=` (as .env.example ships it) means "not set" rather than a validation error.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    bot_token: SecretStr
    db_path: Path = Path("data/cash-interest.db")
    # Which visitors' rates to follow: EU (Trading 212 Markets Ltd, CySEC) or UK (FCA).
    region: Region = Region.EU
    # May send the bot saved trading212.com pages (see README). Optional.
    owner_id: int | None = None
    log_level: str = "INFO"
    # Written by the heartbeat task, read by the Docker healthcheck.
    heartbeat_file: Path = Path("/tmp/cash-interest.heartbeat")  # noqa: S108 - tmpfs in the container
    # A self-hosted Bot API server, or the fake one the end-to-end test runs. Telegram's if unset.
    telegram_api: str | None = None
    # Set by the image build, so the log says which commit is running.
    git_sha: str = "unknown"

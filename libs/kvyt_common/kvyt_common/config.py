from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """Common fields read from environment variables by every KVYT service."""

    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=False,
    )

    log_level: str = "INFO"
    bug_scenario: str = ""
    service_version: str = "0.1.0"

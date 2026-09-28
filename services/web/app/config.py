from functools import lru_cache

from kvyt_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    gateway_url: str
    upstream_timeout_seconds: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

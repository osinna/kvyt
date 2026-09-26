from functools import lru_cache

from kvyt_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    identity_url: str
    catalog_url: str
    booking_url: str
    jwt_secret: str
    upstream_timeout_seconds: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

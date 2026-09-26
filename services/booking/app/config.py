from functools import lru_cache

from kvyt_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    database_url: str
    catalog_url: str
    hold_ttl_seconds: int = 10 * 60


@lru_cache
def get_settings() -> Settings:
    return Settings()

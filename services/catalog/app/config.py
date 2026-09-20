from functools import lru_cache

from kvyt_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()

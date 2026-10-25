from functools import lru_cache

from kvyt_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    database_url: str
    jwt_secret: str
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_days: int = 30
    oauth_code_ttl_seconds: int = 5 * 60


@lru_cache
def get_settings() -> Settings:
    return Settings()

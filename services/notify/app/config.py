from functools import lru_cache

from kvyt_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    database_url: str
    # Postgres superuser: creates the notify database and user when a data
    # volume from before notify existed lacks them.
    admin_database_url: str
    broker_url: str
    notify_delay_min_ms: int = 1
    notify_delay_max_ms: int = 2500
    consumer_prefetch: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()

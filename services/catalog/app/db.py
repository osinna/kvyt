from sqlalchemy.orm import DeclarativeBase

from kvyt_common import Database

from .config import get_settings


class Base(DeclarativeBase):
    pass


database = Database(get_settings().database_url)
get_session = database.session

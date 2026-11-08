import logging
from collections.abc import AsyncIterator

from sqlalchemy import MetaData, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class Database:
    """Engine and session factory of one service's own database."""

    def __init__(self, url: str) -> None:
        self.engine = create_async_engine(url, pool_pre_ping=True)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_schema(self, metadata: MetaData) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def sync_index(self, name: str, create_sql: str, wanted: bool) -> None:
        """Creates or drops one index to match the expected state.

        create_all() builds indexes only together with a new table, so an index
        dropped earlier is not restored by it. Rows that violate a unique index
        keep it from being created: the service then starts without it and says so.
        """
        log = logging.getLogger("kvyt.startup")
        async with self.engine.begin() as conn:
            if not wanted:
                await conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
                return
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text(create_sql))
        except IntegrityError:
            log.error(
                f"index {name} cannot be created: the data has rows it forbids. "
                "Running without it; run 'make reset' to start from clean data"
            )

    async def session(self) -> AsyncIterator[AsyncSession]:
        """FastAPI dependency: one session per request."""
        async with self.sessionmaker() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()

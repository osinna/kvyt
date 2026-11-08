"""Creates the notify database and its user when they are missing.

db/init runs only on an empty data volume, and a volume created before notify
existed has neither. Uses the Postgres superuser from .env.
"""

import logging

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from .config import get_settings


def _libpq(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


async def ensure_database() -> None:
    settings = get_settings()
    target = make_url(settings.database_url)
    log = logging.getLogger("kvyt.startup")
    try:
        conn = await psycopg.AsyncConnection.connect(
            _libpq(settings.admin_database_url), autocommit=True, connect_timeout=5
        )
    except psycopg.Error as exc:
        log.error(
            "refusing to start: cannot reach Postgres as the admin user to prepare "
            f"the {target.database} database ({type(exc).__name__}). Check "
            "POSTGRES_ADMIN_USER and POSTGRES_ADMIN_PASSWORD in .env, or run 'make reset'"
        )
        raise SystemExit(1)
    async with conn:
        role_exists = await (
            await conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (target.username,))
        ).fetchone()
        if not role_exists:
            await conn.execute(
                sql.SQL("CREATE USER {} WITH PASSWORD {}").format(
                    sql.Identifier(target.username), sql.Literal(target.password)
                )
            )
            log.info(f"database user {target.username} created")
        db_exists = await (
            await conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target.database,))
        ).fetchone()
        if not db_exists:
            name = sql.Identifier(target.database)
            await conn.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(name, sql.Identifier(target.username))
            )
            await conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(name))
            await conn.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    name, sql.Identifier(target.username)
                )
            )
            log.info(f"database {target.database} created")

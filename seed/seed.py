"""Loads KVYT reference data.

Idempotent: every row has a deterministic uuid5 id and is inserted with
ON CONFLICT DO NOTHING, so a second run changes nothing. Session dates are
offsets from SEED_EPOCH (midnight UTC of the current day by default).
Bookings start empty.
"""

import logging
import os
import sys
import uuid
from datetime import datetime, time, timedelta, timezone

import bcrypt
import psycopg

from kvyt_common import configure_logging

log = logging.getLogger("kvyt.seed")

PASSWORD = "Passw0rd!"
ROWS = ("A", "B", "C", "D", "E")
SEATS_PER_ROW = 10
ROW_SURCHARGE_UAH = {"A": 300, "B": 200, "C": 100, "D": 0, "E": 0}


def kvyt_id(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"kvyt/{name}")


USERS = (
    ("admin", "admin@kvyt.local", "admin", "Taras Bondar"),
    ("organizer", "organizer@kvyt.local", "organizer", "Iryna Shevchuk"),
    ("anna", "anna@kvyt.local", "user", "Anna Kovalenko"),
    ("borys", "borys@kvyt.local", "user", "Borys Melnyk"),
)

# slug, title, venue, city, status, description, sessions as (day offset, hour UTC, base price)
EVENTS = (
    (
        "jazz-night",
        "Jazz Night",
        "Docker Hall",
        "Kyiv",
        "published",
        "An evening of classic and modern jazz with a live quartet.",
        ((2, 17, 600), (7, 17, 600), (14, 17, 750)),
    ),
    (
        "stand-up-evening",
        "Stand-up Evening",
        "Pidval Club",
        "Lviv",
        "published",
        "Five comedians, one microphone, no rehearsals.",
        ((3, 18, 400), (10, 18, 400)),
    ),
    (
        "indie-fest",
        "Indie Fest",
        "Port Stage",
        "Odesa",
        "draft",
        "Open-air festival of independent bands. Line-up to be announced.",
        ((21, 15, 900),),
    ),
)

# Physically unavailable seats, by session index; two or three per session.
BLOCKED_SEATS = (
    {("C", 5), ("C", 6)},
    {("A", 1), ("E", 10), ("C", 5)},
)


def seed_epoch() -> datetime:
    raw = os.environ.get("SEED_EPOCH", "").strip()
    if not raw:
        return datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    epoch = datetime.fromisoformat(raw)
    return epoch if epoch.tzinfo else epoch.replace(tzinfo=timezone.utc)


def seed_identity(conn: psycopg.Connection) -> int:
    password_hash = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
    inserted = 0
    for slug, email, role, full_name in USERS:
        cur = conn.execute(
            """
            INSERT INTO users (id, email, password_hash, role, full_name, created_at)
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT DO NOTHING
            """,
            (kvyt_id(f"user/{slug}"), email, password_hash, role, full_name),
        )
        inserted += cur.rowcount
    return inserted


def seed_catalog(conn: psycopg.Connection, epoch: datetime) -> tuple[int, int, int]:
    organizer_id = kvyt_id("user/organizer")
    events = sessions = seats = 0
    session_index = 0
    for slug, title, venue, city, status, description, event_sessions in EVENTS:
        event_id = kvyt_id(f"event/{slug}")
        events += conn.execute(
            """
            INSERT INTO events (id, title, venue, city, description, organizer_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (event_id, title, venue, city, description, organizer_id, status),
        ).rowcount
        for number, (day_offset, hour, base_price) in enumerate(event_sessions, start=1):
            session_id = kvyt_id(f"session/{slug}/{number}")
            starts_at = epoch + timedelta(days=day_offset, hours=hour)
            sessions += conn.execute(
                """
                INSERT INTO sessions (id, event_id, starts_at, base_price_uah)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (session_id, event_id, starts_at, base_price),
            ).rowcount
            blocked = BLOCKED_SEATS[session_index % len(BLOCKED_SEATS)]
            session_index += 1
            rows = [
                (
                    kvyt_id(f"seat/{slug}/{number}/{row}/{seat}"),
                    session_id,
                    row,
                    seat,
                    base_price + ROW_SURCHARGE_UAH[row],
                    (row, seat) in blocked,
                )
                for row in ROWS
                for seat in range(1, SEATS_PER_ROW + 1)
            ]
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO seats (id, session_id, row_label, seat_number, price_uah, is_blocked)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    rows,
                )
                seats += cur.rowcount
    return events, sessions, seats


def main() -> int:
    configure_logging("seed", os.environ.get("LOG_LEVEL", "INFO"))
    try:
        epoch = seed_epoch()
    except ValueError:
        log.error("SEED_EPOCH must be an ISO date or date-time, e.g. 2026-10-01")
        return 1
    log.info(f"seeding with SEED_EPOCH={epoch.isoformat()}")
    try:
        with psycopg.connect(os.environ["IDENTITY_DATABASE_URL"]) as conn:
            users = seed_identity(conn)
        with psycopg.connect(os.environ["CATALOG_DATABASE_URL"]) as conn:
            events, sessions, seats = seed_catalog(conn, epoch)
    except Exception:
        log.exception("seeding failed")
        return 1
    log.info(
        f"seeding done, inserted: users={users} events={events} "
        f"sessions={sessions} seats={seats} (0 means already present)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

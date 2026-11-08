"""Consumer of booking events: one notification per event.

Each delivery is handled in its own task, so the delays of messages in flight
overlap instead of adding up.
"""

import asyncio
import json
import logging
import math
import random
import uuid

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractQueue, AbstractRobustConnection
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from kvyt_common import TRACE_ID_HEADER, trace_context
from kvyt_common.events import (
    BOOKING_CANCELLED,
    BOOKING_CONFIRMED,
    BOOKING_ROUTING_PATTERN,
    EXCHANGE,
    NOTIFY_QUEUE,
    declare_exchange,
)

from . import models
from .config import get_settings
from .db import database
from .models import Notification
from .scenarios import scenarios

NOTIFICATION_TYPE = {
    BOOKING_CONFIRMED: models.BOOKING_CONFIRMED,
    BOOKING_CANCELLED: models.BOOKING_CANCELLED,
}

log = logging.getLogger("kvyt.consumer")


def delivery_delay_seconds() -> float:
    """Random delay, log-uniform between NOTIFY_DELAY_MIN_MS and NOTIFY_DELAY_MAX_MS.

    Log-uniform keeps short and long delays both common: most notifications
    are there within a second, a few take up to the upper bound.
    """
    settings = get_settings()
    low = max(1, settings.notify_delay_min_ms)
    high = max(low, settings.notify_delay_max_ms)
    return math.exp(random.uniform(math.log(low), math.log(high))) / 1000


async def _store(event: dict, notification_type: str) -> bool:
    """Saves the notification. False when this event already has one."""
    values = {
        "user_id": uuid.UUID(event["user_id"]),
        "booking_id": uuid.UUID(event["booking_id"]),
        "type": notification_type,
        "status": models.SENT,
    }
    async with database.sessionmaker() as db:
        if scenarios.active("quartz"):
            db.add(Notification(**values))
            await db.commit()
            return True
        existing = await db.scalar(
            select(Notification.id).where(
                Notification.booking_id == values["booking_id"],
                Notification.type == notification_type,
            )
        )
        if existing is not None:
            return False
        created = await db.scalar(
            insert(Notification).values(**values).on_conflict_do_nothing().returning(Notification.id)
        )
        await db.commit()
        return created is not None


async def handle(message: AbstractIncomingMessage) -> None:
    headers = message.headers or {}
    trace_id = headers.get(TRACE_ID_HEADER)
    with trace_context(str(trace_id) if trace_id else None):
        try:
            event = json.loads(message.body)
            name = event["event"]
            booking_id = event["booking_id"]
            notification_type = NOTIFICATION_TYPE[name]
        except (ValueError, KeyError, TypeError):
            log.error("message malformed, dropped", extra={"queue": NOTIFY_QUEUE})
            await message.reject(requeue=False)
            return
        fields = {
            "event": name,
            "booking_id": booking_id,
            "queue": NOTIFY_QUEUE,
            "redelivered": bool(message.redelivered),
        }
        log.info("message consumed", extra=fields)
        try:
            await asyncio.sleep(delivery_delay_seconds())

            if scenarios.active("onyx") and len(event.get("seat_ids", [])) >= 3:
                log.error("notification render failed", extra=fields)
                await message.ack()
                return

            if not await _store(event, notification_type):
                log.info("duplicate message skipped", extra=fields)
                await message.ack()
                return
            log.info("notification created", extra=fields)

            if (
                scenarios.active("quartz")
                and name == BOOKING_CANCELLED
                and not message.redelivered
            ):
                log.error("consumer crashed before ack", extra=fields)
                await message.nack(requeue=True)
                return

            await message.ack()
        except Exception:
            log.exception("message processing failed, returned to the queue", extra=fields)
            await asyncio.sleep(1)
            await message.nack(requeue=True)


class Consumer:
    def __init__(self) -> None:
        self.connection: AbstractRobustConnection | None = None
        self.queue: AbstractQueue | None = None

    async def start(self) -> None:
        settings = get_settings()
        self.connection = await aio_pika.connect_robust(settings.broker_url)
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=settings.consumer_prefetch)
        exchange = await declare_exchange(channel)
        self.queue = await channel.declare_queue(NOTIFY_QUEUE, durable=True)
        await self.queue.bind(exchange, routing_key=BOOKING_ROUTING_PATTERN)
        await self.queue.consume(handle)
        log.info("consumer started", extra={"queue": NOTIFY_QUEUE, "target": EXCHANGE})

    def is_connected(self) -> bool:
        return self.connection is not None and not self.connection.is_closed

    async def stop(self) -> None:
        if self.connection is not None:
            await self.connection.close()


consumer = Consumer()

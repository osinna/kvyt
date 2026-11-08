"""Domain events over RabbitMQ: names shared by the publisher (booking) and the
consumer (notify), and the publisher itself.

Topology is declared by the broker on startup (infra/broker/definitions.json),
so an event published before notify comes up is not lost. Services declare it
again on connect; the declarations are idempotent.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractConnection

from .middleware import TRACE_ID_HEADER, current_trace_id

EXCHANGE = "kvyt.events"
NOTIFY_QUEUE = "notify.booking-events"
BOOKING_ROUTING_PATTERN = "booking.*"

BOOKING_CONFIRMED = "booking.confirmed"
BOOKING_CANCELLED = "booking.cancelled"

PUBLISH_TIMEOUT_SECONDS = 2.0


async def declare_exchange(channel: AbstractChannel) -> AbstractExchange:
    return await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)


class EventPublisher:
    """Publishes events after the change is committed. Never raises.

    No retries and no outbox: when the broker is unreachable the event is
    dropped and logged, and the HTTP response does not change.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: AbstractConnection | None = None
        self._exchange: AbstractExchange | None = None
        self._lock = asyncio.Lock()
        self._log = logging.getLogger("kvyt.events")

    async def _exchange_ready(self) -> AbstractExchange:
        async with self._lock:
            if self._exchange is None or self._connection is None or self._connection.is_closed:
                self._connection = await aio_pika.connect(
                    self._url, timeout=PUBLISH_TIMEOUT_SECONDS
                )
                channel = await self._connection.channel(publisher_confirms=True)
                self._exchange = await declare_exchange(channel)
            return self._exchange

    async def _drop_connection(self) -> None:
        connection, self._connection, self._exchange = self._connection, None, None
        if connection is not None:
            try:
                await connection.close()
            except Exception:
                pass

    async def publish(self, event: str, payload: dict) -> None:
        body = {
            "event": event,
            **payload,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        booking_id = payload.get("booking_id")
        trace_id = current_trace_id()
        message = aio_pika.Message(
            json.dumps(body).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            headers={TRACE_ID_HEADER: trace_id} if trace_id else {},
        )
        try:
            exchange = await asyncio.wait_for(self._exchange_ready(), PUBLISH_TIMEOUT_SECONDS)
            await asyncio.wait_for(
                exchange.publish(message, routing_key=event), PUBLISH_TIMEOUT_SECONDS
            )
        except Exception:
            self._log.error(
                "event publish failed",
                extra={"event": event, "booking_id": booking_id, "target": "broker"},
                exc_info=True,
            )
            await self._drop_connection()
            return
        self._log.info("event published", extra={"event": event, "booking_id": booking_id})

    async def close(self) -> None:
        await self._drop_connection()

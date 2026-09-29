import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kvyt_common import Caller, DomainError, require_user

from .. import catalog_client, lifecycle
from ..config import get_settings
from ..db import get_session
from ..models import CONFIRMED, EXPIRED, HELD, USED, Booking, BookingItem, SeatLock
from ..scenarios import scenarios
from ..schemas import BookingOut, CreateBookingRequest

router = APIRouter(prefix="/bookings", tags=["bookings"])

BOOKABLE_EVENT_STATUS = "published"


def _not_found() -> DomainError:
    return DomainError("booking_not_found", "Booking not found", 404)


async def _get_own(db: AsyncSession, booking_id: uuid.UUID, caller: Caller) -> Booking:
    """Caller's booking, lazily expired. Someone else's booking is reported as missing."""
    await lifecycle.expire_stale_holds(db, Booking.id == booking_id)
    booking = await lifecycle.load_for_update(db, booking_id)
    if booking is None or booking.user_id != caller.user_id:
        raise _not_found()
    return booking


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BookingOut)
async def create_booking(
    body: CreateBookingRequest,
    caller: Caller = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> BookingOut:
    session = await catalog_client.fetch_session_seats(body.session_id, body.seat_ids)
    if session.event_status != BOOKABLE_EVENT_STATUS or session.starts_at <= lifecycle.utcnow():
        raise DomainError("session_not_bookable", "Session is not open for booking", 409)
    missing = [s for s in body.seat_ids if s not in session.seats]
    if missing:
        raise DomainError("seat_not_found", f"Seat {missing[0]} does not exist in this session", 404)
    for seat in session.seats.values():
        if seat.is_blocked:
            raise DomainError(
                "seat_blocked",
                f"Seat {seat.seat_number} in row {seat.row_label} is not available",
                409,
            )

    seat_ids = sorted(body.seat_ids)  # fixed lock order prevents deadlocks
    try:
        await db.execute(
            insert(SeatLock)
            .values([{"seat_id": s} for s in seat_ids])
            .on_conflict_do_nothing(index_elements=[SeatLock.seat_id])
        )
        await db.execute(
            select(SeatLock.seat_id)
            .where(SeatLock.seat_id.in_(seat_ids))
            .order_by(SeatLock.seat_id)
            .with_for_update()
        )

        # Seats are locked now; an overdue hold on them no longer counts.
        occupying = select(BookingItem.booking_id).where(
            BookingItem.seat_id.in_(seat_ids), BookingItem.is_active
        )
        await lifecycle.expire_stale_holds(db, Booking.id.in_(occupying))
        taken = (
            await db.execute(
                select(BookingItem.seat_id, Booking.status)
                .join(Booking, Booking.id == BookingItem.booking_id)
                .where(BookingItem.seat_id.in_(seat_ids), BookingItem.is_active)
                .order_by(BookingItem.seat_id)
            )
        ).first()
        if taken is not None:
            seat = session.seats[taken.seat_id]
            if taken.status == HELD:
                raise DomainError(
                    "seat_already_held",
                    f"Seat {seat.seat_number} in row {seat.row_label} is on hold",
                    409,
                )
            raise DomainError(
                "seat_already_sold",
                f"Seat {seat.seat_number} in row {seat.row_label} is already sold",
                409,
            )

        booking = Booking(
            user_id=caller.user_id,
            session_id=body.session_id,
            status=HELD,
            held_until=lifecycle.utcnow() + timedelta(seconds=get_settings().hold_ttl_seconds),
        )
        db.add(booking)
        await db.flush()
        db.add_all(
            BookingItem(
                booking_id=booking.id,
                seat_id=seat_id,
                price_uah=session.seats[seat_id].price_uah,
            )
            for seat_id in seat_ids
        )
        await db.flush()
        await db.refresh(booking)
        created = BookingOut.model_validate(booking)
        if scenarios.active("phantom-success"):
            await db.rollback()
        else:
            await db.commit()
    except IntegrityError:
        # The partial unique index is the last line of defence behind the locks.
        await db.rollback()
        raise DomainError("seat_already_held", "One of the seats is already taken", 409)

    return created


@router.get("", response_model=list[BookingOut])
async def list_bookings(
    caller: Caller = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[Booking]:
    await lifecycle.expire_stale_holds(db, Booking.user_id == caller.user_id)
    await db.commit()
    bookings = await db.scalars(
        select(Booking)
        .where(Booking.user_id == caller.user_id)
        .order_by(Booking.created_at.desc(), Booking.id)
    )
    return list(bookings)


@router.get("/{booking_id}", response_model=BookingOut)
async def get_booking(
    booking_id: uuid.UUID,
    caller: Caller = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> Booking:
    booking = await _get_own(db, booking_id, caller)
    await db.commit()
    return booking


@router.post("/{booking_id}/confirm", response_model=BookingOut)
async def confirm_booking(
    booking_id: uuid.UUID,
    caller: Caller = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> Booking:
    booking = await _get_own(db, booking_id, caller)
    if booking.status == EXPIRED:
        await db.commit()
        raise DomainError("booking_expired", "Hold has expired, create a new booking", 409)
    if booking.status != HELD:
        raise DomainError(
            "invalid_booking_status", f"Booking in status {booking.status} cannot be confirmed", 409
        )
    booking.status = CONFIRMED
    await db.commit()
    await db.refresh(booking)
    return booking


@router.post("/{booking_id}/cancel", response_model=BookingOut)
async def cancel_booking(
    booking_id: uuid.UUID,
    caller: Caller = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> Booking:
    booking = await _get_own(db, booking_id, caller)
    if booking.status not in (HELD, CONFIRMED):
        await db.commit()
        raise DomainError(
            "invalid_booking_status", f"Booking in status {booking.status} cannot be cancelled", 409
        )
    await lifecycle.cancel(db, booking)
    await db.commit()
    await db.refresh(booking)
    return booking


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_booking(
    booking_id: uuid.UUID,
    caller: Caller = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """Removes an unpaid booking together with its seats. A confirmed one is cancelled instead."""
    booking = await _get_own(db, booking_id, caller)
    if booking.status in (CONFIRMED, USED):
        await db.commit()
        raise DomainError(
            "invalid_booking_status",
            f"Booking in status {booking.status} cannot be deleted, cancel it instead",
            409,
        )
    # Items go with the booking (ON DELETE CASCADE), which frees the seats.
    await db.execute(delete(Booking).where(Booking.id == booking.id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

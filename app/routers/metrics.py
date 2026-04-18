from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.db import get_db
from app.models import CallLog, CallOutcome, CallSentiment
from app.schemas import CallLogRead, DailyCount, MetricsResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["metrics"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(db: Session = Depends(get_db)) -> MetricsResponse:
    total_calls = db.scalar(select(func.count()).select_from(CallLog)) or 0
    bookings = db.scalar(
        select(func.count()).select_from(CallLog).where(CallLog.outcome == CallOutcome.booked)
    ) or 0

    conversion_rate = round(bookings / total_calls, 4) if total_calls else 0.0

    avg_rounds = db.scalar(select(func.avg(CallLog.num_negotiation_rounds))) or 0.0

    avg_final_rate = db.scalar(
        select(func.avg(CallLog.final_rate)).where(CallLog.final_rate.isnot(None))
    )

    avg_margin = _avg_margin(db)

    outcome_breakdown = _breakdown(db, CallLog.outcome, CallOutcome)
    sentiment_breakdown = _breakdown(db, CallLog.sentiment, CallSentiment)

    calls_last_7_days = _daily_counts(db)

    return MetricsResponse(
        total_calls=total_calls,
        bookings=bookings,
        conversion_rate=conversion_rate,
        avg_negotiation_rounds=round(float(avg_rounds), 2),
        avg_final_rate=round(float(avg_final_rate), 2) if avg_final_rate is not None else None,
        avg_margin_vs_loadboard=avg_margin,
        outcome_breakdown=outcome_breakdown,
        sentiment_breakdown=sentiment_breakdown,
        calls_last_7_days=calls_last_7_days,
    )


@router.get("/calls", response_model=list[CallLogRead])
def list_calls(
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    outcome: Optional[CallOutcome] = Query(default=None),
    sentiment: Optional[CallSentiment] = Query(default=None),
    from_date: Optional[str] = Query(default=None, description="ISO date: 2026-04-01"),
    to_date: Optional[str] = Query(default=None, description="ISO date: 2026-04-30"),
) -> list[CallLog]:
    stmt = select(CallLog).order_by(CallLog.created_at.desc())

    if outcome:
        stmt = stmt.where(CallLog.outcome == outcome)
    if sentiment:
        stmt = stmt.where(CallLog.sentiment == sentiment)
    if from_date:
        stmt = stmt.where(CallLog.created_at >= datetime.fromisoformat(from_date))
    if to_date:
        stmt = stmt.where(
            CallLog.created_at <= datetime.fromisoformat(to_date).replace(
                hour=23, minute=59, second=59
            )
        )

    stmt = stmt.offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


# ── Private helpers ───────────────────────────────────────────────────────────

def _avg_margin(db: Session) -> Optional[float]:
    """Average (final_rate - initial_rate) across booked calls that have both rates."""
    row = db.execute(
        select(func.avg(CallLog.final_rate - CallLog.initial_rate)).where(
            CallLog.outcome == CallOutcome.booked,
            CallLog.final_rate.isnot(None),
            CallLog.initial_rate.isnot(None),
        )
    ).scalar()
    return round(float(row), 2) if row is not None else None


def _breakdown(db: Session, column, enum_cls) -> dict:
    rows = db.execute(
        select(column, func.count()).group_by(column)
    ).all()
    result = {member.value: 0 for member in enum_cls}
    for value, count in rows:
        if value is not None:
            result[value.value if hasattr(value, "value") else value] = count
    return result


def _daily_counts(db: Session) -> list[DailyCount]:
    cutoff = datetime.utcnow() - timedelta(days=7)
    rows = db.execute(
        select(
            func.strftime("%Y-%m-%d", CallLog.created_at).label("day"),
            func.count().label("cnt"),
        )
        .where(CallLog.created_at >= cutoff)
        .group_by("day")
        .order_by("day")
    ).all()
    return [DailyCount(date=row.day, count=row.cnt) for row in rows]

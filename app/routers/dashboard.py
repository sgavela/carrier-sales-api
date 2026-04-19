"""GET /dashboard — real-time aggregates for the carrier-sales frontend."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.db import get_db
from app.models import CallLog
from app.schemas import DashboardResponse
from app.services.dashboard import (
    compute_carriers,
    compute_overview,
    compute_pricing,
    compute_quality,
    get_recent_calls,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"], dependencies=[Depends(verify_api_key)])


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    db: Session = Depends(get_db),
    from_date: Optional[str] = Query(
        default=None,
        alias="from",
        description="Start date (YYYY-MM-DD). Defaults to today − 30 days.",
    ),
    to_date: Optional[str] = Query(
        default=None,
        alias="to",
        description="End date (YYYY-MM-DD). Defaults to today.",
    ),
    equipment_type: Optional[str] = Query(
        default=None,
        description="Filter by equipment type, e.g. 'Reefer'. Omit for all.",
    ),
) -> DashboardResponse:
    now = datetime.utcnow()

    date_from = (
        date.fromisoformat(from_date) if from_date else (now - timedelta(days=30)).date()
    )
    date_to = date.fromisoformat(to_date) if to_date else now.date()

    from_dt = datetime(date_from.year, date_from.month, date_from.day)
    to_dt = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59)

    stmt = select(CallLog).where(
        CallLog.received_at >= from_dt,
        CallLog.received_at <= to_dt,
    )

    if equipment_type:
        stmt = stmt.where(CallLog.equipment_type == equipment_type)

    rows = db.scalars(stmt).all()
    calls = _to_dicts(rows)

    logger.info(
        "dashboard computed period=%s to %s equipment=%s calls=%d",
        date_from, date_to, equipment_type, len(calls),
    )

    return DashboardResponse(
        generated_at=now,
        period_from=str(date_from),
        period_to=str(date_to),
        equipment_filter=equipment_type,
        overview=compute_overview(calls, date_from, date_to),
        carriers=compute_carriers(calls, now=now),
        pricing=compute_pricing(calls),
        quality=compute_quality(calls),
        recent_calls=get_recent_calls(calls, limit=20),
    )


def _to_dicts(rows: list[CallLog]) -> list[dict]:
    return [
        {col.name: getattr(r, col.name) for col in CallLog.__table__.columns}
        for r in rows
    ]

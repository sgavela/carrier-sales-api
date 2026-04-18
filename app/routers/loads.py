from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.db import get_db
from app.models import Load, LoadStatus
from app.schemas import LoadRead, SearchLoadsRequest

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/loads",
    tags=["loads"],
    dependencies=[Depends(verify_api_key)],
)


def _city(location: str) -> str:
    """Extract the city portion from 'City, ST' for case-insensitive matching."""
    return location.split(",")[0].strip().lower()


@router.post("/search", response_model=list[LoadRead])
def search_loads(body: SearchLoadsRequest, db: Session = Depends(get_db)) -> list[Load]:
    stmt = select(Load).where(Load.status == LoadStatus.available)

    if body.origin:
        origin_city = _city(body.origin)
        stmt = stmt.where(Load.origin.ilike(f"{origin_city}%"))

    if body.destination:
        dest_city = _city(body.destination)
        stmt = stmt.where(Load.destination.ilike(f"{dest_city}%"))

    if body.equipment_type:
        stmt = stmt.where(Load.equipment_type == body.equipment_type)

    if body.pickup_date_from:
        stmt = stmt.where(
            Load.pickup_datetime >= datetime.combine(body.pickup_date_from, datetime.min.time())
        )

    if body.pickup_date_to:
        stmt = stmt.where(
            Load.pickup_datetime <= datetime.combine(body.pickup_date_to, datetime.max.time())
        )

    stmt = stmt.order_by(Load.pickup_datetime.asc()).limit(body.max_results)
    results = db.scalars(stmt).all()

    logger.info(
        "Load search — origin=%s dest=%s equip=%s results=%d",
        body.origin,
        body.destination,
        body.equipment_type,
        len(results),
    )
    return list(results)


@router.get("/{load_id}", response_model=LoadRead)
def get_load(load_id: str, db: Session = Depends(get_db)) -> Load:
    load = db.get(Load, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    return load

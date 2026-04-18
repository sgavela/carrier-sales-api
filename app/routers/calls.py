from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.db import get_db
from app.models import CallLog, CallOutcome, Load, LoadStatus
from app.schemas import LogCallRequest, LogCallResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/calls",
    tags=["calls"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/log", response_model=LogCallResponse, status_code=status.HTTP_201_CREATED)
def log_call(body: LogCallRequest, db: Session = Depends(get_db)) -> LogCallResponse:
    call_id = body.id or str(uuid.uuid4())
    existing = db.get(CallLog, call_id)
    created = existing is None

    if existing:
        _update_call(existing, body)
    else:
        existing = _create_call(call_id, body)
        db.add(existing)

    if body.outcome == CallOutcome.booked and body.load_id:
        _book_load(db, body.load_id, body.final_rate, body.mc_number)

    db.commit()

    logger.info(
        "Call logged — id=%s mc=%s outcome=%s created=%s",
        call_id,
        body.mc_number,
        body.outcome,
        created,
    )
    return LogCallResponse(id=call_id, created=created)


def _create_call(call_id: str, body: LogCallRequest) -> CallLog:
    return CallLog(
        id=call_id,
        mc_number=body.mc_number,
        carrier_name=body.carrier_name,
        load_id=body.load_id,
        initial_rate=body.initial_rate,
        final_rate=body.final_rate,
        num_negotiation_rounds=body.num_negotiation_rounds,
        outcome=body.outcome,
        sentiment=body.sentiment,
        transcript_summary=body.transcript_summary,
        raw_extraction=body.raw_extraction,
    )


def _update_call(record: CallLog, body: LogCallRequest) -> None:
    record.mc_number = body.mc_number
    record.carrier_name = body.carrier_name
    record.load_id = body.load_id
    record.initial_rate = body.initial_rate
    record.final_rate = body.final_rate
    record.num_negotiation_rounds = body.num_negotiation_rounds
    record.outcome = body.outcome
    record.sentiment = body.sentiment
    record.transcript_summary = body.transcript_summary
    record.raw_extraction = body.raw_extraction


def _book_load(db: Session, load_id: str, rate: float | None, mc: str) -> None:
    load = db.get(Load, load_id)
    if not load:
        logger.warning("log_call: load %s not found — skipping booking", load_id)
        return
    load.status = LoadStatus.booked
    load.booked_rate = rate
    load.booked_mc = mc

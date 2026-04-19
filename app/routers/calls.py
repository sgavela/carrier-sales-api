from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.db import get_db
from app.models import CallLog, CallOutcome, Load, LoadStatus
from app.schemas import (
    LogCallRequest,
    LogCallRequestLegacy,
    LogCallResponse,
    LogCallResponseLegacy,
)
from app.services.call_logging import flatten_payload, validate_business_rules

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/calls",
    tags=["calls"],
    dependencies=[Depends(verify_api_key)],
)


# ── Legacy endpoint (flat payload, kept for backward compat) ──────────────────

@router.post(
    "/log",
    response_model=LogCallResponseLegacy,
    status_code=status.HTTP_201_CREATED,
    summary="Log call (legacy flat payload)",
)
def log_call_legacy(
    body: LogCallRequestLegacy, db: Session = Depends(get_db)
) -> LogCallResponseLegacy:
    call_id = body.id or str(uuid.uuid4())
    existing = db.get(CallLog, call_id)
    created = existing is None

    if existing:
        _update_legacy(existing, body)
    else:
        existing = _create_legacy(call_id, body)
        db.add(existing)

    if body.outcome == CallOutcome.booked and body.load_id:
        _book_load(db, body.load_id, body.final_rate, body.mc_number)

    db.commit()
    logger.info(
        "call_logged id=%s outcome=%s mc=%s created=%s",
        call_id, body.outcome, body.mc_number, created,
    )
    return LogCallResponseLegacy(id=call_id, created=created)


def _create_legacy(call_id: str, body: LogCallRequestLegacy) -> CallLog:
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


def _update_legacy(record: CallLog, body: LogCallRequestLegacy) -> None:
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


# ── New endpoint (HappyRobot nested payload) ──────────────────────────────────

@router.post(
    "/log-call",
    response_model=LogCallResponse,
    status_code=status.HTTP_200_OK,
    summary="Log call (HappyRobot nested payload)",
)
def log_call(body: LogCallRequest, db: Session = Depends(get_db)) -> LogCallResponse:
    # 1. Business-rule validation (beyond schema)
    validate_business_rules(body)

    # 2. Flatten nested payload to column dict
    flat = flatten_payload(body)

    # 3. Upsert
    existing = db.get(CallLog, body.call_id)
    action: str

    if existing:
        for key, val in flat.items():
            setattr(existing, key, val)
        existing.created_at = existing.created_at  # leave original created_at
        action = "updated"
        logger.info(
            "call_log updated id=%s outcome=%s mc=%s",
            body.call_id, flat["outcome"], flat["mc_number"],
        )
    else:
        record = CallLog(**flat, created_at=body.started_at)
        db.add(record)
        action = "created"
        logger.info(
            "call_logged id=%s outcome=%s mc=%s final_rate=%s",
            body.call_id, flat["outcome"], flat["mc_number"], flat["final_rate"],
        )

    if flat["tool_errors"]:
        logger.warning(
            "tool_errors reported for call %s: %s",
            body.call_id, flat["tool_errors"],
        )

    # 4. Side effects for booked outcome
    load_status_changed = False
    warning: str | None = None

    if flat["outcome"] == "booked" and flat["load_id"]:
        load = db.get(Load, flat["load_id"])
        if load:
            if load.status == LoadStatus.available:
                load.status = LoadStatus.booked
                load.booked_rate = flat["final_rate"]
                load.booked_mc = flat["mc_number"] or None
                load_status_changed = True
            elif load.status == LoadStatus.booked:
                warning = (
                    f"load {flat['load_id']} was already booked "
                    f"when call {body.call_id} reported booking"
                )
                logger.warning(
                    "load %s was already booked when call %s reported booking",
                    flat["load_id"], body.call_id,
                )

    db.commit()

    return LogCallResponse(
        call_id=body.call_id,
        stored=True,
        action=action,
        load_status_changed=load_status_changed,
        warning=warning,
    )


# ── Shared helper ─────────────────────────────────────────────────────────────

def _book_load(db: Session, load_id: str, rate: float | None, mc: str) -> None:
    load = db.get(Load, load_id)
    if not load:
        logger.warning("log_call: load %s not found — skipping booking", load_id)
        return
    load.status = LoadStatus.booked
    load.booked_rate = rate
    load.booked_mc = mc

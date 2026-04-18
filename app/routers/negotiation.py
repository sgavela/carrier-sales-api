from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.db import get_db
from app.models import Load
from app.schemas import EvaluateOfferRequest, EvaluateOfferResponse
from app.services.negotiator import evaluate

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/negotiation",
    tags=["negotiation"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/evaluate-offer", response_model=EvaluateOfferResponse)
def evaluate_offer(
    body: EvaluateOfferRequest, db: Session = Depends(get_db)
) -> EvaluateOfferResponse:
    load = db.get(Load, body.load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    # Use the rate from DB as the authoritative source, ignoring whatever
    # the caller sends — prevents manipulation of the negotiation floor
    decision = evaluate(load.loadboard_rate, body.carrier_offer, body.round)

    logger.info(
        "Negotiation — load=%s round=%d offer=%.2f action=%s counter=%s",
        body.load_id,
        body.round,
        body.carrier_offer,
        decision.action,
        decision.counter_offer,
    )

    return EvaluateOfferResponse(
        action=decision.action,
        counter_offer=decision.counter_offer,
        message_hint=decision.message_hint,
        should_close=decision.should_close,
    )

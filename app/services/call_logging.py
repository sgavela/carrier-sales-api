"""Business logic for the POST /log-call endpoint."""

from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException, status

from app.schemas import LogCallRequest


def normalize_mc(raw: Optional[str]) -> Optional[str]:
    """Strip 'MC' prefix, spaces, dashes. Return None if nothing remains."""
    if raw is None:
        return None
    s = raw.strip().upper()
    if s.startswith("MC"):
        s = s[2:]
    s = re.sub(r"[\s\-]", "", s)
    return s if s else None


def validate_business_rules(body: LogCallRequest) -> None:
    """Raise HTTP 400 if the payload violates cross-field business rules."""
    outcome = body.classification.outcome
    neg = body.negotiation
    carrier = body.carrier

    if outcome == "booked":
        if neg.final_rate is None or body.load.load_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="booked calls require final_rate and load_id",
            )

    if outcome == "carrier_not_eligible" and carrier.eligible is not False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="carrier_not_eligible outcome requires carrier.eligible=false",
        )

    if neg.num_rounds != len(neg.rounds_detail):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"num_rounds={neg.num_rounds} does not match "
                f"len(rounds_detail)={len(neg.rounds_detail)}"
            ),
        )


def flatten_payload(p: LogCallRequest) -> dict:
    """Map the nested HappyRobot payload to a flat dict matching CallLog columns."""
    return {
        "id": p.call_id,
        "started_at": p.started_at,
        "ended_at": p.ended_at,
        "mc_number": normalize_mc(p.carrier.mc_number) or "",
        "carrier_name": p.carrier.carrier_name,
        "dot_number": p.carrier.dot_number,
        "carrier_eligible": p.carrier.eligible,
        "ineligible_reason": p.carrier.ineligible_reason,
        "load_id": p.load.load_id,
        "origin": p.load.origin,
        "destination": p.load.destination,
        "equipment_type": p.load.equipment_type,
        "loadboard_rate": p.load.loadboard_rate,
        "miles": p.load.miles,
        "commodity_type": p.load.commodity_type,
        "pickup_datetime": p.load.pickup_datetime,
        "initial_carrier_offer": p.negotiation.initial_carrier_offer,
        "final_rate": p.negotiation.final_rate,
        "num_rounds": p.negotiation.num_rounds,
        "rounds_detail": [r.model_dump() for r in p.negotiation.rounds_detail],
        "walk_away_reason": p.negotiation.walk_away_reason,
        "outcome": p.classification.outcome,
        "sentiment": p.classification.sentiment,
        "unresolved_topics": p.classification.unresolved_topics,
        "tool_errors": p.classification.tool_errors,
        "transcript_summary": p.summary.transcript_summary,
        "raw_extraction": p.summary.raw_extraction,
        # legacy compat columns
        "initial_rate": p.negotiation.initial_carrier_offer,
        "num_negotiation_rounds": p.negotiation.num_rounds,
    }

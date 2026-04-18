from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_api_key
from app.schemas import VerifyCarrierRequest, VerifyCarrierResponse
from app.services.fmcsa import FMCSAError, lookup_carrier

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/carriers",
    tags=["carriers"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/verify", response_model=VerifyCarrierResponse)
async def verify_carrier(body: VerifyCarrierRequest) -> VerifyCarrierResponse:
    if not body.mc_number or not body.mc_number.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mc_number is required",
        )

    try:
        info = await lookup_carrier(body.mc_number)
    except FMCSAError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )

    logger.info(
        "Carrier verification — MC=%s eligible=%s reason=%s",
        info.mc_number,
        info.eligible,
        info.reason,
    )

    return VerifyCarrierResponse(
        eligible=info.eligible,
        mc_number=info.mc_number,
        carrier_name=info.carrier_name,
        dot_number=info.dot_number,
        allowed_to_operate=info.allowed_to_operate,
        reason=info.reason,
    )

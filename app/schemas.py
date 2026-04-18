from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models import CallOutcome, CallSentiment, EquipmentType, LoadStatus


class LoadRead(BaseModel):
    load_id: str
    origin: str
    destination: str
    pickup_datetime: datetime
    delivery_datetime: datetime
    equipment_type: EquipmentType
    loadboard_rate: float
    weight: int
    commodity_type: str
    num_of_pieces: int
    miles: int
    dimensions: str
    status: LoadStatus
    notes: Optional[str] = None
    booked_rate: Optional[float] = None
    booked_mc: Optional[str] = None

    model_config = {"from_attributes": True}


class VerifyCarrierRequest(BaseModel):
    mc_number: str


class VerifyCarrierResponse(BaseModel):
    eligible: bool
    mc_number: str
    carrier_name: Optional[str] = None
    dot_number: Optional[str] = None
    allowed_to_operate: Optional[str] = None
    reason: Optional[str] = None


class EvaluateOfferRequest(BaseModel):
    load_id: str
    loadboard_rate: float
    carrier_offer: float
    round: int = Field(default=1, ge=1)


class EvaluateOfferResponse(BaseModel):
    action: str                         # "accept" | "counter" | "reject"
    counter_offer: Optional[float] = None
    message_hint: str
    should_close: bool


class SearchLoadsRequest(BaseModel):
    origin: Optional[str] = None
    destination: Optional[str] = None
    equipment_type: Optional[EquipmentType] = None
    pickup_date_from: Optional[date] = None
    pickup_date_to: Optional[date] = None
    max_results: int = Field(default=3, ge=1, le=20)


# ── Call logging ──────────────────────────────────────────────────────────────

class LogCallRequest(BaseModel):
    id: Optional[str] = None           # if provided, used as PK for idempotency
    mc_number: str
    carrier_name: Optional[str] = None
    load_id: Optional[str] = None
    initial_rate: Optional[float] = None
    final_rate: Optional[float] = None
    num_negotiation_rounds: int = 0
    outcome: CallOutcome
    sentiment: CallSentiment
    transcript_summary: Optional[str] = None
    raw_extraction: Optional[Any] = None


class LogCallResponse(BaseModel):
    id: str
    created: bool                      # True = new record, False = updated existing

    model_config = {"from_attributes": True}


class CallLogRead(BaseModel):
    id: str
    created_at: datetime
    mc_number: str
    carrier_name: Optional[str] = None
    load_id: Optional[str] = None
    initial_rate: Optional[float] = None
    final_rate: Optional[float] = None
    num_negotiation_rounds: int
    outcome: CallOutcome
    sentiment: CallSentiment
    transcript_summary: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Metrics ───────────────────────────────────────────────────────────────────

class DailyCount(BaseModel):
    date: str
    count: int


class MetricsResponse(BaseModel):
    total_calls: int
    bookings: int
    conversion_rate: float
    avg_negotiation_rounds: float
    avg_final_rate: Optional[float]
    avg_margin_vs_loadboard: Optional[float]
    outcome_breakdown: Dict[str, int]
    sentiment_breakdown: Dict[str, int]
    calls_last_7_days: List[DailyCount]

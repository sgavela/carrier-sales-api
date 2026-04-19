from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

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


# ── Carrier verification ──────────────────────────────────────────────────────

class VerifyCarrierRequest(BaseModel):
    mc_number: str = Field(
        examples=["MC123456"],
        description="Motor Carrier number. Prefix 'MC', dashes and spaces are stripped automatically.",
    )
    model_config = {"json_schema_extra": {"example": {"mc_number": "MC123456"}}}


class VerifyCarrierResponse(BaseModel):
    eligible: bool
    mc_number: str
    carrier_name: Optional[str] = None
    dot_number: Optional[str] = None
    allowed_to_operate: Optional[str] = None
    reason: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "eligible": True,
                "mc_number": "123456",
                "carrier_name": "ACME TRUCKING LLC",
                "dot_number": "3456789",
                "allowed_to_operate": "Y",
                "reason": None,
            }
        }
    }


# ── Load search ───────────────────────────────────────────────────────────────

class SearchLoadsRequest(BaseModel):
    origin: Optional[str] = Field(default=None, examples=["Chicago"])
    destination: Optional[str] = Field(default=None, examples=["Atlanta"])
    equipment_type: Optional[EquipmentType] = Field(default=None, examples=["Dry Van"])
    pickup_date_from: Optional[date] = Field(default=None, examples=["2026-04-19"])
    pickup_date_to: Optional[date] = Field(default=None, examples=["2026-04-26"])
    max_results: int = Field(default=3, ge=1, le=20)

    model_config = {
        "json_schema_extra": {
            "example": {
                "origin": "Chicago",
                "destination": "Atlanta",
                "equipment_type": "Dry Van",
                "pickup_date_from": "2026-04-19",
                "pickup_date_to": "2026-04-26",
                "max_results": 3,
            }
        }
    }


# ── Negotiation ───────────────────────────────────────────────────────────────

class EvaluateOfferRequest(BaseModel):
    load_id: str = Field(examples=["LD-00001"])
    loadboard_rate: float = Field(examples=[1500.0])
    carrier_offer: float = Field(examples=[1700.0])
    round: int = Field(default=1, ge=1, examples=[1])

    model_config = {
        "json_schema_extra": {
            "example": {
                "load_id": "LD-00001",
                "loadboard_rate": 1500.0,
                "carrier_offer": 1700.0,
                "round": 1,
            }
        }
    }


class EvaluateOfferResponse(BaseModel):
    action: str
    counter_offer: Optional[float] = None
    message_hint: str
    should_close: bool

    model_config = {
        "json_schema_extra": {
            "example": {
                "action": "counter",
                "counter_offer": 1600.0,
                "message_hint": "We're close. We can meet you halfway at $1,600.00.",
                "should_close": False,
            }
        }
    }


# ── Call logging — legacy flat schema (used by POST /calls/log) ───────────────

class LogCallRequestLegacy(BaseModel):
    id: Optional[str] = Field(default=None, examples=["550e8400-e29b-41d4-a716-446655440000"])
    mc_number: str = Field(examples=["123456"])
    carrier_name: Optional[str] = Field(default=None, examples=["ACME TRUCKING LLC"])
    load_id: Optional[str] = Field(default=None, examples=["LD-00001"])
    initial_rate: Optional[float] = Field(default=None, examples=[1500.0])
    final_rate: Optional[float] = Field(default=None, examples=[1600.0])
    num_negotiation_rounds: int = Field(default=0, examples=[1])
    outcome: CallOutcome
    sentiment: CallSentiment
    transcript_summary: Optional[str] = Field(default=None)
    raw_extraction: Optional[Any] = Field(default=None)

    model_config = {
        "json_schema_extra": {
            "example": {
                "mc_number": "123456",
                "carrier_name": "ACME TRUCKING LLC",
                "load_id": "LD-00001",
                "initial_rate": 1500.0,
                "final_rate": 1600.0,
                "num_negotiation_rounds": 1,
                "outcome": "booked",
                "sentiment": "positive",
                "transcript_summary": "Carrier agreed after one counter-offer.",
                "raw_extraction": {"call_duration_s": 145},
            }
        }
    }


class LogCallResponseLegacy(BaseModel):
    id: str
    created: bool

    model_config = {"from_attributes": True}


# ── Coercion helpers ──────────────────────────────────────────────────────────

def _coerce_str_or_none(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    s = str(v).strip()
    return s or None


def _coerce_float_or_none(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _coerce_int_or_none(v: Any) -> Optional[int]:
    f = _coerce_float_or_none(v)
    return int(round(f)) if f is not None else None


def _coerce_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "y")
    if isinstance(v, (int, float)):
        return bool(v)
    return False


def _coerce_list_of_str(v: Any) -> List[str]:
    """Accept array, single string, comma-separated string, or empty."""
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if x]
    if isinstance(v, str):
        if "," in v:
            return [t.strip() for t in v.split(",") if t.strip()]
        return [v.strip()]
    return [str(v)]


def _normalize_digits(v: Any) -> Optional[str]:
    """Strip any non-digit characters (handles 'MC-123456', 'DOT-3456789', etc.)."""
    s = _coerce_str_or_none(v)
    if s is None:
        return None
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits or None


# ── Call logging — HappyRobot nested schema (used by POST /log-call) ─────────

class CarrierBlock(BaseModel):
    mc_number: Optional[str] = None
    carrier_name: Optional[str] = None
    dot_number: Optional[str] = None
    eligible: bool = False
    ineligible_reason: Optional[str] = None

    @field_validator("mc_number", "dot_number", mode="before")
    @classmethod
    def _normalize_ids(cls, v: Any) -> Optional[str]:
        return _normalize_digits(v)

    @field_validator("carrier_name", "ineligible_reason", mode="before")
    @classmethod
    def _strs(cls, v: Any) -> Optional[str]:
        return _coerce_str_or_none(v)

    @field_validator("eligible", mode="before")
    @classmethod
    def _eligible(cls, v: Any) -> bool:
        return _coerce_bool(v)


class LoadBlock(BaseModel):
    load_id: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    equipment_type: Optional[str] = None
    loadboard_rate: Optional[float] = None
    miles: Optional[int] = None
    commodity_type: Optional[str] = None
    pickup_datetime: Optional[datetime] = None

    @field_validator("load_id", "origin", "destination", "equipment_type", "commodity_type", mode="before")
    @classmethod
    def _strs(cls, v: Any) -> Optional[str]:
        return _coerce_str_or_none(v)

    @field_validator("loadboard_rate", mode="before")
    @classmethod
    def _rate(cls, v: Any) -> Optional[float]:
        return _coerce_float_or_none(v)

    @field_validator("miles", mode="before")
    @classmethod
    def _miles(cls, v: Any) -> Optional[int]:
        return _coerce_int_or_none(v)

    @field_validator("pickup_datetime", mode="before")
    @classmethod
    def _pickup(cls, v: Any) -> Optional[datetime]:
        s = _coerce_str_or_none(v)
        if s is None:
            return None
        try:
            return datetime.fromisoformat(s)
        except (ValueError, TypeError):
            return None


class NegotiationRound(BaseModel):
    round: int = Field(ge=1, le=3)
    carrier_offer: Optional[float] = None
    our_counter: Optional[float] = None
    decision: Literal["accept", "counter", "reject"]

    @field_validator("carrier_offer", "our_counter", mode="before")
    @classmethod
    def _nums(cls, v: Any) -> Optional[float]:
        return _coerce_float_or_none(v)


class NegotiationBlock(BaseModel):
    initial_carrier_offer: Optional[float] = None
    final_rate: Optional[float] = None
    num_rounds: int = 0
    rounds_detail: List[NegotiationRound] = []
    walk_away_reason: Optional[str] = None

    @field_validator("initial_carrier_offer", "final_rate", mode="before")
    @classmethod
    def _nums(cls, v: Any) -> Optional[float]:
        return _coerce_float_or_none(v)

    @field_validator("num_rounds", mode="before")
    @classmethod
    def _rounds(cls, v: Any) -> int:
        return _coerce_int_or_none(v) or 0

    @field_validator("walk_away_reason", mode="before")
    @classmethod
    def _reason(cls, v: Any) -> Optional[str]:
        return _coerce_str_or_none(v)

    @field_validator("rounds_detail", mode="before")
    @classmethod
    def _rounds_list(cls, v: Any) -> Any:
        if isinstance(v, str):
            if v.strip() in ("", "[]"):
                return []
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return []
        return v or []


class ClassificationBlock(BaseModel):
    outcome: Literal[
        "booked", "no_agreement", "carrier_not_eligible",
        "no_loads_found", "carrier_declined", "other"
    ] = "other"
    sentiment: Literal["positive", "neutral", "negative"] = "neutral"
    unresolved_topics: List[str] = []

    @field_validator("unresolved_topics", mode="before")
    @classmethod
    def _topics(cls, v: Any) -> List[str]:
        return _coerce_list_of_str(v)


class SummaryBlock(BaseModel):
    transcript_summary: Optional[str] = None

    @field_validator("transcript_summary", mode="before")
    @classmethod
    def _str(cls, v: Any) -> Optional[str]:
        return _coerce_str_or_none(v)


class LogCallRequest(BaseModel):
    call_id: str
    duration: int = 0
    num_user_turns: int = 0
    num_assistant_turns: int = 0
    carrier: CarrierBlock
    load: LoadBlock = Field(default_factory=LoadBlock)
    negotiation: NegotiationBlock = Field(default_factory=NegotiationBlock)
    classification: ClassificationBlock = Field(default_factory=ClassificationBlock)
    summary: SummaryBlock = Field(default_factory=SummaryBlock)

    @field_validator("duration", "num_user_turns", "num_assistant_turns", mode="before")
    @classmethod
    def _ints(cls, v: Any) -> int:
        return _coerce_int_or_none(v) or 0

    model_config = {
        "json_schema_extra": {
            "example": {
                "call_id": "8e8a80b0-72fe-4c2b-78ab-fe6214c2b78a",
                "duration": 245,
                "num_user_turns": 5,
                "num_assistant_turns": 6,
                "carrier": {
                    "mc_number": "123456",
                    "carrier_name": "SWIFT LOGISTICS LLC",
                    "dot_number": "2001001",
                    "eligible": True,
                    "ineligible_reason": "",
                },
                "load": {
                    "load_id": "LD-00001",
                    "origin": "Chicago, IL",
                    "destination": "Atlanta, GA",
                    "equipment_type": "Dry Van",
                    "loadboard_rate": 1500.0,
                    "miles": 716,
                    "commodity_type": "Electronics",
                    "pickup_datetime": "2026-04-25T08:00:00",
                },
                "negotiation": {
                    "initial_carrier_offer": 1650.0,
                    "final_rate": 1560.0,
                    "num_rounds": 1,
                    "rounds_detail": [
                        {"round": 1, "carrier_offer": 1650.0, "our_counter": 1500.0, "decision": "accept"}
                    ],
                    "walk_away_reason": "",
                },
                "classification": {
                    "outcome": "booked",
                    "sentiment": "positive",
                    "unresolved_topics": [],
                },
                "summary": {
                    "transcript_summary": "Carrier verified. Booked Chicago-Atlanta Dry Van at $1,560.",
                },
            }
        }
    }


class LogCallResponse(BaseModel):
    call_id: str
    stored: bool
    action: Literal["created", "updated"]
    load_status_changed: bool
    warning: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "call_id": "hr_a1b2c3d4",
                "stored": True,
                "action": "created",
                "load_status_changed": True,
                "warning": None,
            }
        }
    }


# ── Existing read / metrics schemas ───────────────────────────────────────────

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


class DailyCount(BaseModel):
    date: str = Field(examples=["2026-04-18"])
    count: int = Field(examples=[5])


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

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_calls": 42,
                "bookings": 15,
                "conversion_rate": 0.357,
                "avg_negotiation_rounds": 1.8,
                "avg_final_rate": 2087.5,
                "avg_margin_vs_loadboard": -45.2,
                "outcome_breakdown": {"booked": 15, "no_agreement": 12},
                "sentiment_breakdown": {"positive": 20, "neutral": 15, "negative": 7},
                "calls_last_7_days": [{"date": "2026-04-18", "count": 6}],
            }
        }
    }


# ── Dashboard schemas ─────────────────────────────────────────────────────────

class DayBucket(BaseModel):
    date: str
    count: int


class OverviewBlock(BaseModel):
    total_calls: int
    booking_rate: float
    avg_margin_pct: Optional[float]
    revenue_captured: float
    avg_call_duration_seconds: float
    avg_time_to_book_seconds: Optional[float]
    calls_by_day: List[DayBucket]
    outcome_breakdown: Dict[str, int]
    sentiment_breakdown: Dict[str, int]


class CarrierSummary(BaseModel):
    mc_number: str
    carrier_name: Optional[str]
    total_calls: int
    booking_rate: float
    avg_rounds: float
    sentiment_score: float
    tier: str
    last_call_at: Optional[datetime]


class DormantCarrier(BaseModel):
    mc_number: str
    carrier_name: Optional[str]
    last_call_at: datetime
    historical_bookings: int
    days_dormant: int


class CarriersBlock(BaseModel):
    carriers: List[CarrierSummary]
    dormant_carriers: List[DormantCarrier]


class LanePricing(BaseModel):
    lane: str
    equipment_type: Optional[str]
    total_calls: int
    avg_final_rate: float
    avg_loadboard_rate: Optional[float]
    avg_margin_pct: Optional[float]


class CounterOfferBucket(BaseModel):
    bucket: str
    count: int


class AcceptRateByRound(BaseModel):
    round: int
    offers_made: int
    accepted: int
    accept_rate: float


class NearMissDeal(BaseModel):
    call_id: str
    mc_number: str
    carrier_name: Optional[str]
    lane: Optional[str]
    loadboard_rate: Optional[float]
    our_last_counter: float
    carrier_last_offer: float
    gap_pct: float
    revenue_lost_estimate: float


class PricingBlock(BaseModel):
    avg_margin_pct_by_equipment: Dict[str, Optional[float]]
    pricing_by_lane: List[LanePricing]
    counter_offer_distribution: List[CounterOfferBucket]
    accept_rate_by_round: List[AcceptRateByRound]
    lost_near_miss: List[NearMissDeal]
    walk_away_rate: float


class RecentCall(BaseModel):
    call_id: str
    received_at: Optional[datetime]
    mc_number: str
    carrier_name: Optional[str]
    outcome: str
    sentiment: str
    lane: Optional[str]
    final_rate: Optional[float]
    duration_seconds: Optional[int]


class QualityBlock(BaseModel):
    unresolved_topics_breakdown: Dict[str, int]
    near_miss_count: int
    walk_away_count: int
    avg_turn_ratio: Optional[float]
    avg_total_turns: float


class DashboardResponse(BaseModel):
    generated_at: datetime
    period_from: str
    period_to: str
    equipment_filter: Optional[str]
    overview: OverviewBlock
    carriers: CarriersBlock
    pricing: PricingBlock
    quality: QualityBlock
    recent_calls: List[RecentCall]

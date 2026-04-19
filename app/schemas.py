from __future__ import annotations

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


# ── Call logging — HappyRobot nested schema (used by POST /log-call) ─────────

class CarrierBlock(BaseModel):
    mc_number: Optional[str] = None
    carrier_name: Optional[str] = None
    dot_number: Optional[str] = None
    eligible: bool
    ineligible_reason: Optional[str] = None


class LoadBlock(BaseModel):
    load_id: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    equipment_type: Optional[str] = None
    loadboard_rate: Optional[float] = None
    miles: Optional[int] = None
    commodity_type: Optional[str] = None
    pickup_datetime: Optional[datetime] = None


class NegotiationRound(BaseModel):
    round: int = Field(ge=1, le=10)
    carrier_offer: Optional[float] = None
    our_counter: Optional[float] = None
    decision: Literal["accept", "counter", "reject"]


class NegotiationBlock(BaseModel):
    initial_carrier_offer: Optional[float] = None
    final_rate: Optional[float] = None
    num_rounds: int = Field(ge=0, default=0)
    rounds_detail: List[NegotiationRound] = []
    walk_away_reason: Optional[str] = None


class ClassificationBlock(BaseModel):
    outcome: Literal[
        "booked", "no_agreement", "carrier_not_eligible",
        "no_loads_found", "carrier_declined", "other"
    ]
    sentiment: Literal["positive", "neutral", "negative"]
    unresolved_topics: List[str] = []
    tool_errors: List[str] = []


class SummaryBlock(BaseModel):
    transcript_summary: Optional[str] = None
    raw_extraction: Dict[str, Any] = {}


class LogCallRequest(BaseModel):
    call_id: str
    started_at: datetime
    ended_at: datetime
    carrier: CarrierBlock
    load: LoadBlock
    negotiation: NegotiationBlock
    classification: ClassificationBlock
    summary: SummaryBlock

    @field_validator("ended_at")
    @classmethod
    def ended_after_started(cls, v: datetime, info: Any) -> datetime:
        if "started_at" in info.data and v < info.data["started_at"]:
            raise ValueError("ended_at must be after started_at")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "call_id": "hr_a1b2c3d4",
                "started_at": "2026-04-19T15:00:00",
                "ended_at": "2026-04-19T15:04:05",
                "carrier": {
                    "mc_number": "MC-123456",
                    "carrier_name": "SWIFT LOGISTICS LLC",
                    "dot_number": "DOT-2001001",
                    "eligible": True,
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
                    "walk_away_reason": None,
                },
                "classification": {
                    "outcome": "booked",
                    "sentiment": "positive",
                    "unresolved_topics": [],
                    "tool_errors": [],
                },
                "summary": {
                    "transcript_summary": "Carrier verified. Pitched Chicago-Atlanta Dry Van at $1,500. Agreed at $1,560 after 1 round.",
                    "raw_extraction": {},
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
    started_at: Optional[datetime]
    mc_number: str
    carrier_name: Optional[str]
    outcome: str
    sentiment: str
    lane: Optional[str]
    final_rate: Optional[float]
    duration_seconds: Optional[int]


class QualityBlock(BaseModel):
    tool_error_rate: float
    tool_errors_by_tool: Dict[str, int]
    unresolved_topics_breakdown: Dict[str, int]
    near_miss_count: int
    walk_away_count: int


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

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

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "load_id": "LD-00001",
                "origin": "Chicago, IL",
                "destination": "Atlanta, GA",
                "pickup_datetime": "2026-04-19T08:00:00",
                "delivery_datetime": "2026-04-20T18:00:00",
                "equipment_type": "Dry Van",
                "loadboard_rate": 1500.0,
                "weight": 38000,
                "commodity_type": "Electronics",
                "num_of_pieces": 22,
                "miles": 716,
                "dimensions": "48x40x60 in",
                "status": "available",
                "notes": None,
                "booked_rate": None,
                "booked_mc": None,
            }
        },
    }


# ── Carrier verification ──────────────────────────────────────────────────────

class VerifyCarrierRequest(BaseModel):
    mc_number: str = Field(
        examples=["MC123456"],
        description="Motor Carrier number. Prefix 'MC', dashes and spaces are stripped automatically.",
    )

    model_config = {
        "json_schema_extra": {"example": {"mc_number": "MC123456"}}
    }


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
    origin: Optional[str] = Field(
        default=None,
        description="City name or 'City, ST'. Matched case-insensitively against the city portion.",
        examples=["Chicago"],
    )
    destination: Optional[str] = Field(
        default=None,
        examples=["Atlanta"],
    )
    equipment_type: Optional[EquipmentType] = Field(
        default=None,
        examples=["Dry Van"],
    )
    pickup_date_from: Optional[date] = Field(
        default=None,
        examples=["2026-04-19"],
    )
    pickup_date_to: Optional[date] = Field(
        default=None,
        examples=["2026-04-26"],
    )
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
    loadboard_rate: float = Field(
        examples=[1500.0],
        description="Published rate for the load. The API uses the value stored in the database — this field is informational only.",
    )
    carrier_offer: float = Field(
        examples=[1700.0],
        description="The rate the carrier is proposing.",
    )
    round: int = Field(
        default=1, ge=1,
        description="Negotiation round number (1–3). Round 3 is the final round.",
        examples=[1],
    )

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
    action: str = Field(description="One of: accept, counter, reject.")
    counter_offer: Optional[float] = None
    message_hint: str = Field(description="Suggested phrasing for the voice agent.")
    should_close: bool = Field(description="True on round 3 rejection — agent should end the negotiation.")

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


# ── Call logging ──────────────────────────────────────────────────────────────

class LogCallRequest(BaseModel):
    id: Optional[str] = Field(
        default=None,
        description="Optional UUID. If provided, used as primary key for idempotency — resending the same id updates the record.",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    mc_number: str = Field(examples=["123456"])
    carrier_name: Optional[str] = Field(default=None, examples=["ACME TRUCKING LLC"])
    load_id: Optional[str] = Field(default=None, examples=["LD-00001"])
    initial_rate: Optional[float] = Field(default=None, examples=[1500.0])
    final_rate: Optional[float] = Field(default=None, examples=[1600.0])
    num_negotiation_rounds: int = Field(default=0, examples=[1])
    outcome: CallOutcome
    sentiment: CallSentiment
    transcript_summary: Optional[str] = Field(
        default=None,
        examples=["Carrier called asking about dry van loads out of Chicago. Agreed on LD-00001 after one counter-offer."],
    )
    raw_extraction: Optional[Any] = Field(
        default=None,
        examples=[{"call_duration_s": 145, "caller_id": "+13125550100"}],
    )

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
                "transcript_summary": "Carrier called asking about dry van loads out of Chicago. Agreed on LD-00001 after one counter-offer.",
                "raw_extraction": {"call_duration_s": 145, "caller_id": "+13125550100"},
            }
        }
    }


class LogCallResponse(BaseModel):
    id: str
    created: bool = Field(description="True if a new record was created; False if an existing record was updated.")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "created": True,
            }
        },
    }


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

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "created_at": "2026-04-18T21:48:11",
                "mc_number": "123456",
                "carrier_name": "ACME TRUCKING LLC",
                "load_id": "LD-00001",
                "initial_rate": 1500.0,
                "final_rate": 1600.0,
                "num_negotiation_rounds": 1,
                "outcome": "booked",
                "sentiment": "positive",
                "transcript_summary": "Carrier agreed after one counter-offer.",
            }
        },
    }


# ── Metrics ───────────────────────────────────────────────────────────────────

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
                "outcome_breakdown": {
                    "booked": 15,
                    "no_agreement": 12,
                    "carrier_not_eligible": 6,
                    "no_loads_found": 5,
                    "carrier_declined": 3,
                    "other": 1,
                },
                "sentiment_breakdown": {
                    "positive": 20,
                    "neutral": 15,
                    "negative": 7,
                },
                "calls_last_7_days": [
                    {"date": "2026-04-12", "count": 4},
                    {"date": "2026-04-13", "count": 7},
                    {"date": "2026-04-14", "count": 5},
                    {"date": "2026-04-15", "count": 6},
                    {"date": "2026-04-16", "count": 8},
                    {"date": "2026-04-17", "count": 6},
                    {"date": "2026-04-18", "count": 6},
                ],
            }
        }
    }

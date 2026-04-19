from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EquipmentType(str, enum.Enum):
    dry_van = "Dry Van"
    reefer = "Reefer"
    flatbed = "Flatbed"
    step_deck = "Step Deck"
    power_only = "Power Only"


class LoadStatus(str, enum.Enum):
    available = "available"
    booked = "booked"


class Load(Base):
    __tablename__ = "loads"

    load_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    origin: Mapped[str] = mapped_column(String(100))
    destination: Mapped[str] = mapped_column(String(100))
    pickup_datetime: Mapped[datetime] = mapped_column(DateTime)
    delivery_datetime: Mapped[datetime] = mapped_column(DateTime)
    equipment_type: Mapped[EquipmentType] = mapped_column(Enum(EquipmentType))
    loadboard_rate: Mapped[float] = mapped_column(Float)
    weight: Mapped[int] = mapped_column(Integer)
    commodity_type: Mapped[str] = mapped_column(String(100))
    num_of_pieces: Mapped[int] = mapped_column(Integer)
    miles: Mapped[int] = mapped_column(Integer)
    dimensions: Mapped[str] = mapped_column(String(50))
    status: Mapped[LoadStatus] = mapped_column(
        Enum(LoadStatus), default=LoadStatus.available
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    booked_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    booked_mc: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)


class CallOutcome(str, enum.Enum):
    booked = "booked"
    no_agreement = "no_agreement"
    carrier_not_eligible = "carrier_not_eligible"
    no_loads_found = "no_loads_found"
    carrier_declined = "carrier_declined"
    other = "other"


class CallSentiment(str, enum.Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Timestamps — received_at is set server-side when the payload arrives
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    num_user_turns: Mapped[int] = mapped_column(Integer, default=0)
    num_assistant_turns: Mapped[int] = mapped_column(Integer, default=0)
    # Carrier identity
    mc_number: Mapped[str] = mapped_column(String(20))
    carrier_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    dot_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    carrier_eligible: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    ineligible_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # Load reference (denormalized for query performance)
    load_id: Mapped[Optional[str]] = mapped_column(
        String(20), ForeignKey("loads.load_id"), nullable=True
    )
    origin: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    destination: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    equipment_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    loadboard_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    miles: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    commodity_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pickup_datetime: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Negotiation
    initial_carrier_offer: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    final_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    num_rounds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rounds_detail: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    walk_away_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Classification
    outcome: Mapped[CallOutcome] = mapped_column(Enum(CallOutcome))
    sentiment: Mapped[CallSentiment] = mapped_column(Enum(CallSentiment))
    unresolved_topics: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # Summaries
    transcript_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_extraction: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # Legacy fields kept for backward-compat with existing /calls/log router
    initial_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    num_negotiation_rounds: Mapped[int] = mapped_column(Integer, default=0)

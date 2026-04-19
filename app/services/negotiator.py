from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from app.config import settings

Action = Literal["accept", "counter", "reject"]


@dataclass(frozen=True)
class NegotiationDecision:
    action: Action
    counter_offer: Optional[float]
    message_hint: str
    should_close: bool


def evaluate(
    loadboard_rate: float,
    carrier_offer: float,
    round_num: int,
) -> NegotiationDecision:
    """Pure function — no I/O, no side effects. Fully testable in isolation.

    Round ceilings tighten over rounds; if the carrier ever meets our rate we
    accept immediately regardless of round.
    """
    if round_num == 1:
        return _round_1(loadboard_rate, carrier_offer)
    if round_num == 2:
        return _round_2(loadboard_rate, carrier_offer)
    if round_num >= settings.MAX_ROUNDS:
        return _round_final(loadboard_rate, carrier_offer)

    # Unexpected round — treat as final
    return _round_final(loadboard_rate, carrier_offer)


# ── Round helpers ─────────────────────────────────────────────────────────────

def _round_1(rate: float, offer: float) -> NegotiationDecision:
    ceiling = rate * (1 + settings.ROUND1_CEILING_PCT)

    if offer <= rate:
        return NegotiationDecision(
            action="accept",
            counter_offer=None,
            message_hint=f"That works for us. We'll confirm at ${offer:,.2f}.",
            should_close=True,
        )

    our_counter = _fmt(rate * (1 + settings.ROUND1_COUNTER_PCT))

    if offer > ceiling:
        return NegotiationDecision(
            action="counter",
            counter_offer=our_counter,
            message_hint=(
                f"We appreciate the offer, but ${offer:,.2f} is above our range. "
                f"We can do ${our_counter:,.2f}."
            ),
            should_close=False,
        )

    # Offer is between loadboard rate and ceiling — split the difference
    midpoint = _fmt((rate + offer) / 2)
    return NegotiationDecision(
        action="counter",
        counter_offer=midpoint,
        message_hint=(
            f"We're close. We can meet you halfway at ${midpoint:,.2f}."
        ),
        should_close=False,
    )


def _round_2(rate: float, offer: float) -> NegotiationDecision:
    ceiling = rate * (1 + settings.ROUND2_CEILING_PCT)

    if offer <= rate:
        return NegotiationDecision(
            action="accept",
            counter_offer=None,
            message_hint=f"Deal. We'll lock it in at ${offer:,.2f}.",
            should_close=True,
        )

    # Reference point: what we countered in round 1
    r1_counter = rate * (1 + settings.ROUND1_COUNTER_PCT)

    # Move BLEND_RATIO of the way from our r1 counter toward carrier's offer,
    # but never exceed the tighter ceiling
    blend = r1_counter + settings.ROUND2_BLEND_RATIO * (offer - r1_counter)
    our_counter = _fmt(min(blend, ceiling))

    if offer > ceiling:
        return NegotiationDecision(
            action="counter",
            counter_offer=our_counter,
            message_hint=(
                f"We've moved as far as we can. Our best is ${our_counter:,.2f} — "
                "this is our final position before we have to walk away."
            ),
            should_close=False,
        )

    return NegotiationDecision(
        action="counter",
        counter_offer=our_counter,
        message_hint=(
            f"We can come up to ${our_counter:,.2f}. That's the best we can do."
        ),
        should_close=False,
    )


def _round_final(rate: float, offer: float) -> NegotiationDecision:
    accept_ceiling = rate * (1 + settings.ROUND3_ACCEPT_PCT)

    if offer <= accept_ceiling:
        return NegotiationDecision(
            action="accept",
            counter_offer=None,
            message_hint=f"Alright, we'll accept ${offer:,.2f}. Let's get this booked.",
            should_close=True,
        )

    return NegotiationDecision(
        action="reject",
        counter_offer=None,
        message_hint=(
            "Unfortunately we're too far apart on rate. "
            "We'll have to pass on this one — hope to work together soon."
        ),
        should_close=True,
    )


def _fmt(value: float) -> float:
    """Round to nearest dollar for cleaner counter-offers."""
    return round(value, 2)

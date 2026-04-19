"""Transcript summary templates for each call outcome."""

from __future__ import annotations

import random
from typing import Optional


# ── booked ─────────────────────────────────────────────────────────────────────

def _booked_zero_rounds(
    rng: random.Random, name: str, lane: str, eq: str, rate: float
) -> str:
    templates = [
        f"Carrier {name} verified and eligible. Pitched {lane} {eq} load at ${rate:,.0f}. "
        f"Carrier accepted our posted rate outright. Booking transferred to rep.",

        f"Verified {name} — active authority, clean safety rating. {eq} load {lane} at "
        f"${rate:,.0f} posted; carrier agreed immediately with no counter. Transfer initiated.",

        f"{name} called in looking for loads in that lane. Verified eligible, offered {eq} "
        f"at ${rate:,.0f} for {lane}. Carrier took it on the spot — no negotiation needed. Done.",
    ]
    return rng.choice(templates)


def _booked_multi_rounds(
    rng: random.Random,
    name: str,
    lane: str,
    eq: str,
    rate: float,
    first_offer: float,
    final: float,
    rounds: int,
) -> str:
    gap_pct = round((first_offer - rate) / rate * 100, 1)
    diff = round(final - rate, 0)
    templates = [
        f"Carrier {name} verified. Countered at ${first_offer:,.0f} on {lane} {eq} load "
        f"(${gap_pct}% over our ${rate:,.0f}). Agreed at ${final:,.0f} after {rounds} round(s). "
        f"Booking transferred to rep.",

        f"Verified {name} ({eq}, {lane}). Opened at ${first_offer:,.0f}, we held near posted "
        f"rate ${rate:,.0f}. Settled at ${final:,.0f} (+${diff:.0f}) after {rounds} round(s). "
        f"Deal confirmed, transfer done.",

        f"{name} pushed back to ${first_offer:,.0f} on our ${rate:,.0f} post for {lane}. "
        f"Negotiated {rounds} round(s) and closed at ${final:,.0f}. Carrier satisfied, "
        f"booking initiated.",
    ]
    return rng.choice(templates)


# ── no_agreement ───────────────────────────────────────────────────────────────

def _no_agreement(
    rng: random.Random,
    name: str,
    lane: str,
    eq: str,
    rate: float,
    first_offer: float,
    last_offer: float,
) -> str:
    gap_pct = round((first_offer - rate) / rate * 100, 1)
    diff = round(last_offer - rate, 0)
    templates = [
        f"Carrier {name} pushed for ${first_offer:,.0f} on {lane} {eq} load — {gap_pct}% "
        f"over our ${rate:,.0f} post. No agreement after 3 rounds. Carrier ended call neutral.",

        f"{name} countered at ${first_offer:,.0f} for {lane} {eq}. After 3 rounds we were "
        f"still ${diff:.0f} apart. Carrier declined to come down further, call ended.",

        f"Could not close {name} on {lane} {eq} at our rate of ${rate:,.0f}. Carrier's "
        f"best offer was ${last_offer:,.0f} — above our margin ceiling. Ended after 3 rounds.",
    ]
    return rng.choice(templates)


# ── carrier_not_eligible ───────────────────────────────────────────────────────

def _carrier_not_eligible(
    rng: random.Random, mc: str, name: str, reason: str, duration: int
) -> str:
    templates = [
        f"Carrier MC {mc} not authorized to operate per FMCSA — {reason}. "
        f"Informed carrier politely and ended call in {duration}s.",

        f"Verified {name} (MC {mc}) — flagged ineligible: {reason}. "
        f"No load pitched. Call ended after {duration}s.",

        f"Authority check failed for MC {mc}: {reason}. "
        f"Informed carrier and terminated call after {duration}s. No load offered.",
    ]
    return rng.choice(templates)


# ── no_loads_found ─────────────────────────────────────────────────────────────

def _no_loads_found(
    rng: random.Random,
    name: str,
    eq: Optional[str],
    lane: Optional[str],
) -> str:
    eq_str = eq or "requested equipment"
    lane_str = lane or "requested area"
    templates = [
        f"Carrier {name} verified and eligible. No matching {eq_str} loads found for "
        f"{lane_str}. Offered to follow up when inventory posts.",

        f"Verified {name} — active authority confirmed. Searched for {eq_str} loads in "
        f"{lane_str}, no available inventory at this time. Offered callback when loads post.",

        f"{name} called looking for {eq_str} loads. Carrier fully eligible. Inventory "
        f"search returned no matches for {lane_str}. Will contact carrier when loads available.",
    ]
    return rng.choice(templates)


# ── carrier_declined ───────────────────────────────────────────────────────────

def _carrier_declined(
    rng: random.Random,
    name: str,
    lane: str,
    eq: str,
    rate: float,
    topics: list[str],
) -> str:
    topic_str = topics[0] if topics else "route requirements"
    templates = [
        f"Carrier {name} verified, pitched {lane} {eq} load at ${rate:,.0f}. "
        f"Carrier declined — cited {topic_str} as reason. Call ended without negotiation.",

        f"Posted {lane} {eq} at ${rate:,.0f} to {name}. Carrier passed — {topic_str} "
        f"cited as main objection. No counter offered.",

        f"{name} was not interested in {lane} {eq} load (${rate:,.0f}). "
        f"Stated {topic_str} as reason for declining. No negotiation attempted.",
    ]
    return rng.choice(templates)


# ── other ──────────────────────────────────────────────────────────────────────

def _other(rng: random.Random, name: str) -> str:
    templates = [
        f"Carrier {name} called in. Call did not follow standard flow — outcome "
        f"categorized as other. No load booked.",

        f"{name} reached out but call ended inconclusively. Logged for review.",

        f"Inbound call from {name}. Interaction did not result in a standard outcome. "
        f"Agent escalated for follow-up.",
    ]
    return rng.choice(templates)


# ── Public entry point ─────────────────────────────────────────────────────────

def make_summary(
    rng: random.Random,
    outcome: str,
    carrier_name: str,
    mc_number: str,
    lane: Optional[str],
    equipment_type: Optional[str],
    loadboard_rate: Optional[float],
    initial_carrier_offer: Optional[float],
    final_rate: Optional[float],
    num_rounds: int,
    duration: int,
    unresolved_topics: list[str],
    ineligible_reason: Optional[str] = None,
) -> str:
    eq = equipment_type or "Dry Van"
    lane_s = lane or "unknown lane"

    if outcome == "booked":
        if num_rounds == 0:
            return _booked_zero_rounds(rng, carrier_name, lane_s, eq, loadboard_rate or 0)
        return _booked_multi_rounds(
            rng,
            carrier_name,
            lane_s,
            eq,
            loadboard_rate or 0,
            initial_carrier_offer or 0,
            final_rate or 0,
            num_rounds,
        )

    if outcome == "no_agreement":
        last_offer = initial_carrier_offer or 0
        return _no_agreement(
            rng, carrier_name, lane_s, eq, loadboard_rate or 0, initial_carrier_offer or 0, last_offer
        )

    if outcome == "carrier_not_eligible":
        reason = ineligible_reason or "authority inactive per FMCSA"
        return _carrier_not_eligible(rng, mc_number, carrier_name, reason, duration)

    if outcome == "no_loads_found":
        return _no_loads_found(rng, carrier_name, equipment_type, lane)

    if outcome == "carrier_declined":
        return _carrier_declined(
            rng, carrier_name, lane_s, eq, loadboard_rate or 0, unresolved_topics
        )

    return _other(rng, carrier_name)

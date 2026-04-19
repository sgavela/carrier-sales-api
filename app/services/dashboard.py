"""Pure compute functions for GET /dashboard. All take list[dict], return plain dicts."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Optional


# ── Sentiment helpers ─────────────────────────────────────────────────────────

_SENTIMENT_SCORE = {"positive": 1, "neutral": 0, "negative": -1}


def _score(sentiment: Optional[str]) -> int:
    return _SENTIMENT_SCORE.get(sentiment or "neutral", 0)


# ── Near-miss detection (shared between pricing and quality) ──────────────────

def _find_near_misses(calls: list[dict]) -> list[dict]:
    """Return near-miss no_agreement calls: last carrier_offer within 3% of our_counter."""
    result = []
    for c in calls:
        if c.get("outcome") != "no_agreement":
            continue
        rounds = c.get("rounds_detail") or []
        if not rounds:
            continue
        last = rounds[-1]
        co = last.get("carrier_offer")
        oc = last.get("our_counter")
        if co is None or oc is None or oc <= 0:
            continue
        gap = (co - oc) / oc
        if gap < 0.03:
            lane = None
            if c.get("origin") and c.get("destination"):
                lane = f"{c['origin']} → {c['destination']}"
            result.append({
                "call_id": c.get("id", ""),
                "mc_number": c.get("mc_number", ""),
                "carrier_name": c.get("carrier_name"),
                "lane": lane,
                "loadboard_rate": c.get("loadboard_rate"),
                "our_last_counter": round(oc, 2),
                "carrier_last_offer": round(co, 2),
                "gap_pct": round(gap * 100, 2),
                "revenue_lost_estimate": round(oc * 1.03, 2),
            })
    return result


# ── Overview ──────────────────────────────────────────────────────────────────

def compute_overview(
    calls: list[dict], date_from: date, date_to: date
) -> dict:
    total = len(calls)
    booked = [c for c in calls if c.get("outcome") == "booked"]

    booking_rate = round(len(booked) / total, 4) if total else 0.0

    margins = [
        (c["final_rate"] - c["loadboard_rate"]) / c["loadboard_rate"]
        for c in booked
        if c.get("final_rate") and c.get("loadboard_rate")
    ]
    avg_margin_pct = round(sum(margins) / len(margins), 4) if margins else None

    revenue_captured = round(
        sum(c["final_rate"] for c in booked if c.get("final_rate")), 2
    )

    durations = [
        (c["ended_at"] - c["started_at"]).total_seconds()
        for c in calls
        if c.get("started_at") and c.get("ended_at")
        and (c["ended_at"] - c["started_at"]).total_seconds() > 0
    ]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0.0

    book_durations = [
        (c["ended_at"] - c["started_at"]).total_seconds()
        for c in booked
        if c.get("started_at") and c.get("ended_at")
        and (c["ended_at"] - c["started_at"]).total_seconds() > 0
    ]
    avg_time_to_book = round(sum(book_durations) / len(book_durations), 1) if book_durations else None

    # calls_by_day: all days in range, fill zeros
    by_day: Counter = Counter()
    for c in calls:
        ts = c.get("started_at")
        if ts:
            by_day[ts.strftime("%Y-%m-%d")] += 1

    calls_by_day = []
    d = date_from
    while d <= date_to:
        calls_by_day.append({"date": d.strftime("%Y-%m-%d"), "count": by_day.get(d.strftime("%Y-%m-%d"), 0)})
        d += timedelta(days=1)

    outcome_counts: dict[str, int] = dict(Counter(c.get("outcome", "other") for c in calls))
    sentiment_counts: dict[str, int] = dict(Counter(c.get("sentiment", "neutral") for c in calls))

    return {
        "total_calls": total,
        "booking_rate": booking_rate,
        "avg_margin_pct": avg_margin_pct,
        "revenue_captured": revenue_captured,
        "avg_call_duration_seconds": avg_duration,
        "avg_time_to_book_seconds": avg_time_to_book,
        "calls_by_day": calls_by_day,
        "outcome_breakdown": outcome_counts,
        "sentiment_breakdown": sentiment_counts,
    }


# ── Carriers ──────────────────────────────────────────────────────────────────

def compute_carriers(calls: list[dict], now: Optional[datetime] = None) -> dict:
    if now is None:
        now = datetime.utcnow()

    dormant_cutoff = now - timedelta(days=25)

    by_mc: dict[str, list[dict]] = defaultdict(list)
    for c in calls:
        mc = c.get("mc_number") or ""
        if mc:
            by_mc[mc].append(c)

    carriers = []
    for mc, mc_calls in by_mc.items():
        total = len(mc_calls)
        booked_n = sum(1 for c in mc_calls if c.get("outcome") == "booked")
        booking_rate = round(booked_n / total, 4) if total else 0.0

        avg_rounds = round(
            sum(c.get("num_rounds") or 0 for c in mc_calls) / total, 2
        )

        scores = [_score(c.get("sentiment")) for c in mc_calls]
        avg_sentiment = round(sum(scores) / len(scores), 3)

        has_ineligible = any(c.get("carrier_eligible") is False for c in mc_calls)

        # Tier: evaluate in order A → B → C → D
        if total >= 3 and booking_rate > 0.5 and avg_sentiment > 0.3:
            tier = "A"
        elif total >= 2 and booking_rate > 0.3:
            tier = "B"
        elif avg_rounds >= 2.5 or booking_rate < 0.3:
            tier = "C"
        elif has_ineligible:
            tier = "D"
        else:
            tier = "C"  # fallback

        last_call = max(
            (c["started_at"] for c in mc_calls if c.get("started_at")),
            default=None,
        )

        carriers.append({
            "mc_number": mc,
            "carrier_name": mc_calls[0].get("carrier_name"),
            "total_calls": total,
            "booking_rate": booking_rate,
            "avg_rounds": avg_rounds,
            "sentiment_score": avg_sentiment,
            "tier": tier,
            "last_call_at": last_call,
        })

    # Dormant: last call > 25 days ago AND ≥2 bookings within the provided call set
    dormant = []
    for c in carriers:
        last = c["last_call_at"]
        if last and last < dormant_cutoff:
            historical_bookings = sum(
                1 for call in by_mc[c["mc_number"]] if call.get("outcome") == "booked"
            )
            if historical_bookings >= 2:
                dormant.append({
                    "mc_number": c["mc_number"],
                    "carrier_name": c["carrier_name"],
                    "last_call_at": last,
                    "historical_bookings": historical_bookings,
                    "days_dormant": (now - last).days,
                })

    return {
        "carriers": sorted(carriers, key=lambda x: -x["total_calls"]),
        "dormant_carriers": dormant,
    }


# ── Pricing ───────────────────────────────────────────────────────────────────

def compute_pricing(calls: list[dict]) -> dict:
    # avg margin by equipment (booked only)
    by_eq: dict[str, list[float]] = defaultdict(list)
    for c in calls:
        if (
            c.get("outcome") == "booked"
            and c.get("final_rate")
            and c.get("loadboard_rate")
            and c.get("equipment_type")
        ):
            margin = (c["final_rate"] - c["loadboard_rate"]) / c["loadboard_rate"]
            by_eq[c["equipment_type"]].append(margin)

    avg_margin_by_eq = {
        eq: round(sum(ms) / len(ms), 4) for eq, ms in by_eq.items()
    }

    # Pricing by lane (booked calls with origin + destination)
    by_lane: dict[str, list[dict]] = defaultdict(list)
    for c in calls:
        if c.get("outcome") == "booked" and c.get("origin") and c.get("destination"):
            by_lane[f"{c['origin']} → {c['destination']}"].append(c)

    pricing_by_lane = []
    for lane, lc in by_lane.items():
        final_rates = [c["final_rate"] for c in lc if c.get("final_rate")]
        lb_rates = [c["loadboard_rate"] for c in lc if c.get("loadboard_rate")]
        margins = [
            (c["final_rate"] - c["loadboard_rate"]) / c["loadboard_rate"]
            for c in lc
            if c.get("final_rate") and c.get("loadboard_rate")
        ]
        if final_rates:
            eq_types = [c["equipment_type"] for c in lc if c.get("equipment_type")]
            pricing_by_lane.append({
                "lane": lane,
                "equipment_type": eq_types[0] if eq_types else None,
                "total_calls": len(lc),
                "avg_final_rate": round(sum(final_rates) / len(final_rates), 2),
                "avg_loadboard_rate": round(sum(lb_rates) / len(lb_rates), 2) if lb_rates else None,
                "avg_margin_pct": round(sum(margins) / len(margins), 4) if margins else None,
            })

    # Counter-offer gap distribution
    buckets: dict[str, int] = {"<0": 0, "0-5": 0, "5-10": 0, "10-15": 0, "15+": 0}
    for c in calls:
        ico = c.get("initial_carrier_offer")
        lb = c.get("loadboard_rate")
        if ico is not None and lb and lb > 0:
            gap_pct = (ico - lb) / lb * 100
            if gap_pct < 0:
                buckets["<0"] += 1
            elif gap_pct < 5:
                buckets["0-5"] += 1
            elif gap_pct < 10:
                buckets["5-10"] += 1
            elif gap_pct < 15:
                buckets["10-15"] += 1
            else:
                buckets["15+"] += 1

    counter_offer_dist = [{"bucket": k, "count": v} for k, v in buckets.items()]

    # Accept rate by round (requires decision field in rounds_detail)
    round_stats: dict[int, dict[str, int]] = {
        1: {"offers": 0, "accepted": 0},
        2: {"offers": 0, "accepted": 0},
        3: {"offers": 0, "accepted": 0},
    }
    for c in calls:
        for r in c.get("rounds_detail") or []:
            rn = r.get("round")
            if rn in round_stats:
                round_stats[rn]["offers"] += 1
                if r.get("decision") == "accept":
                    round_stats[rn]["accepted"] += 1

    accept_rate_by_round = [
        {
            "round": rn,
            "offers_made": s["offers"],
            "accepted": s["accepted"],
            "accept_rate": round(s["accepted"] / s["offers"], 4) if s["offers"] else 0.0,
        }
        for rn, s in sorted(round_stats.items())
    ]

    near_misses = _find_near_misses(calls)
    walk_away_count = sum(1 for c in calls if c.get("walk_away_reason"))
    total = len(calls)
    walk_away_rate = round(walk_away_count / total, 4) if total else 0.0

    return {
        "avg_margin_pct_by_equipment": avg_margin_by_eq,
        "pricing_by_lane": sorted(pricing_by_lane, key=lambda x: -x["total_calls"]),
        "counter_offer_distribution": counter_offer_dist,
        "accept_rate_by_round": accept_rate_by_round,
        "lost_near_miss": near_misses,
        "walk_away_rate": walk_away_rate,
    }


# ── Quality ───────────────────────────────────────────────────────────────────

def compute_quality(calls: list[dict]) -> dict:
    total = len(calls)
    errors_by_tool: Counter = Counter()
    error_calls = 0

    for c in calls:
        errors = c.get("tool_errors") or []
        if errors:
            error_calls += 1
            for tool in errors:
                errors_by_tool[tool] += 1

    topic_counts: Counter = Counter()
    for c in calls:
        for t in c.get("unresolved_topics") or []:
            topic_counts[t] += 1

    near_misses = _find_near_misses(calls)
    walk_away_count = sum(1 for c in calls if c.get("walk_away_reason"))

    return {
        "tool_error_rate": round(error_calls / total, 4) if total else 0.0,
        "tool_errors_by_tool": dict(errors_by_tool),
        "unresolved_topics_breakdown": dict(topic_counts),
        "near_miss_count": len(near_misses),
        "walk_away_count": walk_away_count,
    }


# ── Recent calls ──────────────────────────────────────────────────────────────

def get_recent_calls(calls: list[dict], limit: int = 20) -> list[dict]:
    sorted_calls = sorted(
        calls,
        key=lambda c: c.get("started_at") or datetime.min,
        reverse=True,
    )[:limit]

    result = []
    for c in sorted_calls:
        started = c.get("started_at")
        ended = c.get("ended_at")
        duration = (
            int((ended - started).total_seconds())
            if started and ended and ended > started
            else None
        )
        lane = None
        if c.get("origin") and c.get("destination"):
            lane = f"{c['origin']} → {c['destination']}"
        result.append({
            "call_id": c.get("id", ""),
            "started_at": started,
            "mc_number": c.get("mc_number", ""),
            "carrier_name": c.get("carrier_name"),
            "outcome": c.get("outcome", "other"),
            "sentiment": c.get("sentiment", "neutral"),
            "lane": lane,
            "final_rate": c.get("final_rate"),
            "duration_seconds": duration,
        })
    return result

"""Pure compute functions for GET /dashboard. All take list[dict], return plain dicts."""

from __future__ import annotations

import statistics
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
    booked_calls = [c for c in calls if c.get("outcome") == "booked"]
    booked_count = len(booked_calls)

    booking_rate = round(booked_count / total, 4) if total else 0.0

    margins = [
        (c["final_rate"] - c["loadboard_rate"]) / c["loadboard_rate"]
        for c in booked_calls
        if c.get("final_rate") and c.get("loadboard_rate")
    ]
    avg_margin_pct = round(sum(margins) / len(margins), 4) if margins else None

    revenue_captured = round(
        sum(c["final_rate"] for c in booked_calls if c.get("final_rate")), 2
    )

    durations = [
        c["duration_seconds"]
        for c in calls
        if c.get("duration_seconds") and c["duration_seconds"] > 0
    ]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0.0

    book_durations = [
        c["duration_seconds"]
        for c in booked_calls
        if c.get("duration_seconds") and c["duration_seconds"] > 0
    ]
    avg_time_to_book = round(sum(book_durations) / len(book_durations), 1) if book_durations else None

    # calls_by_day with booked split
    by_day_total: Counter = Counter()
    by_day_booked: Counter = Counter()
    for c in calls:
        ts = c.get("received_at")
        if ts:
            day_str = ts.strftime("%Y-%m-%d")
            by_day_total[day_str] += 1
            if c.get("outcome") == "booked":
                by_day_booked[day_str] += 1

    calls_by_day = []
    d = date_from
    while d <= date_to:
        day_str = d.strftime("%Y-%m-%d")
        calls_by_day.append({
            "date": day_str,
            "count": by_day_total.get(day_str, 0),
            "booked": by_day_booked.get(day_str, 0),
        })
        d += timedelta(days=1)

    outcome_counts: dict[str, int] = dict(Counter(c.get("outcome", "other") for c in calls))
    sentiment_counts: dict[str, int] = dict(Counter(c.get("sentiment", "neutral") for c in calls))

    return {
        "total_calls": total,
        "booked": booked_count,
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
    tier_counts: Counter = Counter()

    for mc, mc_calls in by_mc.items():
        total = len(mc_calls)
        booked_calls = [c for c in mc_calls if c.get("outcome") == "booked"]
        booked_n = len(booked_calls)
        booking_rate = round(booked_n / total, 4) if total else 0.0

        avg_rounds = round(
            sum(c.get("num_rounds") or 0 for c in mc_calls) / total, 2
        )

        scores = [_score(c.get("sentiment")) for c in mc_calls]
        avg_sentiment = round(sum(scores) / len(scores), 3)

        margins = [
            (c["final_rate"] - c["loadboard_rate"]) / c["loadboard_rate"]
            for c in booked_calls
            if c.get("final_rate") and c.get("loadboard_rate")
        ]
        avg_margin_pct = round(sum(margins) / len(margins), 4) if margins else None

        has_ineligible = any(c.get("carrier_eligible") is False for c in mc_calls)

        if total >= 3 and booking_rate > 0.5 and avg_sentiment > 0.3:
            tier = "A"
        elif total >= 2 and booking_rate > 0.3:
            tier = "B"
        elif avg_rounds >= 2.5 or booking_rate < 0.3:
            tier = "C"
        elif has_ineligible:
            tier = "D"
        else:
            tier = "C"

        tier_counts[tier] += 1

        last_call = max(
            (c["received_at"] for c in mc_calls if c.get("received_at")),
            default=None,
        )

        carriers.append({
            "mc_number": mc,
            "carrier_name": mc_calls[0].get("carrier_name"),
            "total_calls": total,
            "bookings": booked_n,
            "booking_rate": booking_rate,
            "avg_rounds": avg_rounds,
            "avg_margin_pct": avg_margin_pct,
            "sentiment_score": avg_sentiment,
            "tier": tier,
            "last_call_at": last_call,
        })

    # repeat vs new: carriers with >1 call are "repeat"
    repeat_mcs = {mc for mc, mc_calls in by_mc.items() if len(mc_calls) > 1}
    repeat_calls = sum(len(by_mc[mc]) for mc in repeat_mcs)
    new_caller_calls = sum(len(mc_calls) for mc, mc_calls in by_mc.items() if mc not in repeat_mcs)

    # dormant: last call > 25 days ago AND ≥2 bookings
    dormant = []
    for c in carriers:
        last = c["last_call_at"]
        if last and last < dormant_cutoff:
            mc_calls = by_mc[c["mc_number"]]
            booked_calls = [call for call in mc_calls if call.get("outcome") == "booked"]
            historical_bookings = len(booked_calls)
            if historical_bookings >= 2:
                historical_revenue = round(
                    sum(call["final_rate"] for call in booked_calls if call.get("final_rate")), 2
                )
                margins = [
                    (call["final_rate"] - call["loadboard_rate"]) / call["loadboard_rate"]
                    for call in booked_calls
                    if call.get("final_rate") and call.get("loadboard_rate")
                ]
                avg_margin_pct = round(sum(margins) / len(margins), 4) if margins else None
                dormant.append({
                    "mc_number": c["mc_number"],
                    "carrier_name": c["carrier_name"],
                    "last_call_at": last,
                    "historical_bookings": historical_bookings,
                    "historical_revenue": historical_revenue,
                    "avg_margin_pct": avg_margin_pct,
                    "days_dormant": (now - last).days,
                })

    return {
        "carriers": sorted(carriers, key=lambda x: -x["total_calls"]),
        "tier_distribution": dict(tier_counts),
        "repeat_vs_new": {"repeat_calls": repeat_calls, "new_caller_calls": new_caller_calls},
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

    # Pricing by lane: count all calls and booked calls per lane
    by_lane_all: dict[str, list[dict]] = defaultdict(list)
    by_lane_booked: dict[str, list[dict]] = defaultdict(list)
    for c in calls:
        if c.get("origin") and c.get("destination"):
            lane_key = f"{c['origin']} → {c['destination']}"
            by_lane_all[lane_key].append(c)
            if c.get("outcome") == "booked":
                by_lane_booked[lane_key].append(c)

    pricing_by_lane = []
    for lane, all_lc in by_lane_all.items():
        booked_lc = by_lane_booked.get(lane, [])
        final_rates = [c["final_rate"] for c in booked_lc if c.get("final_rate")]
        lb_rates = [c["loadboard_rate"] for c in booked_lc if c.get("loadboard_rate")]
        margins = [
            (c["final_rate"] - c["loadboard_rate"]) / c["loadboard_rate"]
            for c in booked_lc
            if c.get("final_rate") and c.get("loadboard_rate")
        ]
        eq_types = [c["equipment_type"] for c in all_lc if c.get("equipment_type")]
        pricing_by_lane.append({
            "lane": lane,
            "equipment_type": eq_types[0] if eq_types else None,
            "calls": len(all_lc),
            "bookings": len(booked_lc),
            "avg_final_rate": round(sum(final_rates) / len(final_rates), 2) if final_rates else 0.0,
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

    # Accept rate by round
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
        "pricing_by_lane": sorted(pricing_by_lane, key=lambda x: -x["calls"]),
        "counter_offer_distribution": counter_offer_dist,
        "accept_rate_by_round": accept_rate_by_round,
        "lost_near_miss": near_misses,
        "walk_away_rate": walk_away_rate,
    }


# ── Quality ───────────────────────────────────────────────────────────────────

def compute_quality(calls: list[dict]) -> dict:
    total = len(calls)

    # Duration by outcome
    by_outcome: dict[str, list[float]] = defaultdict(list)
    for c in calls:
        outcome = c.get("outcome")
        dur = c.get("duration_seconds")
        if outcome and dur and dur > 0:
            by_outcome[outcome].append(float(dur))

    duration_by_outcome = [
        {
            "outcome": outcome,
            "avg_seconds": round(sum(durs) / len(durs), 1),
            "median_seconds": round(statistics.median(durs), 1),
        }
        for outcome, durs in sorted(by_outcome.items())
    ]

    # Rounds distribution (num_rounds column: 0, 1, 2, 3+)
    rounds_dist = {"0_rounds": 0, "1_round": 0, "2_rounds": 0, "3_rounds": 0}
    for c in calls:
        nr = c.get("num_rounds") or 0
        if nr == 0:
            rounds_dist["0_rounds"] += 1
        elif nr == 1:
            rounds_dist["1_round"] += 1
        elif nr == 2:
            rounds_dist["2_rounds"] += 1
        else:
            rounds_dist["3_rounds"] += 1

    # Unresolved topics
    topic_counts: Counter = Counter()
    for c in calls:
        for t in c.get("unresolved_topics") or []:
            topic_counts[t] += 1

    # Sentiment breakdown for booked calls only
    booked_sentiments = [c.get("sentiment", "neutral") for c in calls if c.get("outcome") == "booked"]
    sentiment_on_booked = dict(Counter(booked_sentiments))

    near_misses = _find_near_misses(calls)
    walk_away_count = sum(1 for c in calls if c.get("walk_away_reason"))

    # Conversational turn KPIs
    ratios = [
        c["num_assistant_turns"] / c["num_user_turns"]
        for c in calls
        if c.get("num_user_turns") and c["num_user_turns"] > 0
        and c.get("num_assistant_turns") is not None
    ]
    avg_turn_ratio = round(sum(ratios) / len(ratios), 3) if ratios else None

    total_turns_list = [
        (c.get("num_user_turns") or 0) + (c.get("num_assistant_turns") or 0)
        for c in calls
    ]
    avg_total_turns = round(sum(total_turns_list) / total, 1) if total else 0.0

    return {
        "duration_by_outcome": duration_by_outcome,
        "rounds_distribution": rounds_dist,
        "unresolved_topics_breakdown": dict(topic_counts),
        "sentiment_on_booked_transfer": sentiment_on_booked,
        "near_miss_count": len(near_misses),
        "walk_away_count": walk_away_count,
        "avg_turn_ratio": avg_turn_ratio,
        "avg_total_turns": avg_total_turns,
    }


# ── Recent calls ──────────────────────────────────────────────────────────────

def get_recent_calls(calls: list[dict], limit: int = 20) -> list[dict]:
    sorted_calls = sorted(
        calls,
        key=lambda c: c.get("received_at") or datetime.min,
        reverse=True,
    )[:limit]

    result = []
    for c in sorted_calls:
        lane = None
        if c.get("origin") and c.get("destination"):
            lane = f"{c['origin']} → {c['destination']}"
        result.append({
            "call_id": c.get("id", ""),
            "received_at": c.get("received_at"),
            "mc_number": c.get("mc_number", ""),
            "carrier_name": c.get("carrier_name"),
            "outcome": c.get("outcome", "other"),
            "sentiment": c.get("sentiment", "neutral"),
            "lane": lane,
            "load_id": c.get("load_id"),
            "final_rate": c.get("final_rate"),
            "duration_seconds": c.get("duration_seconds"),
        })
    return result

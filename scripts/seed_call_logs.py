"""
Seed ~150 realistic call_log rows for dashboard testing.

Usage:
  python -m scripts.seed_call_logs            # seed if ≤10 rows exist
  python -m scripts.seed_call_logs --force    # truncate and repopulate
  python -m scripts.seed_call_logs --count 300
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import random

from sqlalchemy import text

import app.db as _app_db
from app.db import Base, init_db
from app.models import CallLog, CallOutcome, CallSentiment, Load

from scripts._fixtures.carriers import CARRIERS
from scripts._fixtures.summaries import make_summary

# ── Reproducibility ────────────────────────────────────────────────────────────

SEED_VALUE = 42

# ── Time window ────────────────────────────────────────────────────────────────

TODAY = datetime(2026, 4, 19, 0, 0, 0)
WINDOW_DAYS = 30
BASE_DATE = TODAY - timedelta(days=WINDOW_DAYS)  # 2026-03-20

# Dormant carriers must have all calls in first DORMANT_MAX_DAY days of window
# so that last call is >25 days before TODAY (i.e., before 2026-03-25)
DORMANT_MAX_DAY = 4  # days 0-3 → dates 2026-03-20 to 2026-03-23

# ── Outcome distribution ───────────────────────────────────────────────────────
# These are exact integer targets for 150 total calls.
# Dormant calls (15) contribute: 10 booked + 5 other
# Non-dormant calls (135) make up the rest.

TOTAL_COUNT = 150

# Full distribution targets
OUTCOME_TARGETS_FULL = {
    "booked":               39,
    "no_agreement":         45,
    "no_loads_found":       25,
    "carrier_not_eligible": 20,
    "carrier_declined":     15,
    "other":                 6,
}
assert sum(OUTCOME_TARGETS_FULL.values()) == TOTAL_COUNT

# Non-dormant slice (135 calls): dormant contributes 10 booked + 5 other
OUTCOME_TARGETS_NONDORMANT = {
    "booked":               29,
    "no_agreement":         45,
    "no_loads_found":       25,
    "carrier_not_eligible": 20,
    "carrier_declined":     15,
    "other":                 1,
}
assert sum(OUTCOME_TARGETS_NONDORMANT.values()) == 135

# ── Call duration params (mean, sigma) seconds ────────────────────────────────

DURATION_PARAMS: dict[str, tuple[float, float]] = {
    "booked":               (245, 60),
    "no_agreement":         (410, 90),
    "carrier_not_eligible": (85,  20),
    "no_loads_found":       (130, 40),
    "carrier_declined":     (180, 50),
    "other":                (200, 80),
}

# ── Sentiment weights per outcome ─────────────────────────────────────────────

SENTIMENT_WEIGHTS: dict[str, list[tuple[str, float]]] = {
    "booked":               [("positive", 0.60), ("neutral", 0.35), ("negative", 0.05)],
    "no_agreement":         [("positive", 0.15), ("neutral", 0.50), ("negative", 0.35)],
    "carrier_not_eligible": [("positive", 0.05), ("neutral", 0.70), ("negative", 0.25)],
    "no_loads_found":       [("positive", 0.30), ("neutral", 0.55), ("negative", 0.15)],
    "carrier_declined":     [("positive", 0.20), ("neutral", 0.55), ("negative", 0.25)],
    "other":                [("positive", 0.25), ("neutral", 0.50), ("negative", 0.25)],
}

# ── Equipment margin adjustments ──────────────────────────────────────────────
# For num_rounds>0 booked calls, target final_rate = loadboard * (1 + adj)
# Adjusted so the weighted avg (15% rounds=0 + 85% rounds>0) hits the stated target.

EQUIPMENT_MARGIN_ADJ: dict[str, float] = {
    "Reefer":     0.04 / 0.85,   # ≈ 0.0471
    "Flatbed":    0.06 / 0.85,   # ≈ 0.0706
    "Dry Van":    0.01 / 0.85,   # ≈ 0.0118
    "Step Deck":  0.03 / 0.85,   # ≈ 0.0353
    "Power Only": 0.00,
}

# ── Booked rounds distribution ────────────────────────────────────────────────

BOOKED_ROUNDS = [0, 1, 2, 3]
BOOKED_ROUNDS_WEIGHTS = [0.15, 0.30, 0.35, 0.20]

# ── Carrier call count pre-assignment (non-dormant, 135 calls) ────────────────
# Layout: CARRIERS[5..9] top-5, CARRIERS[10..22] middle, CARRIERS[23..39] bottom

CARRIER_CALL_COUNTS: dict[int, int] = {
    5: 20, 6: 15, 7: 12, 8: 8, 9: 5,                     # top-5  = 60
    10: 8, 11: 6, 12: 6, 13: 5, 14: 5, 15: 5, 16: 4,     # middle  part-1
    17: 4, 18: 4, 19: 4, 20: 3, 21: 2, 22: 2,             # middle  part-2 = 58
    **{i: 1 for i in range(23, 40)},                       # bottom-17 = 17
}
assert sum(CARRIER_CALL_COUNTS.values()) == 135

# ── "Hot" loads that get extra calls to create dense lanes ────────────────────

HOT_LOAD_IDS = ["LD-00001", "LD-00002", "LD-00005", "LD-00010"]
HOT_LOAD_WEIGHT = 8
DEFAULT_LOAD_WEIGHT = 2

# ── Unresolved topic pool ─────────────────────────────────────────────────────

TOPIC_WEIGHTS = [
    ("price", 0.70), ("dates", 0.20), ("equipment", 0.10),
    ("route", 0.07), ("payment_terms", 0.05), ("hazmat", 0.03),
]

INELIGIBLE_REASONS = [
    "FMCSA authority inactive",
    "Safety rating: Unsatisfactory",
    "Insurance lapsed",
    "Out-of-service order (FMCSA)",
    "Operating authority revoked",
]

# Near-miss count among no_agreement calls
NEAR_MISS_COUNT = 11


# ── Helpers ────────────────────────────────────────────────────────────────────

def _wc(rng: random.Random, choices_weights: list[tuple]) -> Any:
    """Weighted choice from a list of (value, weight) tuples."""
    r = rng.random()
    cumulative = 0.0
    for val, weight in choices_weights:
        cumulative += weight
        if r <= cumulative:
            return val
    return choices_weights[-1][0]


def _gauss_clamp(rng: random.Random, mu: float, sigma: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, rng.gauss(mu, sigma)))


def _pick_weekday(rng: random.Random, day_start: int, day_end: int) -> int:
    """Pick day offset (from BASE_DATE) with weekday/weekend weighting."""
    days = list(range(day_start, day_end + 1))
    weights = [1.0 if (BASE_DATE + timedelta(days=d)).weekday() < 5 else 0.25 for d in days]
    total = sum(weights)
    return _wc(rng, list(zip(days, [w / total for w in weights])))


def _call_start(rng: random.Random, day: int) -> datetime:
    """Return a datetime for a call on the given day offset. 6am-8pm Central (11-01 UTC)."""
    hour_utc = _gauss_clamp(rng, 15.0, 2.0, 11.0, 25.0)  # peak 10am CT = 15 UTC
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    return BASE_DATE + timedelta(days=day, hours=hour_utc, minutes=minute, seconds=second)


def _build_load_pool(loads: list[Load]) -> list[tuple[Load, int]]:
    """Returns (load, weight) pairs; hot loads get higher weight."""
    pool = []
    for load in loads:
        w = HOT_LOAD_WEIGHT if load.load_id in HOT_LOAD_IDS else DEFAULT_LOAD_WEIGHT
        pool.append((load, w))
    return pool


def _pick_load(rng: random.Random, pool: list[tuple[Load, int]]) -> Load:
    total = sum(w for _, w in pool)
    return _wc(rng, [(load, w / total) for load, w in pool])


def _rounds_detail_booked(
    rng: random.Random,
    loadboard_rate: float,
    initial_offer: float,
    num_rounds: int,
    target_final: float,
) -> list[dict]:
    """Generate realistic booked rounds that converge toward target_final."""
    rounds = []
    carrier_ask = initial_offer
    our_price = loadboard_rate

    for r in range(1, num_rounds + 1):
        is_last = r == num_rounds
        if is_last:
            carrier_ask = max(target_final * 1.01, carrier_ask * 0.97)
            our_price = target_final
        else:
            gap = carrier_ask - our_price
            carrier_ask -= gap * _gauss_clamp(rng, 0.30, 0.10, 0.15, 0.50)
            our_price += (carrier_ask - our_price) * _gauss_clamp(rng, 0.15, 0.05, 0.05, 0.30)

        rounds.append({
            "round": r,
            "carrier_offer": round(carrier_ask, 2),
            "our_counter": round(our_price, 2),
        })
    return rounds


def _rounds_detail_no_agreement(
    rng: random.Random,
    loadboard_rate: float,
    initial_offer: float,
    near_miss: bool,
) -> list[dict]:
    """Generate no_agreement rounds (always 3). Near-miss: last carrier_offer within 3% of our_counter."""
    rounds = []
    carrier_ask = initial_offer
    our_price = loadboard_rate

    for r in range(1, 4):
        gap = carrier_ask - our_price
        carrier_ask -= gap * _gauss_clamp(rng, 0.25, 0.08, 0.10, 0.40)
        our_price += (carrier_ask - our_price) * _gauss_clamp(rng, 0.12, 0.05, 0.04, 0.22)

        if r == 3:
            if near_miss:
                # last carrier_offer within 0.5%-2.9% above our_counter
                carrier_ask = our_price * (1 + rng.uniform(0.005, 0.029))
            else:
                # ensure gap > 3% so it's NOT a near-miss
                min_gap_price = our_price * 1.035
                if carrier_ask < min_gap_price:
                    carrier_ask = min_gap_price + our_price * rng.uniform(0.0, 0.02)

        rounds.append({
            "round": r,
            "carrier_offer": round(carrier_ask, 2),
            "our_counter": round(our_price, 2),
        })
    return rounds


def _pick_topics(rng: random.Random) -> list[str]:
    """Pick 1-3 unresolved topics without replacement."""
    n = _wc(rng, [(1, 0.60), (2, 0.30), (3, 0.10)])
    pool = list(TOPIC_WEIGHTS)
    chosen = []
    for _ in range(n):
        if not pool:
            break
        topic = _wc(rng, pool)
        chosen.append(topic)
        pool = [(t, w) for t, w in pool if t != topic]
        if pool:
            total = sum(w for _, w in pool)
            pool = [(t, w / total) for t, w in pool]
    return chosen


# ── Core call builder ─────────────────────────────────────────────────────────

def _make_call(
    rng: random.Random,
    carrier_idx: int,
    outcome: str,
    received_at: datetime,
    load: Optional[Load],
    near_miss: bool = False,
) -> CallLog:
    carrier = CARRIERS[carrier_idx]
    mu, sigma = DURATION_PARAMS[outcome]
    duration = max(30, int(rng.gauss(mu, sigma)))

    carrier_eligible = outcome != "carrier_not_eligible"
    ineligible_reason: Optional[str] = (
        rng.choice(INELIGIBLE_REASONS) if not carrier_eligible else None
    )

    # Denormalized load fields
    load_id = load.load_id if load else None
    origin = load.origin if load else None
    destination = load.destination if load else None
    eq_type: Optional[str] = load.equipment_type.value if load else None
    lb_rate: Optional[float] = load.loadboard_rate if load else None
    miles = load.miles if load else None
    commodity = load.commodity_type if load else None
    pickup_dt = load.pickup_datetime if load else None

    # Negotiation defaults
    initial_offer: Optional[float] = None
    final_rate: Optional[float] = None
    num_rounds = 0
    rounds: list[dict] = []
    walk_away: Optional[str] = None

    if outcome == "booked":
        num_rounds = _wc(rng, list(zip(BOOKED_ROUNDS, BOOKED_ROUNDS_WEIGHTS)))
        if num_rounds == 0:
            final_rate = lb_rate
        else:
            gap = _gauss_clamp(rng, 0.07, 0.04, 0.03, 0.15)
            initial_offer = round(lb_rate * (1 + gap), 2)
            margin_adj = EQUIPMENT_MARGIN_ADJ.get(eq_type, 0.01)
            target = lb_rate * (1 + margin_adj + rng.gauss(0, 0.005))
            target = round(max(lb_rate, min(initial_offer * 0.99, target)), 2)
            rounds = _rounds_detail_booked(rng, lb_rate, initial_offer, num_rounds, target)
            final_rate = target

    elif outcome == "no_agreement":
        num_rounds = 3
        gap = _gauss_clamp(rng, 0.07, 0.04, 0.03, 0.15)
        initial_offer = round(lb_rate * (1 + gap), 2)
        rounds = _rounds_detail_no_agreement(rng, lb_rate, initial_offer, near_miss)
        r = rng.random()
        if r < 0.08:
            walk_away = "over_margin_cap"
        elif r < 0.55:
            walk_away = "max_rounds_reached"

    elif outcome == "carrier_declined":
        gap = _gauss_clamp(rng, 0.07, 0.04, 0.03, 0.15)
        initial_offer = round(lb_rate * (1 + gap), 2)

    # Sentiment
    sentiment = _wc(rng, SENTIMENT_WEIGHTS[outcome])

    # Unresolved topics
    topics: list[str] = []
    if outcome == "no_agreement":
        topics = _pick_topics(rng)
    elif outcome == "carrier_declined" and rng.random() < 0.40:
        topics = _pick_topics(rng)

    lane_str = f"{origin} → {destination}" if origin and destination else None

    summary = make_summary(
        rng=rng,
        outcome=outcome,
        carrier_name=carrier["name"],
        mc_number=carrier["mc"],
        lane=lane_str,
        equipment_type=eq_type,
        loadboard_rate=lb_rate,
        initial_carrier_offer=initial_offer,
        final_rate=final_rate,
        num_rounds=num_rounds,
        duration=duration,
        unresolved_topics=topics,
        ineligible_reason=ineligible_reason,
    )

    # Turn counts based on outcome and duration
    if outcome == "carrier_not_eligible":
        num_user_turns = max(1, int(rng.gauss(3, 0.5)))
    elif outcome == "no_agreement":
        num_user_turns = max(3, int(rng.gauss(11, 2)))
    else:
        num_user_turns = max(1, int(duration / 20 * rng.gauss(1.0, 0.2)))
    num_assistant_turns = max(1, int(num_user_turns * rng.gauss(1.15, 0.15)))

    call_id = "hr_" + str(uuid.uuid4())[:8]

    return CallLog(
        id=call_id,
        created_at=received_at,
        received_at=received_at,
        duration_seconds=duration,
        num_user_turns=num_user_turns,
        num_assistant_turns=num_assistant_turns,
        mc_number=carrier["mc"],
        carrier_name=carrier["name"],
        dot_number=carrier["dot"],
        carrier_eligible=carrier_eligible,
        ineligible_reason=ineligible_reason,
        load_id=load_id,
        origin=origin,
        destination=destination,
        equipment_type=eq_type,
        loadboard_rate=lb_rate,
        miles=miles,
        commodity_type=commodity,
        pickup_datetime=pickup_dt,
        initial_carrier_offer=initial_offer,
        final_rate=final_rate,
        num_rounds=num_rounds,
        rounds_detail=rounds or None,
        walk_away_reason=walk_away,
        outcome=CallOutcome(outcome),
        sentiment=CallSentiment(sentiment),
        unresolved_topics=topics or None,
        transcript_summary=summary,
        # legacy fields
        initial_rate=initial_offer,
        num_negotiation_rounds=num_rounds,
    )


# ── Schema migration helper ────────────────────────────────────────────────────

def _ensure_schema() -> None:
    """Drop call_logs if it's missing new columns, then recreate via create_all."""
    engine = _app_db.engine
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(call_logs)"))
        existing = {row[1] for row in result}

    if not existing:
        init_db()
        return

    required_new = {"received_at", "duration_seconds", "num_user_turns", "num_assistant_turns"}
    if not required_new.issubset(existing):
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS call_logs"))
        Base.metadata.create_all(bind=engine, tables=[CallLog.__table__])


# ── Main seed function ────────────────────────────────────────────────────────

def seed_call_logs(count: int = TOTAL_COUNT, force: bool = False) -> None:
    _ensure_schema()

    with _app_db.SessionLocal() as db:
        existing_count = db.query(CallLog).count()

        if existing_count > 10 and not force:
            print(
                f"Skipping: {existing_count} call_logs already exist. "
                "Pass --force to truncate and repopulate."
            )
            return

        if force and existing_count > 0:
            db.query(CallLog).delete()
            db.commit()

        # Load available loads from DB
        loads = db.query(Load).all()
        if not loads:
            print("WARNING: No loads in DB. Run seed_db first. Skipping call_log seed.")
            return

        load_pool = _build_load_pool(loads)
        rng = random.Random(SEED_VALUE)

        all_calls: list[CallLog] = []

        # ── 1. Dormant carrier calls (15 total: 5 carriers × 3 calls each) ──
        # Outcomes: 2 booked + 1 other per carrier, all in first DORMANT_MAX_DAY days
        dormant_carrier_idxs = list(range(5))  # CARRIERS[0..4]
        for cidx in dormant_carrier_idxs:
            dormant_outcomes = ["booked", "booked", "other"]
            rng.shuffle(dormant_outcomes)
            for outcome in dormant_outcomes:
                day = _pick_weekday(rng, 0, DORMANT_MAX_DAY - 1)
                received_at = _call_start(rng, day)
                load: Optional[Load] = None
                if outcome in ("booked", "no_agreement", "carrier_declined"):
                    load = _pick_load(rng, load_pool)
                elif outcome == "other" and rng.random() < 0.50:
                    load = _pick_load(rng, load_pool)
                call = _make_call(rng, cidx, outcome, received_at, load)
                all_calls.append(call)

        # ── 2. Non-dormant calls (135 total) ─────────────────────────────────
        # Build flat outcome list matching exact targets
        outcome_list: list[str] = []
        for outcome, n in OUTCOME_TARGETS_NONDORMANT.items():
            outcome_list.extend([outcome] * n)
        rng.shuffle(outcome_list)

        # Pre-determine which no_agreement slots are near-miss
        na_slot_indices = [i for i, o in enumerate(outcome_list) if o == "no_agreement"]
        near_miss_slots = set(rng.sample(na_slot_indices, NEAR_MISS_COUNT))

        # Build flat carrier assignment list matching Pareto counts
        carrier_slots: list[int] = []
        for cidx, n in CARRIER_CALL_COUNTS.items():
            carrier_slots.extend([cidx] * n)
        rng.shuffle(carrier_slots)

        for slot_i, (outcome, cidx) in enumerate(zip(outcome_list, carrier_slots)):
            day = _pick_weekday(rng, 0, WINDOW_DAYS - 1)
            received_at = _call_start(rng, day)

            load = None
            if outcome in ("booked", "no_agreement", "carrier_declined"):
                load = _pick_load(rng, load_pool)
            elif outcome == "other" and rng.random() < 0.50:
                load = _pick_load(rng, load_pool)

            near_miss = slot_i in near_miss_slots
            call = _make_call(rng, cidx, outcome, received_at, load, near_miss=near_miss)
            all_calls.append(call)

        # ── 3. Scale to requested count if different from default ─────────────
        if count != TOTAL_COUNT:
            # Regenerate with scaled targets (simple proportional approach)
            all_calls = _scale_calls(rng, loads, load_pool, count)

        # ── 4. Persist ────────────────────────────────────────────────────────
        db.add_all(all_calls)
        db.commit()
        _print_summary(all_calls)


def _scale_calls(
    rng: random.Random,
    loads: list[Load],
    load_pool: list[tuple],
    count: int,
) -> list[CallLog]:
    """Generate `count` calls using proportional outcome weights."""
    outcomes = list(OUTCOME_TARGETS_FULL.keys())
    weights_full = [OUTCOME_TARGETS_FULL[o] / TOTAL_COUNT for o in outcomes]
    call_list: list[CallLog] = []

    # Assign carrier indices round-robin across all 40 carriers
    carrier_idxs = list(range(40))

    for i in range(count):
        outcome = _wc(rng, list(zip(outcomes, weights_full)))
        cidx = carrier_idxs[i % 40]
        day = _pick_weekday(rng, 0, WINDOW_DAYS - 1)
        received_at = _call_start(rng, day)

        load = None
        if outcome in ("booked", "no_agreement", "carrier_declined"):
            load = _pick_load(rng, load_pool)

        near_miss = outcome == "no_agreement" and rng.random() < (NEAR_MISS_COUNT / 45)
        call = _make_call(rng, cidx, outcome, received_at, load, near_miss=near_miss)
        call_list.append(call)

    return call_list


# ── Summary printer ───────────────────────────────────────────────────────────

def _print_summary(calls: list[CallLog]) -> None:
    from collections import Counter

    outcome_counts = Counter(c.outcome.value for c in calls)
    mc_counts = Counter(c.mc_number for c in calls)
    top_mc = mc_counts.most_common(1)[0]
    top_carrier_name = next(
        c["name"] for c in CARRIERS if c["mc"] == top_mc[0]
    )

    # Near-miss count: no_agreement calls where last carrier_offer within 3% of last our_counter
    near_miss = 0
    for c in calls:
        if c.outcome.value == "no_agreement" and c.rounds_detail:
            last = c.rounds_detail[-1]
            co = last.get("carrier_offer", 0)
            oc = last.get("our_counter", 0)
            if oc > 0 and (co - oc) / oc < 0.03:
                near_miss += 1

    # Dormant carriers: last call >25 days ago + ≥2 bookings
    cutoff = TODAY - timedelta(days=25)
    by_mc: dict[str, list[CallLog]] = defaultdict(list)
    for c in calls:
        by_mc[c.mc_number].append(c)

    dormant = 0
    for mc, mc_calls in by_mc.items():
        last_call_dt = max(c.received_at for c in mc_calls if c.received_at)
        bookings = sum(1 for c in mc_calls if c.outcome.value == "booked")
        if last_call_dt < cutoff and bookings >= 2:
            dormant += 1

    # Avg margin on booked calls
    margins = []
    for c in calls:
        if c.outcome.value == "booked" and c.final_rate and c.loadboard_rate:
            margins.append((c.final_rate - c.loadboard_rate) / c.loadboard_rate)
    avg_margin = sum(margins) / len(margins) * 100 if margins else 0

    print(f"\nSeeded {len(calls)} call logs across {WINDOW_DAYS} days")
    print(
        "  Outcome breakdown:   "
        + "  ".join(f"{k}={v}" for k, v in sorted(outcome_counts.items()))
    )
    print(f"  Unique carriers:     {len(set(c.mc_number for c in calls))}"
          f"  (top caller: {top_carrier_name} with {top_mc[1]} calls)")
    print(f"  Near-miss deals:     {near_miss}")
    print(f"  Dormant carriers:    {dormant}")
    print(f"  Avg margin (booked): +{avg_margin:.1f}%")


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed call_logs table with realistic data.")
    p.add_argument("--force", action="store_true", help="Truncate and repopulate")
    p.add_argument("--count", type=int, default=TOTAL_COUNT, help="Number of calls to generate")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    seed_call_logs(count=args.count, force=args.force)

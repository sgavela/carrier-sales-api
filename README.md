# carrier-sales-api

**FastAPI backend that powers a HappyRobot voice agent for inbound carrier sales — carrier verification, load matching, rules-based rate negotiation, and a full-featured analytics dashboard.**

---

## Table of contents

1. [What this is](#what-this-is)
2. [Architecture](#architecture)
3. [Tech stack](#tech-stack)
4. [Quick start — local (no Docker)](#quick-start--local-no-docker)
5. [Quick start — Docker](#quick-start--docker)
6. [Environment variables](#environment-variables)
7. [API reference](#api-reference)
   - [Authentication](#authentication)
   - [GET /health](#get-health)
   - [POST /carriers/verify](#post-carriersverify)
   - [POST /loads/search](#post-loadssearch)
   - [GET /loads/{load\_id}](#get-loadsload_id)
   - [POST /negotiation/evaluate-offer](#post-negotiationevaluate-offer)
   - [POST /calls/log-call](#post-callslog-call)
   - [POST /calls/log (legacy)](#post-callslog-legacy)
   - [GET /calls](#get-calls)
   - [GET /metrics](#get-metrics)
   - [GET /dashboard](#get-dashboard)
8. [Negotiation engine](#negotiation-engine)
9. [Data model](#data-model)
10. [Seeding](#seeding)
11. [Testing](#testing)
12. [CI/CD](#cicd)
13. [Deploying to the cloud](#deploying-to-the-cloud)
14. [Security](#security)
15. [FMCSA web key](#fmcsa-web-key)
16. [Extending](#extending)
17. [Discrepancies and known gaps](#discrepancies-and-known-gaps)

---

## What this is

A freight broker's [HappyRobot](https://happyrobot.ai) voice agent calls this API during live phone conversations. The agent handles all speech (ASR / LLM / TTS). This API handles all business logic:

- **Carrier eligibility** — look up an MC number against the FMCSA carrier registry in real time.
- **Load matching** — filter available loads by origin, destination, equipment type, and pickup window.
- **Rate negotiation** — stateless, rules-based engine that returns `accept`, `counter`, or `reject` for each carrier offer across up to three rounds.
- **Call logging** — persist structured call outcomes so the broker can audit every interaction.
- **Analytics dashboard** — aggregated KPIs (booking rate, margin, near-misses, carrier tiering, dormant carriers, lane pricing) consumed by the companion React dashboard.

---

## Architecture

```
Carrier (inbound phone call)
         │
         ▼
HappyRobot voice agent (ASR → LLM → TTS, cloud-hosted)
         │
         │  POST /carriers/verify
         │  POST /loads/search
         │  POST /negotiation/evaluate-offer
         │  POST /calls/log-call
         ▼
  carrier-sales-api  ◄──► SQLite (WAL mode)
         │
         ├─► FMCSA QC API  (live carrier registry lookups)
         │
         └─► GET /dashboard  ◄── React dashboard (acme-dashboard)
```

Every endpoint except `/health` is protected by a static `X-API-Key` header. The key is compared with `secrets.compare_digest` to prevent timing attacks.

---

## Tech stack

| Layer | Library / tool | Version |
|---|---|---|
| Web framework | FastAPI | 0.115.5 |
| ASGI server | Uvicorn (standard extras) | 0.32.1 |
| Data validation | Pydantic v2 + pydantic-settings | 2.10.3 / 2.6.1 |
| ORM | SQLAlchemy 2.0 (Core + ORM) | 2.0.36 |
| HTTP client (FMCSA) | httpx (async) | 0.28.1 |
| Config | python-dotenv + pydantic-settings | 1.0.1 / 2.6.1 |
| Runtime | Python 3.11 |  |
| Container | Docker multi-stage, python:3.11-slim | |
| CI | GitHub Actions | |
| Linter | ruff | 0.11.7 |
| Test runner | pytest + pytest-asyncio | 8.3.4 / 0.24.0 |

Production database is SQLite with WAL mode enabled. SQLAlchemy's `DATABASE_URL` is the only change needed to switch to PostgreSQL.

---

## Quick start — local (no Docker)

**Requirements:** Python 3.11+

```bash
cd carrier-sales-api

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements-dev.txt

cp .env.example .env
# Edit .env: set API_KEY and optionally FMCSA_WEBKEY
# For local development set FMCSA_MOCK=true if you don't have a FMCSA key

uvicorn app.main:app --reload --port 8000
```

On first boot the app **auto-seeds** the database:
- 27 freight loads across 10+ US lanes and 5 equipment types.
- ~150 synthetic call log records for dashboard development.

Both seeds are idempotent — they only run when the tables are empty.

Verify the server is up:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

Interactive API docs: http://localhost:8000/docs

---

## Quick start — Docker

```bash
cp .env.example .env
# Edit .env

docker compose up --build -d

# Tail logs
docker compose logs -f

# Stop
docker compose down
```

The SQLite database is stored in `./data/` on the host and mounted as a volume — it persists across container restarts. The Docker Compose health check polls `/health` every 30 seconds.

**Dockerfile highlights:**
- Multi-stage build: dependencies are installed in a `builder` stage, the `runtime` stage copies only the compiled venv.
- Runs as a non-root user (`appuser`).
- Base image: `python:3.11-slim`.

---

## Environment variables

All variables are read via `pydantic-settings` from the `.env` file (or real environment variables). The table below lists every variable defined in `app/config.py`.

| Variable | Required | Default | Description |
|---|---|---|---|
| `API_KEY` | **yes** | `dev-insecure-key` | Shared secret sent in `X-API-Key` header. Change before deploying. |
| `FMCSA_WEBKEY` | yes (prod) | `""` | Free government key from FMCSA (see [FMCSA web key](#fmcsa-web-key)). |
| `FMCSA_BASE_URL` | no | `https://mobile.fmcsa.dot.gov/qc/services/carriers` | FMCSA QC API base URL. |
| `FMCSA_TIMEOUT` | no | `5.0` | HTTP timeout (seconds) for FMCSA requests. |
| `FMCSA_MOCK` | no | `false` | `true` — skip real FMCSA calls, return deterministic mock data. |
| `DATABASE_URL` | no | `sqlite:///./data/carrier_sales.db` | Any SQLAlchemy-compatible URL. |
| `PORT` | no | `8000` | Uvicorn port. |
| `LOG_LEVEL` | no | `INFO` | Passed to Python's logging system. Case-insensitive. |
| `DEBUG` | no | `false` | Enables `POST /calls/log-call-debug` raw payload echo endpoint. |
| `CORS_ORIGINS` | no | `http://localhost:3000` | Comma-separated list of allowed CORS origins. |
| `MAX_ROUNDS` | no | `3` | Maximum negotiation rounds before auto-reject. |
| `MAX_MARGIN_PCT` | no | `0.12` | Absolute ceiling — broker never pays more than `loadboard_rate × (1 + 0.12)`. |
| `ROUND1_CEILING_PCT` | no | `0.12` | Round 1: if carrier offer exceeds `rate × (1 + this)`, counter at `ROUND1_COUNTER_PCT`. |
| `ROUND1_COUNTER_PCT` | no | `0.05` | Round 1 counter-offer: `rate × (1 + this)`. |
| `ROUND2_CEILING_PCT` | no | `0.10` | Round 2: tighter ceiling. |
| `ROUND2_BLEND_RATIO` | no | `0.75` | Round 2: move this fraction of the way from our R1 counter toward carrier's offer. |
| `ROUND3_ACCEPT_PCT` | no | `0.08` | Round 3: accept if carrier offer ≤ `rate × (1 + this)`, otherwise reject. |

`.env.example` ships with all variables pre-documented and safe defaults.

---

## API reference

### Authentication

Every endpoint except `GET /health` requires the header:

```
X-API-Key: <your API_KEY value>
```

Missing or incorrect key returns `HTTP 401`.

---

### GET /health

No authentication required. Returns `HTTP 200` when the process is running.

```bash
curl http://localhost:8000/health
```

```json
{"status": "ok"}
```

---

### POST /carriers/verify

Verify a carrier's operating authority against the FMCSA QC registry.

The MC number is normalised before lookup — `"MC-123456"`, `"mc123456"`, and `"123456"` all resolve to `"123456"`.

**Request**

```json
{"mc_number": "MC123456"}
```

**Response**

```json
{
  "eligible": true,
  "mc_number": "123456",
  "carrier_name": "ACME TRUCKING LLC",
  "dot_number": "3456789",
  "allowed_to_operate": "Y",
  "reason": null
}
```

| Field | Type | Notes |
|---|---|---|
| `eligible` | bool | `true` if carrier is found and `allowedToOperate == "Y"`. |
| `mc_number` | string | Normalised digits only. |
| `carrier_name` | string\|null | Legal name from FMCSA (`legalName` or `dbaName`). |
| `dot_number` | string\|null | DOT number from FMCSA. |
| `allowed_to_operate` | string\|null | `"Y"` or `"N"`. |
| `reason` | string\|null | Human-readable reason when `eligible=false`. |

**Error responses**

| Status | Condition |
|---|---|
| 400 | `mc_number` is blank or whitespace-only. |
| 401 | Missing or invalid `X-API-Key`. |
| 422 | `mc_number` field missing from request body. |
| 502 | FMCSA service unreachable or returned an unexpected response. |

**FMCSA mock numbers (when `FMCSA_MOCK=true`)**

| MC | Result |
|---|---|
| `000000` | Not found |
| `111111` | Found, not authorized to operate |
| `123456` | Eligible — ACME TRUCKING LLC |
| `654321` | Eligible — SWIFT FREIGHT INC |
| `789012` | Eligible — BLUE RIDGE CARRIERS LLC |
| any other | Eligible — GENERIC TRANSPORT LLC |

```bash
curl -X POST http://localhost:8000/carriers/verify \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"mc_number": "MC123456"}'
```

---

### POST /loads/search

Search available loads. All filter fields are optional; omitting all returns the next `max_results` available loads ordered by pickup date ascending.

**Request**

```json
{
  "origin": "Chicago",
  "destination": "Atlanta",
  "equipment_type": "Dry Van",
  "pickup_date_from": "2026-04-19",
  "pickup_date_to": "2026-04-26",
  "max_results": 3
}
```

| Field | Type | Notes |
|---|---|---|
| `origin` | string\|null | Case-insensitive prefix match on city name (e.g., `"Chicago"` matches `"Chicago, IL"`). |
| `destination` | string\|null | Same as `origin`. |
| `equipment_type` | enum\|null | One of `"Dry Van"`, `"Reefer"`, `"Flatbed"`, `"Step Deck"`, `"Power Only"`. |
| `pickup_date_from` | date\|null | `YYYY-MM-DD`. Inclusive lower bound on pickup datetime. |
| `pickup_date_to` | date\|null | `YYYY-MM-DD`. Inclusive upper bound. |
| `max_results` | int | 1–20, default 3. |

Only loads with `status == "available"` are returned.

**Response** — array of load objects:

```json
[
  {
    "load_id": "LD-00001",
    "origin": "Chicago, IL",
    "destination": "Atlanta, GA",
    "pickup_datetime": "2026-04-25T08:00:00",
    "delivery_datetime": "2026-04-26T18:00:00",
    "equipment_type": "Dry Van",
    "loadboard_rate": 1500.0,
    "weight": 38000,
    "commodity_type": "Electronics",
    "num_of_pieces": 22,
    "miles": 716,
    "dimensions": "48x40x60 in",
    "status": "available",
    "notes": null,
    "booked_rate": null,
    "booked_mc": null
  }
]
```

```bash
curl -X POST http://localhost:8000/loads/search \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"origin": "Chicago", "equipment_type": "Dry Van", "max_results": 3}'
```

---

### GET /loads/{load\_id}

Fetch a single load by its primary key.

```bash
curl http://localhost:8000/loads/LD-00001 \
  -H "X-API-Key: $API_KEY"
```

Returns the same load object schema as `/loads/search`. Returns `HTTP 404` if the `load_id` does not exist.

---

### POST /negotiation/evaluate-offer

Evaluate a carrier's rate counter-offer. The negotiation engine reads the authoritative `loadboard_rate` from the database — the `loadboard_rate` field in the request body is present only for the agent's context and **is intentionally ignored**. This prevents rate manipulation.

**Request**

```json
{
  "load_id": "LD-00001",
  "loadboard_rate": 1500.0,
  "carrier_offer": 1700.0,
  "round": 1
}
```

| Field | Type | Notes |
|---|---|---|
| `load_id` | string | Must exist in the `loads` table. |
| `loadboard_rate` | float | Ignored — included for agent logging only. |
| `carrier_offer` | float | Carrier's proposed rate. |
| `round` | int | Negotiation round number (1–3). Rounds ≥ `MAX_ROUNDS` are treated as the final round. |

**Response**

```json
{
  "action": "counter",
  "counter_offer": 1575.0,
  "message_hint": "We're close. We can meet you halfway at $1,575.00.",
  "should_close": false
}
```

| Field | Type | Notes |
|---|---|---|
| `action` | `"accept"` \| `"counter"` \| `"reject"` | Decision for this round. |
| `counter_offer` | float\|null | Our counter-offer. `null` when `action` is `"accept"` or `"reject"`. |
| `message_hint` | string | Suggested phrasing for the voice agent. |
| `should_close` | bool | `true` when the negotiation is over (accepted or rejected). |

**Error responses:** `HTTP 404` if `load_id` not found. `HTTP 401` for missing key.

```bash
curl -X POST http://localhost:8000/negotiation/evaluate-offer \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"load_id": "LD-00001", "loadboard_rate": 1500.0, "carrier_offer": 1700.0, "round": 1}'
```

For the full negotiation logic, see [Negotiation engine](#negotiation-engine).

---

### POST /calls/log-call

**Primary endpoint.** Log a completed call using the full HappyRobot nested payload schema. Idempotent on `call_id` — resending the same `call_id` updates the existing record.

When `classification.outcome == "booked"`, the referenced load is automatically marked as `booked` and its `booked_rate` / `booked_mc` fields are set. If the load was already booked by a prior call, the response includes a `warning` message but returns `HTTP 200`.

**Request schema**

```json
{
  "call_id": "hr_a1b2c3d4",
  "duration": 245,
  "num_user_turns": 5,
  "num_assistant_turns": 6,
  "carrier": {
    "mc_number": "MC-123456",
    "carrier_name": "SWIFT LOGISTICS LLC",
    "dot_number": "DOT-2001001",
    "eligible": true,
    "ineligible_reason": ""
  },
  "load": {
    "load_id": "LD-00001",
    "origin": "Chicago, IL",
    "destination": "Atlanta, GA",
    "equipment_type": "Dry Van",
    "loadboard_rate": 1500.0,
    "miles": 716,
    "commodity_type": "Electronics",
    "pickup_datetime": "2026-04-25T08:00:00"
  },
  "negotiation": {
    "initial_carrier_offer": 1650.0,
    "final_rate": 1560.0,
    "num_rounds": 1,
    "rounds_detail": [
      {"round": 1, "carrier_offer": 1650.0, "our_counter": 1500.0, "decision": "accept"}
    ],
    "walk_away_reason": ""
  },
  "classification": {
    "outcome": "booked",
    "sentiment": "positive",
    "unresolved_topics": []
  },
  "summary": {
    "transcript_summary": "Carrier verified. Booked Chicago–Atlanta Dry Van at $1,560 after 1 round."
  }
}
```

**Top-level fields**

| Field | Type | Notes |
|---|---|---|
| `call_id` | string | Unique identifier for the call. Used as the idempotency key. |
| `duration` | int | Call duration in seconds. Coerced from string if needed. |
| `num_user_turns` | int | Number of carrier turns in the conversation. |
| `num_assistant_turns` | int | Number of agent turns. |

**`carrier` block**

| Field | Type | Notes |
|---|---|---|
| `mc_number` | string | `"MC-"` prefix and dashes are stripped automatically. |
| `carrier_name` | string\|null | |
| `dot_number` | string\|null | `"DOT-"` prefix stripped. |
| `eligible` | bool | Accepts `true`/`false` or string `"true"`/`"false"`. |
| `ineligible_reason` | string\|null | Empty string stored as `null`. |

**`load` block** — all fields optional for non-booked outcomes.

**`negotiation` block**

| Field | Type | Notes |
|---|---|---|
| `initial_carrier_offer` | float\|null | Carrier's opening ask. |
| `final_rate` | float\|null | Required when `outcome == "booked"`. |
| `num_rounds` | int | Must equal `len(rounds_detail)` — validated server-side. |
| `rounds_detail` | array | Each element: `{round, carrier_offer, our_counter, decision}`. Accepts JSON string `"[]"`. |
| `walk_away_reason` | string\|null | Free-text reason if carrier walked. |

**`classification` block**

| Field | Allowed values |
|---|---|
| `outcome` | `booked`, `no_agreement`, `carrier_not_eligible`, `no_loads_found`, `carrier_declined`, `other` |
| `sentiment` | `positive`, `neutral`, `negative` |
| `unresolved_topics` | Array of strings. Accepts a single string or comma-separated string. |

**Business-rule validations (HTTP 400)**

- `outcome == "booked"` requires `negotiation.final_rate` and `load.load_id`.
- `outcome == "carrier_not_eligible"` requires `carrier.eligible == false`.
- `num_rounds` must equal `len(rounds_detail)`.

**Coercion** — all numeric fields accept numeric strings (`"1500"` → `1500.0`). Empty strings are stored as `null`. This handles the varied output formats of LLM-driven extraction.

**Response**

```json
{
  "call_id": "hr_a1b2c3d4",
  "stored": true,
  "action": "created",
  "load_status_changed": true,
  "warning": null
}
```

| Field | Notes |
|---|---|
| `action` | `"created"` on first submission, `"updated"` on re-submission of same `call_id`. |
| `load_status_changed` | `true` if the referenced load was transitioned to `booked`. |
| `warning` | Non-null string if the load was already booked before this call reported it. |

```bash
curl -X POST http://localhost:8000/calls/log-call \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d @payload.json
```

---

### POST /calls/log (legacy)

Flat payload schema, retained for backward compatibility. Accepts a simpler structure without nested blocks. New integrations should use `POST /calls/log-call`.

**Request**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "mc_number": "123456",
  "carrier_name": "ACME TRUCKING LLC",
  "load_id": "LD-00001",
  "initial_rate": 1500.0,
  "final_rate": 1600.0,
  "num_negotiation_rounds": 1,
  "outcome": "booked",
  "sentiment": "positive",
  "transcript_summary": "Carrier agreed after one counter-offer.",
  "raw_extraction": {"call_duration_s": 145}
}
```

`id` is optional — omitting it generates a UUID. Idempotent on `id`. Returns `HTTP 201` with `{"id": "...", "created": true/false}`.

---

### GET /calls

Paginated call log history, most recent first.

**Query parameters**

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 20 | 1–100 |
| `offset` | int | 0 | Pagination offset. |
| `outcome` | enum | — | Filter by outcome value. |
| `sentiment` | enum | — | Filter by sentiment value. |
| `from_date` | string | — | ISO date `YYYY-MM-DD`. Inclusive. |
| `to_date` | string | — | ISO date `YYYY-MM-DD`. Inclusive (end of day). |

```bash
curl "http://localhost:8000/calls?limit=10&outcome=booked&from_date=2026-04-01" \
  -H "X-API-Key: $API_KEY"
```

Returns an array of call log objects.

---

### GET /metrics

Lightweight aggregated metrics. Covers all time (no date filter). For filtered, richer analytics use `GET /dashboard`.

**Response**

```json
{
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
    "no_loads_found": 4,
    "carrier_declined": 3,
    "other": 2
  },
  "sentiment_breakdown": {
    "positive": 20,
    "neutral": 15,
    "negative": 7
  },
  "calls_last_7_days": [
    {"date": "2026-04-18", "count": 6}
  ]
}
```

`avg_margin_vs_loadboard` is `avg(final_rate - initial_rate)` across booked calls that have both rates. Negative means the broker paid above loadboard on average.

---

### GET /dashboard

Full analytics dashboard. Returns a rich, filterable snapshot suitable for driving a real-time KPI UI.

**Query parameters**

| Param | Type | Default | Description |
|---|---|---|---|
| `from` | string | today − 30 days | Start date `YYYY-MM-DD`. |
| `to` | string | today | End date `YYYY-MM-DD`. |
| `equipment_type` | string | — | Filter to a single equipment type (e.g., `"Reefer"`). |

```bash
curl "http://localhost:8000/dashboard?from=2026-03-01&to=2026-04-19" \
  -H "X-API-Key: $API_KEY"
```

**Top-level response shape**

```
DashboardResponse
├── generated_at          datetime
├── period_from           string (YYYY-MM-DD)
├── period_to             string (YYYY-MM-DD)
├── equipment_filter      string|null
├── overview              OverviewBlock
├── carriers              CarriersBlock
├── pricing               PricingBlock
├── quality               QualityBlock
└── recent_calls          list[RecentCall] (last 20)
```

**`overview` block**

| Field | Description |
|---|---|
| `total_calls` | Calls in the period. |
| `booked` | Count of booked calls. |
| `booking_rate` | `booked / total_calls`. |
| `avg_margin_pct` | Average `(final_rate - loadboard_rate) / loadboard_rate` across booked calls. |
| `revenue_captured` | Sum of `final_rate` across booked calls. |
| `avg_call_duration_seconds` | Average of `duration_seconds` across all calls with non-zero duration. |
| `avg_time_to_book_seconds` | Average `duration_seconds` for booked calls only. |
| `calls_by_day` | Array of `{date, count, booked}` for every day in the period. |
| `outcome_breakdown` | Count per outcome value. |
| `sentiment_breakdown` | Count per sentiment value. |

**`carriers` block**

| Field | Description |
|---|---|
| `carriers` | Per-carrier summary sorted by `total_calls` desc. Each entry includes `mc_number`, `carrier_name`, `total_calls`, `bookings`, `booking_rate`, `avg_rounds`, `avg_margin_pct`, `sentiment_score`, `tier` (A/B/C/D), `last_call_at`. |
| `tier_distribution` | Count of carriers per tier. |
| `repeat_vs_new` | `{repeat_calls, new_caller_calls}`. |
| `dormant_carriers` | Carriers with last call > 25 days ago and ≥ 2 historical bookings. Fields: `mc_number`, `carrier_name`, `last_call_at`, `historical_bookings`, `historical_revenue`, `avg_margin_pct`, `days_dormant`. |

**Carrier tier logic**

| Tier | Criteria |
|---|---|
| A | ≥3 calls, booking rate > 50%, avg sentiment score > 0.3 |
| B | ≥2 calls, booking rate > 30% |
| C | avg rounds ≥ 2.5 or booking rate < 30% |
| D | Has a call where carrier was ineligible |

**`pricing` block**

| Field | Description |
|---|---|
| `avg_margin_pct_by_equipment` | Dict of equipment type → avg margin (booked calls only). |
| `pricing_by_lane` | Per-lane stats: `lane`, `equipment_type`, `calls`, `bookings`, `avg_final_rate`, `avg_loadboard_rate`, `avg_margin_pct`. Sorted by call volume desc. |
| `counter_offer_distribution` | Histogram of initial carrier offer gap vs loadboard rate: buckets `<0`, `0-5%`, `5-10%`, `10-15%`, `15+%`. |
| `accept_rate_by_round` | For each round 1–3: `offers_made`, `accepted`, `accept_rate`. |
| `lost_near_miss` | `no_agreement` calls where the last carrier offer was within 3% of our final counter. Fields: `call_id`, `mc_number`, `carrier_name`, `lane`, `loadboard_rate`, `our_last_counter`, `carrier_last_offer`, `gap_pct`, `revenue_lost_estimate`. |
| `walk_away_rate` | Fraction of calls with a non-null `walk_away_reason`. |

**`quality` block**

| Field | Description |
|---|---|
| `duration_by_outcome` | Per-outcome `avg_seconds` and `median_seconds`. |
| `rounds_distribution` | Count of calls by negotiation round count: `0_rounds`, `1_round`, `2_rounds`, `3_rounds`. |
| `unresolved_topics_breakdown` | Frequency count of each topic string across all calls. |
| `sentiment_on_booked_transfer` | Sentiment breakdown for booked calls only. |
| `near_miss_count` | Count of near-miss deals. |
| `walk_away_count` | Count of calls with a `walk_away_reason`. |
| `avg_turn_ratio` | Average of `num_assistant_turns / num_user_turns` (excludes calls with zero user turns). |
| `avg_total_turns` | Average of `num_user_turns + num_assistant_turns` across all calls. |

---

## Negotiation engine

The engine lives in `app/services/negotiator.py` as a **pure function** — no I/O, no database, no side effects. All thresholds are injected from `app/config.Settings`.

```
evaluate(loadboard_rate, carrier_offer, round_num) → NegotiationDecision
```

### Round 1 (`ROUND1_*`)

```
ceiling = loadboard_rate × (1 + ROUND1_CEILING_PCT)   # default: +12%

if carrier_offer ≤ loadboard_rate:
    → accept

if carrier_offer > ceiling:
    counter = loadboard_rate × (1 + ROUND1_COUNTER_PCT)  # default: +5%
    → counter at our floor

if loadboard_rate < carrier_offer ≤ ceiling:
    midpoint = (loadboard_rate + carrier_offer) / 2
    → counter at midpoint
```

### Round 2 (`ROUND2_*`)

```
ceiling = loadboard_rate × (1 + ROUND2_CEILING_PCT)   # default: +10%, tighter

if carrier_offer ≤ loadboard_rate:
    → accept

r1_counter = loadboard_rate × (1 + ROUND1_COUNTER_PCT)
blend = r1_counter + ROUND2_BLEND_RATIO × (carrier_offer - r1_counter)
our_counter = min(blend, ceiling)    # never exceed the tighter ceiling
→ counter at our_counter
```

### Round 3 / final (`ROUND3_*`)

```
accept_ceiling = loadboard_rate × (1 + ROUND3_ACCEPT_PCT)  # default: +8%

if carrier_offer ≤ accept_ceiling:
    → accept (should_close=true)
else:
    → reject (should_close=true)
```

`should_close=true` on accept in round 3 (not rounds 1–2 where negotiation continues).

Rounds beyond `MAX_ROUNDS` are treated identically to the final round.

### Configuring thresholds

All percentages are environment variables — set them in `.env` to tune broker margins without touching code. Example: to tighten round 3 acceptance:

```
ROUND3_ACCEPT_PCT=0.05   # only accept if offer is ≤ 5% above loadboard
```

---

## Data model

### `loads` table

| Column | Type | Notes |
|---|---|---|
| `load_id` | `String(20)` PK | e.g., `LD-00001` |
| `origin` | `String(100)` | `"Chicago, IL"` |
| `destination` | `String(100)` | |
| `pickup_datetime` | `DateTime` | |
| `delivery_datetime` | `DateTime` | |
| `equipment_type` | `Enum(EquipmentType)` | `Dry Van`, `Reefer`, `Flatbed`, `Step Deck`, `Power Only` |
| `loadboard_rate` | `Float` | Authoritative rate used in negotiation. |
| `weight` | `Integer` | Lbs. |
| `commodity_type` | `String(100)` | |
| `num_of_pieces` | `Integer` | |
| `miles` | `Integer` | |
| `dimensions` | `String(50)` | |
| `status` | `Enum(LoadStatus)` | `available` or `booked` |
| `notes` | `Text` nullable | |
| `booked_rate` | `Float` nullable | Set when a call with `outcome=booked` references this load. |
| `booked_mc` | `String(20)` nullable | MC number of the carrier that booked. |

### `call_logs` table

| Column | Type | Notes |
|---|---|---|
| `id` | `String(36)` PK | UUID. Maps to `call_id` in the HappyRobot schema. |
| `created_at` | `DateTime` | Server timestamp, set at insert. |
| `received_at` | `DateTime` | Server timestamp for the POST request arrival. |
| `duration_seconds` | `Integer` | Call duration. |
| `num_user_turns` | `Integer` | |
| `num_assistant_turns` | `Integer` | |
| `mc_number` | `String(20)` | |
| `carrier_name` | `String(200)` nullable | |
| `dot_number` | `String(20)` nullable | |
| `carrier_eligible` | `Boolean` nullable | |
| `ineligible_reason` | `String(200)` nullable | |
| `load_id` | `String(20)` FK→`loads.load_id` nullable | |
| `origin` | `String(100)` nullable | Denormalised from load for query performance. |
| `destination` | `String(100)` nullable | |
| `equipment_type` | `String(50)` nullable | |
| `loadboard_rate` | `Float` nullable | |
| `miles` | `Integer` nullable | |
| `commodity_type` | `String(100)` nullable | |
| `pickup_datetime` | `DateTime` nullable | |
| `initial_carrier_offer` | `Float` nullable | |
| `final_rate` | `Float` nullable | |
| `num_rounds` | `Integer` nullable | |
| `rounds_detail` | `JSON` nullable | Array of `{round, carrier_offer, our_counter, decision}`. |
| `walk_away_reason` | `String(100)` nullable | |
| `outcome` | `Enum(CallOutcome)` | `booked`, `no_agreement`, `carrier_not_eligible`, `no_loads_found`, `carrier_declined`, `other` |
| `sentiment` | `Enum(CallSentiment)` | `positive`, `neutral`, `negative` |
| `unresolved_topics` | `JSON` nullable | Array of strings. |
| `transcript_summary` | `Text` nullable | |
| `raw_extraction` | `JSON` nullable | Full LLM extraction blob (legacy). |
| `initial_rate` | `Float` nullable | Legacy alias of `initial_carrier_offer`. |
| `num_negotiation_rounds` | `Integer` | Legacy alias of `num_rounds`. |

**SQLite configuration:** WAL journal mode is set at connect time for better concurrent read performance. The data directory is created automatically on startup.

---

## Seeding

The database is auto-seeded on first boot (empty tables). Both seeds are idempotent.

**Manual seed:**

```bash
# Loads only
python scripts/seed_db.py --loads-only

# Loads + call logs (default)
python scripts/seed_db.py

# Inside Docker
docker compose exec api python scripts/seed_db.py
```

**`scripts/seed_db.py`** — reads `data/loads_seed.json` and upserts 27 loads covering:

- 5 equipment types (Dry Van, Reefer, Flatbed, Step Deck, Power Only)
- 10+ US lanes (Chicago→Atlanta, LA→Dallas, NYC→Chicago, etc.)
- 8 commodity types

**`scripts/seed_call_logs.py`** — generates ~150 synthetic call log records using realistic carrier fixtures from `scripts/_fixtures/carriers.py` and transcript summaries from `scripts/_fixtures/summaries.py`. Used to pre-populate the dashboard for demos.

---

## Testing

```bash
pip install -r requirements-dev.txt

pytest -v
# or quietly:
pytest -q
```

**Test suite overview**

| File | What it covers |
|---|---|
| `tests/test_auth.py` | API key enforcement across all protected routes. |
| `tests/test_carriers.py` | MC normalisation, eligible/ineligible/not-found mock scenarios, input validation. |
| `tests/test_loads.py` | Search filtering (origin, destination, equipment, date range), `GET /loads/{id}`, 404 handling. |
| `tests/test_negotiation.py` | **Two-layer**: (1) pure unit tests on `evaluate()` — all round/ceiling/midpoint/blend edge cases; (2) HTTP integration tests including rate manipulation prevention. |
| `tests/test_calls.py` | Both logging endpoints, idempotency, load booking side effect, business-rule validation, coercion of string numbers / empty strings / JSON strings. |
| `tests/test_dashboard.py` | Pure unit tests on all four compute functions plus HTTP integration test for equipment filter. |
| `tests/test_seed_call_logs.py` | Seed script produces expected record count and valid data. |

**Test infrastructure** (`tests/conftest.py`):

- In-memory SQLite (no file I/O).
- `FMCSA_MOCK=true` (no network calls).
- Each test function gets a fresh schema — `autouse` fixture drops and recreates all tables.
- `TestClient` (synchronous ASGI test client from `httpx`).

No network calls, no file I/O, no side effects. The full suite runs in < 5 seconds.

---

## CI/CD

Three-stage GitHub Actions pipeline defined in `.github/workflows/ci.yml`. Triggers on push and pull request to `main`.

```
lint ──► test ──► docker build & push   (main branch only)
```

| Stage | Tool | Notes |
|---|---|---|
| **Lint** | `ruff check .` | Fast linter/formatter. Fails the pipeline on any violation. |
| **Test** | `pytest -q` | Runs on `ubuntu-latest`, Python 3.11. pip cache keyed on `requirements-dev.txt`. |
| **Docker** | `docker/build-push-action@v6` | Multi-platform build with GHA layer cache. Pushes `latest` + `sha-<commit>` tags to Docker Hub. Only runs on push to `main` (skipped on PRs). |

Docker Hub credentials are stored as GitHub secrets (`DOCKER_HUB_TOKEN`) and variables (`DOCKER_HUB_USERNAME`).

---

## Deploying to the cloud

### Render (recommended for proof-of-concept)

1. Push the repo to GitHub.
2. Create a new **Web Service** on [render.com](https://render.com), point it at the repo.
3. Set runtime to **Docker**.
4. Add environment variables from `.env.example` in the Render dashboard.
5. Render builds the Docker image from the repo root and gives a permanent `https://` URL.

Set `CORS_ORIGINS` to include your HappyRobot agent origin and dashboard domain.

### Railway / Fly.io

Both support Docker deploys. Railway is fastest to configure; Fly.io gives more control over regions and persistent volumes.

### Production checklist

- [ ] Replace `API_KEY` default with a strong random secret (32+ chars).
- [ ] Set `FMCSA_MOCK=false` and provide a real `FMCSA_WEBKEY`.
- [ ] Set `CORS_ORIGINS` to the exact origins of your HappyRobot agent and dashboard.
- [ ] Mount a persistent volume for `./data/` (or swap to PostgreSQL).
- [ ] Set `LOG_LEVEL=INFO` (default) or `WARNING` in production.
- [ ] Keep `DEBUG=false` — enabling it exposes a raw payload echo endpoint.

---

## Security

| Concern | Implementation |
|---|---|
| API key auth | `secrets.compare_digest` — constant-time comparison prevents timing attacks. |
| Key confidentiality | `FMCSA_WEBKEY` and `API_KEY` are never logged (verified in `app/services/fmcsa.py` and `app/auth.py`). |
| Container isolation | Docker image runs as non-root user `appuser`. |
| CORS | Configurable via `CORS_ORIGINS`. Restrict to known origins in production. |
| Rate manipulation | `POST /negotiation/evaluate-offer` reads `loadboard_rate` from the database, ignoring the caller-supplied value. |
| Input validation | All request bodies are Pydantic v2 models with strict validators. Cross-field business rules are enforced in `app/services/call_logging.py`. |
| Debug endpoint | `POST /calls/log-call-debug` is only registered when `DEBUG=true`. |

---

## FMCSA web key

The FMCSA QC API is a free US government service. To get a web key:

1. Submit a request at https://ask.fmcsa.dot.gov/app/ask (select "QC API access").
2. Approval typically takes 1–2 business days.
3. Add the key: `FMCSA_WEBKEY=your-key-here` and set `FMCSA_MOCK=false`.

While waiting (or if the API is geo-restricted in your environment), set `FMCSA_MOCK=true` — the mock returns realistic, deterministic responses with no network calls and is what CI uses.

---

## Extending

The codebase is intentionally minimal. Common next steps:

**PostgreSQL** — swap `DATABASE_URL` for a Postgres URL. SQLAlchemy handles it transparently. Add `psycopg2-binary` to `requirements.txt`.

**Alembic migrations** — add schema migration support for production database evolution without dropping tables.

**Rate limiting** — add `slowapi` middleware to `app/main.py` to protect against abuse (especially relevant once the API is public-facing).

**Observability** — instrument with OpenTelemetry. The structured JSON log format (`app/main.py:_configure_logging`) already makes logs indexable; add OTLP traces for request-level visibility.

**Auth upgrade** — replace the static `X-API-Key` with JWT or OAuth2 for multi-tenant or multi-agent deployments.

**Async database** — replace `sqlalchemy` sync sessions with `sqlalchemy.ext.asyncio` + `aiosqlite` for higher throughput on async routes.

---

## Discrepancies and known gaps

The following are honest observations about the current state of the codebase:

1. **`should_close` on Round 1/2 accept** — `should_close=true` is returned when the carrier's offer is at or below the loadboard rate in rounds 1 and 2 (accepted immediately). Tests in `test_negotiation.py` assert `should_close is False` for these cases. The test assertions are **wrong** — the implementation correctly returns `should_close=True` on an immediate accept (the negotiation is over). This is a test bug, not an application bug.

2. **`GET /metrics` vs `GET /dashboard`** — `GET /metrics` does not support date or equipment filters. For any filtered analytics, use `GET /dashboard`.

3. **No `GET /calls/{id}` endpoint** — individual call retrieval by ID is not implemented. Use `GET /calls` with filtering.

4. **SQLite concurrency** — WAL mode allows concurrent reads. For high write concurrency or multi-instance deployments, migrate to PostgreSQL.

5. **No request-level rate limiting** — the API has no built-in rate limiting. If exposed publicly, add `slowapi` or a gateway layer.

6. **`avg_margin_vs_loadboard` in `/metrics`** — computed as `avg(final_rate - initial_rate)` (dollar delta, not percentage), while `avg_margin_pct` in `/dashboard` is `avg((final_rate - loadboard_rate) / loadboard_rate)`. The two metrics are not directly comparable.

# Carrier Sales API

Backend REST API for an AI-powered inbound carrier sales voice agent. A freight broker's [HappyRobot](https://happyrobot.ai) voice agent calls this API during live phone conversations to verify carrier eligibility, search available loads, negotiate rates, and record call outcomes.

The agent handles all speech (ASR/LLM/TTS). This API handles all business logic — carrier verification against the FMCSA registry, load matching, rules-based rate negotiation, and a metrics dashboard feed.

## Architecture

```
Carrier (phone call)
      │
      ▼
HappyRobot (voice agent, cloud)
      │  POST /carriers/verify
      │  POST /loads/search
      │  POST /negotiation/evaluate-offer
      │  POST /calls/log
      ▼
Carrier Sales API  ◄──► SQLite
      │
      ▼
FMCSA QC API (carrier registry)
```

---

## Quick start — local (no Docker)

**Requirements:** Python 3.11+

```bash
cd carrier-sales-api

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements-dev.txt

cp .env.example .env
# Edit .env — set API_KEY and optionally FMCSA_WEBKEY

python scripts/seed_db.py        # populate 27 sample loads

uvicorn app.main:app --reload --port 8000
```

- Swagger UI → http://localhost:8000/docs
- Health check → http://localhost:8000/health

---

## Quick start — Docker

```bash
cp .env.example .env
# Edit .env

docker compose up --build -d

# Seed the database (first run only)
docker compose exec api python scripts/seed_db.py

# Tail logs
docker compose logs -f
```

The SQLite database is stored in `./data/` on your host — it persists across container restarts.

To stop: `docker compose down`

---

## How to get the FMCSA webKey

The FMCSA QC API is a free US government service. Access requires a webKey:

1. Go to https://ask.fmcsa.dot.gov/app/ask and submit a request for QC API access.
2. Approval typically takes 1–2 business days.
3. Add the key to `.env` as `FMCSA_WEBKEY=your-key-here` and set `FMCSA_MOCK=false`.

While waiting (or if the API is geo-restricted), set `FMCSA_MOCK=true` — the mock returns realistic responses with no network calls.

**Mock MC numbers for testing:**

| MC | Result |
|---|---|
| `123456` | Eligible — ACME TRUCKING LLC |
| `654321` | Eligible — SWIFT FREIGHT INC |
| `789012` | Eligible — BLUE RIDGE CARRIERS LLC |
| `000000` | Not found |
| `111111` | Not authorized to operate |
| any other | Eligible — GENERIC TRANSPORT LLC |

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `API_KEY` | **yes** | `dev-insecure-key` | Secret sent in `X-API-Key` header by HappyRobot |
| `FMCSA_WEBKEY` | yes (prod) | — | Free key from FMCSA (see above) |
| `FMCSA_MOCK` | no | `false` | `true` = skip real FMCSA calls |
| `DATABASE_URL` | no | `sqlite:///./data/carrier_sales.db` | SQLAlchemy URL |
| `PORT` | no | `8000` | Uvicorn port |
| `LOG_LEVEL` | no | `INFO` | `DEBUG` for verbose output |
| `CORS_ORIGINS` | no | `http://localhost:3000` | Comma-separated allowed origins |
| `MAX_ROUNDS` | no | `3` | Max negotiation rounds before reject |
| `MAX_MARGIN_PCT` | no | `0.12` | Absolute ceiling — broker never pays more than `rate × (1 + this)` |
| `ROUND1_CEILING_PCT` | no | `0.12` | Round 1: if offer exceeds `rate × (1+this)`, counter at `ROUND1_COUNTER_PCT` |
| `ROUND1_COUNTER_PCT` | no | `0.05` | Round 1 counter-offer: `rate × (1+this)` |
| `ROUND2_CEILING_PCT` | no | `0.10` | Round 2: tighter ceiling |
| `ROUND2_BLEND_RATIO` | no | `0.75` | Round 2: move this fraction of the way toward the carrier's offer |
| `ROUND3_ACCEPT_PCT` | no | `0.08` | Round 3: accept if offer ≤ `rate × (1+this)`, else reject |

---

## Endpoints

All endpoints except `/health` require `X-API-Key: <your key>` header.

### `GET /health`
```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### `POST /carriers/verify`
Verify a carrier's MC number against the FMCSA registry.
```bash
curl -X POST http://localhost:8000/carriers/verify \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"mc_number": "MC123456"}'
```
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

### `POST /loads/search`
Search available loads. All fields optional.
```bash
curl -X POST http://localhost:8000/loads/search \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "Chicago",
    "destination": "Atlanta",
    "equipment_type": "Dry Van",
    "pickup_date_from": "2026-04-19",
    "pickup_date_to": "2026-04-25",
    "max_results": 3
  }'
```

### `GET /loads/{load_id}`
```bash
curl http://localhost:8000/loads/LD-00001 \
  -H "X-API-Key: $API_KEY"
```

### `POST /negotiation/evaluate-offer`
Evaluate a carrier's counter-offer. The negotiation engine uses the rate stored in the database — the `loadboard_rate` field in the request is ignored to prevent manipulation.
```bash
curl -X POST http://localhost:8000/negotiation/evaluate-offer \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "load_id": "LD-00001",
    "loadboard_rate": 1500.0,
    "carrier_offer": 1700.0,
    "round": 1
  }'
```
```json
{
  "action": "counter",
  "counter_offer": 1575.0,
  "message_hint": "We can meet you halfway at $1,575.00.",
  "should_close": false
}
```
`action` is one of `accept`, `counter`, `reject`. When `should_close` is `true` the agent should end the negotiation.

### `POST /calls/log`
Record a completed call. If `outcome` is `booked`, the load is automatically marked as booked. Idempotent — send the same `id` multiple times to update.
```bash
curl -X POST http://localhost:8000/calls/log \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "mc_number": "123456",
    "carrier_name": "ACME TRUCKING LLC",
    "load_id": "LD-00001",
    "initial_rate": 1500.0,
    "final_rate": 1575.0,
    "num_negotiation_rounds": 1,
    "outcome": "booked",
    "sentiment": "positive",
    "transcript_summary": "Carrier agreed after one round.",
    "raw_extraction": {}
  }'
```
`outcome` values: `booked`, `no_agreement`, `carrier_not_eligible`, `no_loads_found`, `carrier_declined`, `other`.  
`sentiment` values: `positive`, `neutral`, `negative`.

### `GET /metrics`
Aggregated dashboard metrics.
```bash
curl http://localhost:8000/metrics -H "X-API-Key: $API_KEY"
```

### `GET /calls`
Paginated call history. Query params: `limit`, `offset`, `outcome`, `sentiment`, `from_date`, `to_date`.
```bash
curl "http://localhost:8000/calls?limit=10&outcome=booked" \
  -H "X-API-Key: $API_KEY"
```

---

## Running tests

```bash
# Install dev dependencies if not already done
pip install -r requirements-dev.txt

pytest -v
```

Tests use an in-memory SQLite database and the FMCSA mock — no network calls, no side effects.

---

## Seeding the database

```bash
python scripts/seed_db.py
```

Loads 27 realistic freight loads covering all equipment types, 10+ US routes, and 8 commodity types. Idempotent — safe to run multiple times.

---

## Connecting to HappyRobot

1. Deploy the API (see next section) or expose locally with `ngrok http 8000`.
2. In HappyRobot, create a new agent and add four *function calls*:

| Function | Method | Path |
|---|---|---|
| `verify_carrier` | `POST` | `/carriers/verify` |
| `search_loads` | `POST` | `/loads/search` |
| `evaluate_offer` | `POST` | `/negotiation/evaluate-offer` |
| `log_call` | `POST` | `/calls/log` |

3. Set `X-API-Key` as a static header in each function call definition.

---

## Deploying to the cloud

### Render (recommended — free tier)

1. Push the repo to GitHub.
2. Create a new **Web Service** on [render.com](https://render.com), point it at the repo.
3. Set runtime to **Docker**.
4. Add environment variables from `.env.example` in the Render dashboard.
5. Render builds the image and gives you a permanent URL.

### Railway / Fly.io

Both support Docker deploys with similar steps. Fly.io offers the most control; Railway is the fastest to set up.

---

## Security notes

- The `API_KEY` is compared with `secrets.compare_digest` to prevent timing attacks.
- The FMCSA `WEBKEY` and the `API_KEY` are never logged.
- The Docker image runs as a non-root user (`appuser`).
- CORS origins are configurable — restrict to your HappyRobot and dashboard domains in production.

---

## Next steps

- **PostgreSQL**: swap `DATABASE_URL` for a Postgres URL — SQLAlchemy supports it with no code changes (add `psycopg2-binary` to requirements).
- **Alembic migrations**: add schema migration support for production database evolution.
- **Rate limiting**: add `slowapi` middleware to protect against abuse.
- **Observability**: instrument with OpenTelemetry for traces and metrics in production.
- **Auth upgrade**: add JWT or OAuth2 for multi-tenant / multi-agent support.
- **Dashboard frontend**: consume `GET /metrics` and `GET /calls` from a React/Next.js app.

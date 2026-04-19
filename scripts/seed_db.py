"""Populate the database with loads and call_logs. Idempotent."""
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Allow running as `python scripts/seed_db.py` from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.models import Load, LoadStatus

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SEED_FILE = Path(__file__).parent.parent / "data" / "loads_seed.json"


def seed_loads(db: Session) -> tuple[int, int]:
    """Insert or update loads from the seed file. Returns (created, updated)."""
    raw = json.loads(SEED_FILE.read_text())
    created = updated = 0
    for item in raw:
        item["pickup_datetime"] = datetime.fromisoformat(item["pickup_datetime"])
        item["delivery_datetime"] = datetime.fromisoformat(item["delivery_datetime"])
        existing = db.get(Load, item["load_id"])
        if existing:
            for k, v in item.items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(Load(**item, status=LoadStatus.available))
            created += 1
    db.commit()
    return created, updated


def seed(loads_only: bool = False) -> None:
    init_db()
    with SessionLocal() as db:
        created, updated = seed_loads(db)
    logger.info("Loads seed complete — created: %d, updated: %d", created, updated)

    if not loads_only:
        from scripts.seed_call_logs import seed_call_logs
        seed_call_logs()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed database with loads and call_logs.")
    p.add_argument("--loads-only", action="store_true", help="Skip call_logs seed")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    seed(loads_only=args.loads_only)

"""Populate the database with loads from data/loads_seed.json. Idempotent."""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Allow running as `python scripts/seed_db.py` from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import SessionLocal, init_db
from app.models import Load, LoadStatus

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SEED_FILE = Path(__file__).parent.parent / "data" / "loads_seed.json"


def seed() -> None:
    init_db()
    raw = json.loads(SEED_FILE.read_text())

    with SessionLocal() as db:
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
                load = Load(**item, status=LoadStatus.available)
                db.add(load)
                created += 1
        db.commit()

    logger.info("Seed complete — created: %d, updated: %d", created, updated)


if __name__ == "__main__":
    seed()

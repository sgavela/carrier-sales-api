from __future__ import annotations

import logging
import logging.config

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import SessionLocal, init_db
from app.models import Load
from app.routers import calls as calls_router
from app.routers import carriers as carriers_router
from app.routers import dashboard as dashboard_router
from app.routers import loads as loads_router
from app.routers import metrics as metrics_router
from app.routers import negotiation as negotiation_router


def _configure_logging() -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "format": '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}'
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                }
            },
            "root": {"level": settings.LOG_LEVEL, "handlers": ["console"]},
        }
    )


_configure_logging()
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Carrier Sales API",
        description="Backend API for the HappyRobot inbound carrier sales voice agent.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def on_startup() -> None:
        init_db()
        _auto_seed()
        logger.info("Application startup complete")

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(carriers_router.router)
    app.include_router(loads_router.router)
    app.include_router(negotiation_router.router)
    app.include_router(calls_router.router)
    app.include_router(metrics_router.router)
    app.include_router(dashboard_router.router)

    return app


def _auto_seed() -> None:
    """Seed loads and call_logs on first boot (empty tables). Safe to call on every startup."""
    from scripts.seed_db import seed_loads
    from scripts.seed_call_logs import seed_call_logs
    from app.models import CallLog

    with SessionLocal() as db:
        loads_exist = db.query(Load).first() is not None
        calls_exist = db.query(CallLog).first() is not None

    if not loads_exist:
        with SessionLocal() as db:
            created, _ = seed_loads(db)
            if created:
                logger.info("Auto-seeded %d loads", created)

    if not calls_exist:
        logger.info("call_logs empty — seeding call logs...")
        seed_call_logs()
        logger.info("Auto-seeded call logs")


app = create_app()

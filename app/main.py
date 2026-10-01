from contextlib import asynccontextmanager
from pathlib import Path
import time
import uuid

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.admin.routes import router as admin_web_router
from app.api.v1.admin_api import router as admin_api_router
from app.api.v1.auth import router as admin_auth_router
from app.api.v1.catalog import router as public_catalog_router
from app.api.v1.community import (
    collections_router,
    community_library_router,
    offers_action_router,
    router as community_requests_router,
)
from app.api.v1.health import router as health_router
from app.api.v1.internal_bot import router as internal_bot_router
from app.api.v1.me import inventory_router, router as me_router
from app.core.config import settings
from app.core.errors import (
    BoconicException,
    boconic_exception_handler,
    generic_http_exception_handler,
)
from app.core.logging import logger
from app.db.session import engine

STATIC_DIR = Path(__file__).resolve().parent / "admin" / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: verify database connection
    logger.info(f"Starting Boconic v{app.version} in '{settings.APP_ENV}' mode...")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connectivity check: OK.")
    except Exception as e:
        logger.error(f"Database connection warning: {e}")

    yield

    # Shutdown
    logger.info("Gracefully shutting down Boconic...")
    await engine.dispose()
    logger.info("Database connection pools closed.")

def create_app() -> FastAPI:
    app = FastAPI(
        title="Boconic Platform API",
        version="2.0.0",
        description="Boconic Community Textbook & Educational Book Circulation Platform",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.APP_ENV == "development" else [settings.APP_BASE_URL],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID and Timing Middleware
    @app.middleware("http")
    async def request_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        request.state.request_id = req_id
        start_time = time.time()

        response: Response = await call_next(request)

        duration = time.time() - start_time
        response.headers["X-Request-Id"] = req_id
        response.headers["X-Process-Time"] = f"{duration:.4f}s"
        return response

    # Mount static assets for Admin Web Console
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/admin/static", StaticFiles(directory=str(STATIC_DIR)), name="admin_static")

    # Exception Handlers
    app.add_exception_handler(BoconicException, boconic_exception_handler)
    app.add_exception_handler(HTTPException, generic_http_exception_handler)

    # Health Probes
    app.include_router(health_router)

    # Public Discovery API (/api/v1/catalog)
    app.include_router(public_catalog_router, prefix="/api/v1")

    # Community Requests & Offers API (/api/v1/community-requests, /api/v1/offers)
    app.include_router(community_requests_router, prefix="/api/v1")
    app.include_router(offers_action_router, prefix="/api/v1")
    app.include_router(community_library_router, prefix="/api/v1")
    app.include_router(collections_router, prefix="/api/v1")

    # Personal Context & Inventory API (/api/v1/me, /api/v1/inventory)
    app.include_router(me_router, prefix="/api/v1")
    app.include_router(inventory_router, prefix="/api/v1")

    # Internal Bot Gateway API (/api/v1/internal/telegram)
    app.include_router(internal_bot_router, prefix="/api/v1")

    # Admin Auth API (/api/v1/admin/auth)
    app.include_router(admin_auth_router, prefix="/api/v1")

    # Admin Management API (/api/v1/admin)
    app.include_router(admin_api_router, prefix="/api/v1")

    # Admin Web Console (/admin)
    app.include_router(admin_web_router)

    return app

app = create_app()

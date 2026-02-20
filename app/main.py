"""
FastAPI application entry point.

Sets up the app, lifespan (DB connect/disconnect), CORS, logging,
and includes API routers. Background tasks run via BackgroundTasks.add_task()
in the documents router so uploads return immediately while processing continues.

Why async: All I/O (DB with Motor, future LLM HTTP calls) is non-blocking so
one process can handle many concurrent requests. PDF extraction runs in a
thread pool (asyncio.to_thread) so it doesn't block the event loop.
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents, timeline
from app.config import get_settings
from app.database import close_mongo_connection, connect_to_mongo

# Configure logging - single place for log format and level
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context: runs on startup and shutdown.
    We use it to connect to MongoDB at start and disconnect at end.
    """
    # Startup
    await connect_to_mongo()
    settings = get_settings()
    # Warn if JWT secret looks like a placeholder (causes 401 on every request)
    secret = settings.supabase_jwt_secret or ""
    if not secret:
        logger.warning("SUPABASE_JWT_SECRET is not set. Set it in .env to fix 401 Unauthorized.")
    elif len(secret) < 32 or "secret key" in secret.lower() or "your-" in secret.lower():
        logger.warning(
            "SUPABASE_JWT_SECRET looks like a placeholder. Get the real value from: "
            "Supabase Dashboard → Project Settings → API → JWT Secret (long random string). "
            "Update backend/.env then restart the server."
        )
    # Ensure upload directory exists for storing PDFs
    upload_path = Path(settings.upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)
    logger.info("Upload directory ready: %s", upload_path.resolve())
    yield
    # Shutdown
    await close_mongo_connection()


def create_application() -> FastAPI:
    """Factory for the FastAPI app. Keeps main.py clean and testable."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description="Extract and serve timelines from legal documents (PDF).",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS - allow frontend (e.g. Supabase app) to call this API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production to your frontend origin
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routers. Auth is a dependency (get_current_user) used by documents/timeline.
    app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
    app.include_router(timeline.router, prefix="/api/documents", tags=["timeline"])

    return app


app = create_application()

import logging
import redis as redis_lib
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import check_db_connection

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hireflow")

# ── LangSmith tracing (no-op if key is blank) ──────────────────────────────
if settings.LANGSMITH_API_KEY:
    import os
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("HireFlow AI starting up...")
    # Import all models so SQLAlchemy registers them (Alembic handles actual creation)
    import app.models  # noqa: F401
    logger.info("Models registered.")
    yield
    logger.info("HireFlow AI shutting down.")


# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="HireFlow AI API",
    description="Autonomous Campus Recruitment Operating System",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────
from app.api.auth import router as auth_router
from app.api.companies import router as companies_router
from app.api.campaigns import router as campaigns_router
from app.api.checkpoints import router as checkpoints_router
from app.api.colleges import router as colleges_router
from app.api.candidates import router as candidates_router
from app.api.resumes import router as resumes_router
from app.api.assessments import router as assessments_router
from app.api.interviews import router as interviews_router
from app.api.decisions import router as decisions_router
from app.api.offers import router as offers_router
from app.api.onboarding import router as onboarding_router
from app.api.dashboard import router as dashboard_router
from app.api.rag import router as rag_router
from app.api.websocket import router as websocket_router

app.include_router(auth_router)
app.include_router(companies_router)
app.include_router(campaigns_router)
app.include_router(checkpoints_router)
app.include_router(colleges_router)
app.include_router(candidates_router)
app.include_router(resumes_router)
app.include_router(assessments_router)
app.include_router(interviews_router)
app.include_router(decisions_router)
app.include_router(offers_router)
app.include_router(onboarding_router)
app.include_router(dashboard_router)
app.include_router(rag_router)
app.include_router(websocket_router)


# ── Health ──────────────────────────────────────────────────────────────────
@app.get("/api/v1/health", tags=["health"])
def health():
    db_ok = check_db_connection()

    redis_ok = False
    try:
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        r.ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    all_ok = db_ok and redis_ok
    return {
        "success": all_ok,
        "message": "All systems operational" if all_ok else "Some services degraded",
        "data": {
            "status": "healthy" if all_ok else "degraded",
            "services": {
                "database": "green" if db_ok else "red",
                "redis": "green" if redis_ok else "red",
                "groq": "configured" if settings.GROQ_API_KEY else "not_configured",
                "sendgrid": "configured" if settings.SENDGRID_API_KEY else "not_configured",
                "clerk": "configured" if settings.CLERK_SECRET_KEY else "not_configured",
            },
        },
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat(), "version": "3.0.0"},
    }

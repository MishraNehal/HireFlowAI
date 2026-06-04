import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database.session import engine, Base

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("hireflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle handler."""
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)

    logger.info("Starting RAG ingestion (ChromaDB)...")
    try:
        from app.rag.ingest import run_ingestion
        run_ingestion()
        logger.info("RAG ingestion complete.")
    except Exception as e:
        logger.warning(f"RAG ingestion failed (non-fatal): {e}")

    yield
    logger.info("HireFlowAI shutting down.")


app = FastAPI(
    title="HireFlowAI API",
    description="Automated AI Recruiter screening and interviewing platform.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
from app.routers import jobs, candidates, pipelines, hiring_requests, jd_generation, offer, dashboard
app.include_router(hiring_requests.router)
app.include_router(jd_generation.router)
app.include_router(jobs.router)
app.include_router(candidates.router)
app.include_router(pipelines.router)
app.include_router(offer.router)
app.include_router(dashboard.router)


@app.get("/")
def read_root():
    return {"message": "Welcome to HireFlowAI API", "version": "1.0.0", "status": "running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

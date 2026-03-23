"""
FastAPI application entry point
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os

from app.database import engine, Base
from app.api import auth, cdr, dashboard, admin, agent_performance
from app.clients.fusionpbx import get_fusion_client, close_fusion_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Additional file logging for easy retrieval when docker logs interface is limited
log_file_path = os.getenv("BACKEND_LOG_FILE", "/app/backend.log")
try:
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    file_handler.setFormatter(file_formatter)
    logging.getLogger().addHandler(file_handler)
except OSError:
    logger.warning("File logging is disabled because log path is not writable: %s", log_file_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager - handles startup and shutdown
    """
    # Startup
    logger.info("Application startup - initializing components")
    
    # Create database tables
    Base.metadata.create_all(bind=engine)
    
    # Initialize FusionPBX client
    await get_fusion_client()
    logger.info("FusionPBX client initialized")
    
    yield
    
    # Shutdown
    logger.info("Application shutdown - cleaning up")
    await close_fusion_client()
    logger.info("FusionPBX client closed")


# Create FastAPI app
app = FastAPI(
    title="FusionPBX Analytics API",
    description="API for FusionPBX call center analytics and reporting",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="", tags=["Authentication"])
app.include_router(cdr.router, tags=["CDR"])
app.include_router(dashboard.router, tags=["Dashboard"])
app.include_router(admin.router, tags=["Admin"])
app.include_router(agent_performance.router, tags=["Agent Performance"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "FusionPBX Analytics API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

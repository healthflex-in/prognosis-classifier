"""
FastAPI backend for Clinical Dashboard.
Reads triage classification JSON files and serves data to the frontend.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.routes import patients, stats, performance, matrix, triage

app = FastAPI(
    title="Clinical Dashboard API",
    description="API for serving patient triage classification data",
    version="1.0.0"
)

# CORS configuration
# Allow specific origins for development (add production URL when deploying)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:8013",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:8013",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(patients.router, prefix="/api")
app.include_router(stats.router, prefix="/api/stats")
app.include_router(performance.router, prefix="/api/performance")
app.include_router(matrix.router, prefix="/api/matrix")
app.include_router(triage.router, prefix="/api")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Clinical Dashboard API"}

@app.get("/")
async def root():
    """Root endpoint."""
    # Get processing progress
    from api.progress_tracker import get_progress
    from api.data_loader import get_all_patients
    
    progress = get_progress()
    patients = get_all_patients()
    
    return {
        "message": "Clinical Dashboard API",
        "version": "1.0.0",
        "processing": {
            "status": progress.get("status", "idle"),
            "current": progress.get("current", 0),
            "total": progress.get("total", 0),
            "started_at": progress.get("started_at"),
            "completed_at": progress.get("completed_at")
        },
        "patients": {
            "total_classified": len(patients),
            "in_classification_file": len(patients)
        },
        "endpoints": {
            "patients": "/api/patients",
            "stats": "/api/stats/*",
            "performance": "/api/performance/*",
            "matrix": "/api/matrix/*",
            "triage_progress": "/api/triage/progress"
        }
    }

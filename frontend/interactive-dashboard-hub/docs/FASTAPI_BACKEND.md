# FastAPI Backend Reference

This document describes the FastAPI backend structure required to connect to this clinical dashboard.

## Setup

```bash
pip install fastapi uvicorn pydantic
```

## main.py

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import patients, stats, performance, matrix

app = FastAPI(title="Clinical Dashboard API")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(patients.router, prefix="/api")
app.include_router(stats.router, prefix="/api/stats")
app.include_router(performance.router, prefix="/api/performance")
app.include_router(matrix.router, prefix="/api/matrix")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

## routes/patients.py

```python
from fastapi import APIRouter, Query
from typing import Optional, List
from models.patient import Patient, Criticality, TimelineStatus, RiskLevel

router = APIRouter()

@router.get("/patients", response_model=List[Patient])
async def get_patients(
    criticality: Optional[Criticality] = Query(None),
    timeline: Optional[TimelineStatus] = Query(None),
    risk: Optional[RiskLevel] = Query(None),
    joint_group: Optional[str] = Query(None),
    testing_focus: Optional[str] = Query(None),
):
    # Filter and return patients from database
    pass
```

## routes/stats.py

```python
from fastapi import APIRouter, Query
from typing import Optional, List
from pydantic import BaseModel

router = APIRouter()

class CountStats(BaseModel):
    name: str
    value: int

class StackedCountStats(BaseModel):
    name: str
    value: int
    High: Optional[int] = 0
    Medium: Optional[int] = 0
    Low: Optional[int] = 0

@router.get("/criticality", response_model=List[CountStats])
async def get_criticality_stats(
    timeline: Optional[str] = Query(None),
    risk: Optional[str] = Query(None),
):
    # Return: [{"name": "High", "value": 3}, {"name": "Medium", "value": 3}]
    pass

@router.get("/timeline", response_model=List[StackedCountStats])
async def get_timeline_stats(
    criticality: Optional[str] = Query(None),
    risk: Optional[str] = Query(None),
):
    # Return: [{"name": "Acute", "value": 3, "High": 1, "Medium": 2}, ...]
    pass

@router.get("/risk", response_model=List[CountStats])
async def get_risk_stats():
    # Return: [{"name": "Low", "value": 5}, {"name": "High", "value": 1}]
    pass

@router.get("/joint-group", response_model=List[dict])
async def get_joint_group_stats():
    # Return with testing focus breakdown
    pass

@router.get("/testing-focus", response_model=List[CountStats])
async def get_testing_focus_stats():
    pass
```

## routes/performance.py

```python
from fastapi import APIRouter, Query
from typing import Optional, List
from pydantic import BaseModel

router = APIRouter()

class AsymmetryData(BaseModel):
    name: str
    value: float
    category: Optional[str] = None

class ScatterData(BaseModel):
    x: float
    y: float
    name: str
    category: Optional[str] = None

class DistributionBin(BaseModel):
    range: str
    min: float
    max: float
    count: int

@router.get("/asymmetry", response_model=List[AsymmetryData])
async def get_asymmetry_data(
    criticality: Optional[str] = Query(None),
    joint_group: Optional[str] = Query(None),
):
    # Return: [{"name": "Patient A", "value": 36.9, "category": "High"}, ...]
    pass

@router.get("/asymmetry-force", response_model=List[ScatterData])
async def get_asymmetry_force_data():
    # Return: [{"x": 36.9, "y": 2, "name": "Patient A", "category": "High"}, ...]
    # y values: Low=1, Medium=2, High=3
    pass

@router.get("/distribution", response_model=List[DistributionBin])
async def get_distribution_data():
    # Return: [{"range": "0-10%", "min": 0, "max": 10, "count": 1}, ...]
    pass
```

## routes/matrix.py

```python
from fastapi import APIRouter
from typing import List
from pydantic import BaseModel

router = APIRouter()

class MatrixCell(BaseModel):
    xLabel: str  # Criticality
    yLabel: str  # Risk Level
    value: int   # Count

@router.get("/risk-criticality", response_model=List[MatrixCell])
async def get_risk_criticality_matrix():
    # Return: [{"xLabel": "High", "yLabel": "Low", "value": 2}, ...]
    pass
```

## models/patient.py

```python
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

class Criticality(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

class Goal(str, Enum):
    RTA = "RTA"
    RTS = "RTS"

class TimelineStatus(str, Enum):
    ACUTE = "Acute"
    SUB_ACUTE = "Sub-Acute"
    CHRONIC = "Chronic"

class RiskLevel(str, Enum):
    LOW = "Low"
    HIGH = "High"

class TestingFocus(str, Enum):
    FORCE_FRAME = "ForceFrame"
    FORCE_DECK = "ForceDeck"
    STANDARD = "Standard"

class ForceLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"

class Patient(BaseModel):
    id: str
    patientName: str
    criticality: Criticality
    goal: Goal
    timelineStatus: TimelineStatus
    riskLevel: RiskLevel
    jointGroup: str
    primaryJoint: str
    testingFocus: TestingFocus
    strengthAsymmetry: Optional[float] = None
    absoluteForceLevel: Optional[ForceLevel] = None
    psychosocialFlags: Optional[List[str]] = []
```

## Running the API

```bash
uvicorn main:app --reload --port 8000
```

## Connecting to Frontend

Set the `VITE_API_URL` environment variable in your frontend:

```env
VITE_API_URL=http://localhost:8000
```

The frontend will use mock data when the API is unavailable, making development easier.

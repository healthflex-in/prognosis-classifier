# Clinical Dashboard API

FastAPI backend for serving patient triage classification data to the frontend dashboard.

## Setup

1. Install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

2. Start the API server:
```bash
# Option 1: Using the shell script
./start_api.sh

# Option 2: Direct uvicorn command
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

## API Endpoints

### Health Check
- `GET /health` - Health check endpoint
- `GET /` - API information

### Patients
- `GET /api/patients` - Get all patients with optional filters
  - Query params: `criticality`, `timeline`, `risk`, `joint_group`, `testing_focus`

### Statistics
- `GET /api/stats/criticality` - Criticality distribution
- `GET /api/stats/timeline` - Timeline status distribution with criticality breakdown
- `GET /api/stats/risk` - Risk level distribution
- `GET /api/stats/joint-group` - Joint group distribution with testing focus breakdown
- `GET /api/stats/testing-focus` - Testing focus distribution

### Performance
- `GET /api/performance/asymmetry` - Asymmetry data for lollipop chart
- `GET /api/performance/asymmetry-force` - Asymmetry vs force scatter plot data
- `GET /api/performance/distribution` - Asymmetry distribution histogram data

### Matrix
- `GET /api/matrix/risk-criticality` - Risk vs criticality matrix for heatmap

## Data Source

The API automatically loads the most recent triage classification JSON file from:
`backend/LLM/triage_classifications_*.json`

The file is selected based on modification time (most recent first).

## Frontend Connection

Set the `VITE_API_URL` environment variable in your frontend:
```env
VITE_API_URL=http://localhost:8000
```

Or create a `.env` file in the frontend directory:
```
VITE_API_URL=http://localhost:8000
```

## Testing

You can test the API using curl or visit the interactive docs at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

Example:
```bash
curl http://localhost:8000/api/patients
curl http://localhost:8000/api/stats/criticality
```


# Clinical Dashboard with Per-Widget Query Configuration

## Overview
Transform the current dashboard into a clinical patient monitoring system with:
1. Per-widget query/data source configuration
2. FastAPI backend integration 
3. Comprehensive clinical visualizations for patient data

---

## Widget Types and Chart Recommendations

Based on your clinical data requirements, here are the specific widget types to implement:

### Classification Widgets (Top Row)
| Widget | Chart Type | Purpose |
|--------|-----------|---------|
| Criticality Distribution | Vertical Bar Chart | Workload/triage overview - High vs Medium cases |
| Timeline Status | Stacked Bar Chart | Case mix by chronicity (Acute/Sub-Acute/Chronic) |
| Risk Level | Bar Chart | Distribution of Low vs High risk patients |

### Clinical Grouping Widgets (Middle Row)
| Widget | Chart Type | Purpose |
|--------|-----------|---------|
| Joint Group Mix | Grouped Bar Chart | Posterior vs Anterior Chain vs Other |
| Testing Modality | Bar Chart | ForceFrame vs ForceDeck vs Standard usage |

### Performance/VALD Widgets (Bottom Row)
| Widget | Chart Type | Purpose |
|--------|-----------|---------|
| Asymmetry by Patient | Lollipop/Dot Plot | Identify most asymmetric patients, with threshold line |
| Asymmetry vs Force | Scatter Plot | Relationship between asymmetry % and force level |
| Asymmetry Distribution | Histogram/Box Plot | Overall cohort spread |
| Risk vs Criticality | Heatmap | Psychosocial risk overlap with severity |

### Data Table Widget
| Widget | Columns |
|--------|---------|
| Master Patient Table | Patient Name, Criticality, Goal (RTA/RTS), Timeline, Risk Level, Joint Group, Primary Joint, Testing Focus, Strength Asymmetry %, Force Level |

---

## Technical Implementation

### 1. New Type Definitions (`src/types/dashboard.ts`)

```text
+------------------------------------------+
|  WidgetType (Extended)                   |
+------------------------------------------+
| - id: string                             |
| - type: chart type enum                  |
| - title: string                          |
| - queryConfig: QueryConfig               |  <-- NEW
| - minW, minH                             |
+------------------------------------------+

+------------------------------------------+
|  QueryConfig                             |
+------------------------------------------+
| - endpoint: string (FastAPI route)       |
| - params: Record<string, string>         |
| - refreshInterval?: number               |
| - filters?: FilterConfig[]               |
+------------------------------------------+

+------------------------------------------+
|  PatientData (Clinical)                  |
+------------------------------------------+
| - patientName: string                    |
| - criticality: "High" | "Medium"         |
| - goal: "RTA" | "RTS"                    |
| - timelineStatus: "Acute" | "Sub-Acute"  |
|                   | "Chronic"            |
| - riskLevel: "Low" | "High"              |
| - jointGroup: string                     |
| - primaryJoint: string                   |
| - testingFocus: "ForceFrame" |           |
|                 "ForceDeck" | "Standard" |
| - strengthAsymmetry: number | null       |
| - absoluteForceLevel: "Low" | "Medium"   |
|                       | "High" | null    |
+------------------------------------------+
```

### 2. New Chart Widget Types

Extend the current widget type enum:

```
"bar" | "stacked-bar" | "grouped-bar" | "scatter" | 
"lollipop" | "histogram" | "heatmap" | "pie" | 
"stats" | "table" | "progress"
```

### 3. Widget Configuration Dialog

New `WidgetConfigDialog` component allowing users to:
- Select data endpoint from predefined list
- Configure query parameters
- Set refresh interval
- Add filters (Criticality, Timeline, Risk Level, etc.)

### 4. FastAPI Endpoints Structure

The FastAPI backend should provide these endpoints:

| Endpoint | Returns | Used By |
|----------|---------|---------|
| `GET /api/patients` | Full patient list | Master table |
| `GET /api/stats/criticality` | Count by criticality | Bar chart |
| `GET /api/stats/timeline` | Count by timeline status | Bar chart |
| `GET /api/stats/risk` | Count by risk level | Bar chart |
| `GET /api/stats/joint-group` | Count by joint group | Bar chart |
| `GET /api/stats/testing-focus` | Count by testing modality | Bar chart |
| `GET /api/performance/asymmetry` | Asymmetry data per patient | Lollipop/Scatter |
| `GET /api/performance/distribution` | Histogram bins | Histogram |
| `GET /api/matrix/risk-criticality` | Cross-tabulation counts | Heatmap |

All endpoints accept query params:
- `criticality`: Filter by High/Medium
- `timeline`: Filter by Acute/Sub-Acute/Chronic
- `risk`: Filter by Low/High
- `joint_group`: Filter by joint classification

---

## New Files to Create

### Frontend Components

| File | Purpose |
|------|---------|
| `src/components/dashboard/WidgetConfigDialog.tsx` | Per-widget query configuration UI |
| `src/components/dashboard/charts/BarChartWidget.tsx` | Configurable bar chart |
| `src/components/dashboard/charts/StackedBarWidget.tsx` | Stacked bar chart |
| `src/components/dashboard/charts/ScatterWidget.tsx` | Scatter plot with colored points |
| `src/components/dashboard/charts/LollipopWidget.tsx` | Dot/lollipop chart with threshold line |
| `src/components/dashboard/charts/HistogramWidget.tsx` | Distribution histogram |
| `src/components/dashboard/charts/HeatmapWidget.tsx` | 2D matrix heatmap |
| `src/components/dashboard/PatientTableWidget.tsx` | Clinical patient master table |
| `src/hooks/useWidgetData.ts` | Custom hook for fetching widget data from FastAPI |
| `src/lib/api.ts` | API client configuration and helper functions |
| `src/types/clinical.ts` | Clinical data type definitions |

### FastAPI Backend Structure (Reference)

```
fastapi_backend/
├── main.py              # FastAPI app entry point
├── routes/
│   ├── patients.py      # Patient CRUD endpoints
│   ├── stats.py         # Aggregation endpoints
│   └── performance.py   # VALD metrics endpoints
├── models/
│   └── patient.py       # Pydantic models
└── services/
    └── data_service.py  # Business logic
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/types/dashboard.ts` | Add QueryConfig, PatientData, extended WidgetType enum |
| `src/components/dashboard/WidgetWrapper.tsx` | Add settings/config button |
| `src/components/dashboard/AddWidgetDialog.tsx` | Include new chart types |
| `src/components/dashboard/DashboardGrid.tsx` | Handle new widget types, pass config |
| `src/pages/Index.tsx` | State management for widget configs |
| `src/data/mockData.ts` | Add clinical mock data for development |

---

## Implementation Flow

```text
User Adds Widget
       │
       ▼
┌─────────────────────────┐
│  AddWidgetDialog        │
│  (Select chart type)    │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  WidgetConfigDialog     │
│  - Select endpoint      │
│  - Configure params     │
│  - Set filters          │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  Widget Created with    │
│  queryConfig attached   │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  useWidgetData hook     │
│  - Fetches from FastAPI │
│  - Handles loading      │
│  - Auto-refresh         │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  Chart renders with     │
│  live data              │
└─────────────────────────┘
```

---

## Widget Configuration UI Preview

Each widget will have a settings icon that opens a configuration panel:

```text
┌────────────────────────────────────┐
│  Configure Widget                  │
├────────────────────────────────────┤
│  Data Source:                      │
│  ┌──────────────────────────────┐  │
│  │ Criticality Distribution  ▼  │  │
│  └──────────────────────────────┘  │
│                                    │
│  Endpoint:                         │
│  /api/stats/criticality            │
│                                    │
│  Filters:                          │
│  ┌──────────────────────────────┐  │
│  │ Timeline: All            ▼  │  │
│  └──────────────────────────────┘  │
│  ┌──────────────────────────────┐  │
│  │ Risk Level: All          ▼  │  │
│  └──────────────────────────────┘  │
│                                    │
│  Refresh Interval:                 │
│  ○ None  ○ 30s  ● 1min  ○ 5min    │
│                                    │
│  [Cancel]              [Save]      │
└────────────────────────────────────┘
```

---

## Technical Considerations

### API Integration
- Use TanStack Query (already installed) for data fetching and caching
- Configure base URL via environment variable (`VITE_API_URL`)
- Handle CORS on FastAPI side
- Implement loading and error states in widgets

### Error Handling
- Show skeleton loaders during fetch
- Display error messages within widget bounds
- Retry mechanism for failed requests

### Performance
- Memoize chart components to prevent unnecessary re-renders
- Use query caching to reduce API calls
- Lazy load chart libraries for initial page speed


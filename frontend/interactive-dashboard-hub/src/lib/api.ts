// API client configuration for FastAPI backend
import { ClinicalFilters } from "@/types/clinical";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8013";

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  params?: Record<string, string | undefined>;
}

export async function apiRequest<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { method = "GET", body, params } = options;

  // Build URL with query params
  const url = new URL(`${API_BASE_URL}${endpoint}`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") {
        url.searchParams.append(key, value);
      }
    });
  }

  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };

  const config: RequestInit = {
    method,
    headers,
    // Don't use credentials - not needed for this API
    // credentials: "include",
  };

  if (body) {
    config.body = JSON.stringify(body);
  }

  console.log(`🌐 API Request: ${method} ${url.toString()}`);

  try {
    const response = await fetch(url.toString(), config);

    if (!response.ok) {
      const error = await response.text();
      console.error(`❌ API Error ${response.status}:`, error);
      throw new Error(`API Error: ${response.status} - ${error}`);
    }

    const data = await response.json();
    console.log(`✅ API Response from ${endpoint}:`, Array.isArray(data) ? `${data.length} items` : 'object');
    return data;
  } catch (error) {
    console.error(`❌ API Request failed for ${endpoint}:`, error);
    throw error;
  }
}

// Helper to convert ClinicalFilters to query params
export function filtersToParams(
  filters?: ClinicalFilters
): Record<string, string | undefined> {
  if (!filters) return {};
  return {
    criticality: filters.criticality,
    timeline: filters.timelineStatus,
    risk: filters.riskLevel,
    joint_group: filters.jointGroup,
    testing_focus: filters.testingFocus,
  };
}

// API Endpoints
export const endpoints = {
  patients: "/api/patients",
  // Legacy endpoints (still supported)
  statsCriticality: "/api/stats/criticality",
  statsTimeline: "/api/stats/timeline",
  statsRisk: "/api/stats/risk",
  statsJointGroup: "/api/stats/joint-group",
  statsTestingFocus: "/api/stats/testing-focus",
  performanceAsymmetry: "/api/performance/asymmetry",
  performanceAsymmetryForce: "/api/performance/asymmetry-force",
  performanceDistribution: "/api/performance/distribution",
  matrixRiskCriticality: "/api/matrix/risk-criticality",
  // New Master Prompt endpoints
  statsDiagnosis: "/api/stats/diagnosis",
  statsJointRegion: "/api/stats/joint-region",
  statsOccupation: "/api/stats/occupation",
  statsActivityProfile: "/api/stats/activity-profile",
  statsActivityRecreational: "/api/stats/activity-recreational",
  statsClinicalStage: "/api/stats/clinical-stage",
  statsPainInterference: "/api/stats/pain-interference",
  nprsAvailability: "/api/stats/nprs-availability",
  nprsDistribution: "/api/stats/nprs-distribution",
  painNprsMatrix: "/api/matrix/pain-nprs",
  intentStats: "/api/stats/intent",
  // Triage endpoints
  triageRun: "/api/triage/run",
  triageStatus: "/api/triage/status",
  triageProgress: "/api/triage/progress",
} as const;

export type EndpointKey = keyof typeof endpoints;

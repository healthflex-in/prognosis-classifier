import { useQuery } from "@tanstack/react-query";
import { apiRequest, filtersToParams } from "@/lib/api";
import { QueryConfig } from "@/types/dashboard";

interface UseWidgetDataOptions<T> {
  queryConfig: QueryConfig;
  enabled?: boolean;
  fallbackData?: T;
}

export function useWidgetData<T>({
  queryConfig,
  enabled = true,
  fallbackData,
}: UseWidgetDataOptions<T>) {
  const { endpoint, params, refreshInterval, filters } = queryConfig;

  // Combine params with filters
  const queryParams = {
    ...params,
    ...filtersToParams(filters),
  };

  return useQuery<T>({
    queryKey: ["widget-data", endpoint, queryParams],
    queryFn: async () => {
      try {
        const data = await apiRequest<T>(endpoint, { params: queryParams });
        console.log(`✅ API data loaded for ${endpoint}:`, data?.length || 'object');
        return data;
      } catch (error) {
        // Return fallback data in development/when API not available
        if (fallbackData !== undefined) {
          console.warn(`⚠️ API call failed for ${endpoint}, using fallback data:`, error);
          return fallbackData;
        }
        throw error;
      }
    },
    enabled,
    refetchInterval: refreshInterval ? refreshInterval * 1000 : false,
    retry: 2,
    staleTime: refreshInterval && refreshInterval < 10 ? 0 : 30000, // No cache when polling frequently (during triage)
  });
}

// Hook for checking if API is available
export function useApiHealth() {
  return useQuery({
    queryKey: ["api-health"],
    queryFn: async () => {
      try {
        const response = await fetch(
          `${import.meta.env.VITE_API_URL || "http://localhost:8013"}/health`
        );
        return response.ok;
      } catch {
        return false;
      }
    },
    retry: false,
    staleTime: 60000,
  });
}

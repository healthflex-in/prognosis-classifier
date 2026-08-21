import { useQuery } from "@tanstack/react-query";
import { apiRequest, endpoints } from "@/lib/api";

export function useTriageStatus() {
  return useQuery<{
    status: string;
    current: number;
    total: number;
    message?: string | null;
    output_file?: string | null;
  }>({
    queryKey: ["triage-progress"],
    queryFn: async () => {
      try {
        return await apiRequest<{
          status: string;
          current: number;
          total: number;
          message?: string | null;
          output_file?: string | null;
        }>(endpoints.triageProgress);
      } catch (error) {
        return {
          status: "idle",
          current: 0,
          total: 0,
          message: null,
          output_file: null,
        };
      }
    },
    refetchInterval: 2000, // Poll every 2 seconds
    retry: false,
    staleTime: 0, // Always consider stale to force refetch
  });
}

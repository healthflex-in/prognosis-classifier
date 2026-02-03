import { Search, Bell, Calendar, RefreshCw } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { DashboardFilters } from "@/types/dashboard";
import AddWidgetDialog from "./AddWidgetDialog";
import TriageRunDialog from "./TriageRunDialog";
import { WidgetType } from "@/types/dashboard";
import { useState, useEffect } from "react";
import { apiRequest, endpoints } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

interface DashboardHeaderProps {
  filters: DashboardFilters;
  onFilterChange: (filters: DashboardFilters) => void;
  onAddWidget: (widget: WidgetType) => void;
  existingWidgets: string[];
  onRefresh?: () => void;
  onProgressChange?: (progress: { current: number; total: number; status: string; error?: string | null }) => void;
}

const periodOptions: DashboardFilters["period"][] = ["Day", "Week", "Month", "Year"];

const DashboardHeader = ({
  filters,
  onFilterChange,
  onAddWidget,
  existingWidgets,
  onRefresh,
  onProgressChange,
}: DashboardHeaderProps) => {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [progress, setProgress] = useState<{ current: number; total: number; status: string; error?: string | null; message?: string | null } | null>(null);
  const [showTriageDialog, setShowTriageDialog] = useState(false);
  const { toast } = useToast();

  // Poll for progress when refreshing
  useEffect(() => {
    if (!isRefreshing) {
      // Reset progress when not refreshing
      setProgress(null);
      return;
    }

    let intervalId: NodeJS.Timeout | null = null;
    let timeoutId: NodeJS.Timeout | null = null;
    let maxTimeout: NodeJS.Timeout | null = null;

    const pollProgress = async () => {
      try {
        const progressData = await apiRequest<{
          status: string;
          current: number;
          total: number;
          error?: string | null;
          message?: string | null;
        }>(endpoints.triageProgress);

        const progressState = {
          current: progressData.current || 0,
          total: progressData.total || 0,
          status: progressData.status || "idle",
          error: progressData.error || null,
          message: progressData.message || null,
        };

        setProgress(progressState);

        // Notify parent component
        if (onProgressChange) {
          onProgressChange(progressState);
        }

        // If completed or error, stop polling
        if (progressData.status === "completed" || progressData.status === "error") {
          setIsRefreshing(false);
          if (intervalId) clearTimeout(intervalId);
          if (maxTimeout) clearTimeout(maxTimeout);
          
          if (progressData.status === "completed") {
            // Check status to see if file is ready
            setTimeout(async () => {
              try {
                const status = await apiRequest<{ status: string; latest_file?: string }>(
                  endpoints.triageStatus
                );
                
                if (status.status === "ready") {
                  toast({
                    title: "Classification Complete",
                    description: "Dashboard data has been updated.",
                  });
                  
                  if (onRefresh) {
                    onRefresh();
                  }
                  
                  // Force a page refresh to reload all data
                  window.location.reload();
                }
              } catch (error) {
                console.error("Error checking final status:", error);
              }
            }, 1000);
          } else if (progressData.status === "error") {
            toast({
              title: "Classification Error",
              description: progressData.error || "An error occurred during classification.",
              variant: "destructive",
            });
          }
          return;
        }

        // Continue polling if still running (check status, not isRefreshing state)
        if (progressData.status === "running") {
          intervalId = setTimeout(pollProgress, 1000); // Poll every 1 second
        }
      } catch (error) {
        console.error("Error polling progress:", error);
        // Continue polling even on error
        intervalId = setTimeout(pollProgress, 2000);
      }
    };

    // Start polling after a short delay
    timeoutId = setTimeout(pollProgress, 500);

    // Set a maximum timeout (5 minutes)
    maxTimeout = setTimeout(() => {
      setIsRefreshing(false);
      setProgress(null);
      if (intervalId) clearTimeout(intervalId);
      if (timeoutId) clearTimeout(timeoutId);
      toast({
        title: "Refresh Timeout",
        description: "Classification is taking longer than expected. Please check manually.",
        variant: "default",
      });
    }, 5 * 60 * 1000);

    return () => {
      if (timeoutId) clearTimeout(timeoutId);
      if (intervalId) clearTimeout(intervalId);
      if (maxTimeout) clearTimeout(maxTimeout);
    };
  }, [isRefreshing, onProgressChange, onRefresh, toast]);

  const handleRunTriage = async (monthsBack: number | null, limit: number | null) => {
    setIsRefreshing(true);
    try {
      // Trigger triage agent with user-selected parameters
      // Convert 0 to null to mean "all patients"
      const requestBody: {
        months_back?: number | null;
        limit?: number | null;
      } = {};
      
      if (monthsBack !== null && monthsBack > 0) {
        requestBody.months_back = monthsBack;
      }
      
      if (limit !== null && limit > 0) {
        requestBody.limit = limit;
      }
      // If both are null/empty, send empty object which will default to "all patients"

      const response = await apiRequest<{ status: string; message: string }>(
        endpoints.triageRun,
        {
          method: "POST",
          body: requestBody,
        }
      );

      toast({
        title: "Triage Agent Started",
        description: response.message || "Classification is running in the background...",
      });

      // Progress polling is handled by useEffect
      
    } catch (error) {
      setIsRefreshing(false);
      console.error("Error triggering triage agent:", error);
      toast({
        title: "Refresh Failed",
        description: "Failed to start triage agent. Please try again.",
        variant: "destructive",
      });
    }
  };

  const handleRefreshClick = () => {
    setShowTriageDialog(true);
  };

  return (
    <header className="bg-card border-b border-border px-6 py-4">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
        </div>

        <div className="flex items-center gap-3 ml-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefreshClick}
            disabled={isRefreshing}
            className="gap-2"
          >
            <RefreshCw className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
            <span>{isRefreshing ? "Refreshing..." : "Refresh Data"}</span>
          </Button>
          
          <TriageRunDialog
            open={showTriageDialog}
            onOpenChange={setShowTriageDialog}
            onRun={handleRunTriage}
          />
          
          <AddWidgetDialog onAddWidget={onAddWidget} existingWidgets={existingWidgets} />
          
          <Button variant="ghost" size="icon" className="relative">
            <Bell className="h-5 w-5 text-muted-foreground" />
            <span className="absolute top-1 right-1 w-2 h-2 bg-destructive rounded-full" />
          </Button>

          <div className="w-9 h-9 rounded-full bg-primary flex items-center justify-center">
            <span className="text-sm font-medium text-primary-foreground">JD</span>
          </div>
        </div>
      </div>
    </header>
  );
};

export default DashboardHeader;

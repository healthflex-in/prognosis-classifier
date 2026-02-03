import { Progress } from "@/components/ui/progress";

interface ProgressBarProps {
  current: number;
  total: number;
  status: string;
  error?: string | null;
  message?: string | null;
}

export const ProgressBar = ({ current, total, status, error, message }: ProgressBarProps) => {
  if (status === "idle" || status === "completed") {
    return null;
  }

  const percentage = total > 0 ? Math.round((current / total) * 100) : 0;
  
  // Determine display text
  let statusText = "Processing...";
  if (message) {
    statusText = message;
  } else if (status === "running") {
    statusText = total > 0 ? "Classifying Patients..." : "Preparing...";
  } else if (status === "error") {
    statusText = "Error";
  }

  return (
    <div className="w-full bg-muted/50 border-b border-border">
      <div className="container mx-auto px-6 py-3">
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-foreground">
                {statusText}
              </span>
              {total > 0 && (
                <span className="text-sm text-muted-foreground">
                  {current} / {total} patients
                </span>
              )}
            </div>
            {total > 0 ? (
              <Progress value={percentage} className="h-2" />
            ) : (
              <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
                <div className="h-full bg-primary animate-pulse" style={{ width: "100%" }} />
              </div>
            )}
            {error && (
              <p className="text-xs text-destructive mt-2">{error}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

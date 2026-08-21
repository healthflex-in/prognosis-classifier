import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface HeatmapWidgetProps {
  data: Array<{
    xLabel: string;
    yLabel: string;
    value: number;
  }>;
  isLoading?: boolean;
  title?: string;
  xLabels?: string[];
  yLabels?: string[];
  onCellClick?: (data: { xLabel: string; yLabel: string; filters?: Record<string, string> }) => void;
}

const HeatmapWidget = ({
  data,
  isLoading = false,
  title,
  xLabels,
  yLabels,
  onCellClick,
}: HeatmapWidgetProps) => {
  if (isLoading) {
    return (
      <div className="h-full w-full p-4 flex flex-col gap-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="flex-1" />
      </div>
    );
  }

  const hasData =
    Array.isArray(data) &&
    data.length > 0 &&
    data.some((d) => typeof d.value === "number" && d.value > 0);

  if (!hasData) {
    return (
      <div className="h-full w-full p-4 flex flex-col justify-center items-center text-sm text-muted-foreground">
        {title && (
          <h3 className="text-sm font-medium text-foreground mb-2">{title}</h3>
        )}
        <p>No data available for this widget.</p>
      </div>
    );
  }

  // Extract unique labels if not provided
  const uniqueXLabels = xLabels || [...new Set(data.map((d) => d.xLabel))];
  const uniqueYLabels = yLabels || [...new Set(data.map((d) => d.yLabel))];

  // Find max value for color scaling
  const maxValue = Math.max(...data.map((d) => d.value), 1);

  // Create a lookup map for quick access
  const valueMap = new Map<string, number>();
  data.forEach((d) => {
    valueMap.set(`${d.xLabel}-${d.yLabel}`, d.value);
  });

  const getOpacity = (value: number) => {
    return Math.max(0.15, value / maxValue);
  };

  return (
    <div className="h-full w-full p-4 flex flex-col">
      {title && (
        <h3 className="text-sm font-medium text-foreground mb-3">{title}</h3>
      )}
      <div className="flex-1 min-h-0 flex flex-col">
        {/* Header row */}
        <div className="flex">
          <div className="w-20 flex-shrink-0" /> {/* Empty corner cell */}
          {uniqueXLabels.map((xLabel) => (
            <div
              key={xLabel}
              className="flex-1 text-center text-xs font-medium text-muted-foreground pb-2 truncate px-1"
            >
              {xLabel}
            </div>
          ))}
        </div>

        {/* Grid rows */}
        <div className="flex-1 flex flex-col gap-1">
          {uniqueYLabels.map((yLabel) => (
            <div key={yLabel} className="flex flex-1 gap-1">
              <div className="w-20 flex-shrink-0 text-xs font-medium text-muted-foreground flex items-center truncate">
                {yLabel}
              </div>
              {uniqueXLabels.map((xLabel) => {
                const value = valueMap.get(`${xLabel}-${yLabel}`) || 0;
                return (
                  <div
                    key={`${xLabel}-${yLabel}`}
                    className={cn(
                      "flex-1 rounded-md flex items-center justify-center text-sm font-semibold transition-all hover:ring-2 hover:ring-primary/50",
                      value > 0 ? "text-primary-foreground" : "text-muted-foreground",
                      onCellClick && value > 0 && "cursor-pointer"
                    )}
                    style={{
                      backgroundColor:
                        value > 0
                          ? `hsla(var(--primary), ${getOpacity(value)})`
                          : "hsl(var(--muted))",
                    }}
                    title={`${yLabel} / ${xLabel}: ${value}`}
                    onClick={() => {
                      if (onCellClick && value > 0) {
                        onCellClick({
                          xLabel,
                          yLabel,
                          filters: {
                            criticality: xLabel,
                            risk: yLabel,
                          },
                        });
                      }
                    }}
                  >
                    {value}
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        {/* Legend */}
        <div className="flex items-center justify-center gap-2 mt-3 text-xs text-muted-foreground">
          <span>Low</span>
          <div className="flex gap-0.5">
            {[0.2, 0.4, 0.6, 0.8, 1].map((opacity) => (
              <div
                key={opacity}
                className="w-4 h-3 rounded-sm"
                style={{ backgroundColor: `hsla(var(--primary), ${opacity})` }}
              />
            ))}
          </div>
          <span>High</span>
        </div>
      </div>
    </div>
  );
};

export default HeatmapWidget;

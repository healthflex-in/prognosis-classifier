import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from "recharts";
import { Skeleton } from "@/components/ui/skeleton";

interface ScatterWidgetProps {
  data: Array<{
    x: number;
    y: number;
    name?: string;
    category?: string;
  }>;
  isLoading?: boolean;
  xAxisLabel?: string;
  yAxisLabel?: string;
  thresholdX?: number;
  thresholdY?: number;
  categoryColorMap?: Record<string, string>;
  title?: string;
}

const defaultColorMap: Record<string, string> = {
  High: "hsl(var(--destructive))",
  Medium: "hsl(var(--chart-4))",
  Low: "hsl(var(--chart-3))",
};

const ScatterWidget = ({
  data,
  isLoading = false,
  xAxisLabel = "X",
  yAxisLabel = "Y",
  thresholdX,
  thresholdY,
  categoryColorMap = defaultColorMap,
  title,
}: ScatterWidgetProps) => {
  if (isLoading) {
    return (
      <div className="h-full w-full p-4 flex flex-col gap-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="flex-1" />
      </div>
    );
  }

  return (
    <div className="h-full w-full p-4 flex flex-col">
      {title && (
        <h3 className="text-sm font-medium text-foreground mb-2">{title}</h3>
      )}
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 10, right: 10, left: 0, bottom: 20 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis
              type="number"
              dataKey="x"
              name={xAxisLabel}
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              tickLine={false}
              label={{
                value: xAxisLabel,
                position: "bottom",
                offset: 0,
                style: { fontSize: 11, fill: "hsl(var(--muted-foreground))" },
              }}
            />
            <YAxis
              type="number"
              dataKey="y"
              name={yAxisLabel}
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              tickLine={false}
              label={{
                value: yAxisLabel,
                angle: -90,
                position: "insideLeft",
                style: { fontSize: 11, fill: "hsl(var(--muted-foreground))" },
              }}
            />
            {thresholdX !== undefined && (
              <ReferenceLine
                x={thresholdX}
                stroke="hsl(var(--destructive))"
                strokeDasharray="5 5"
                label={{
                  value: "Threshold",
                  position: "top",
                  style: { fontSize: 10, fill: "hsl(var(--destructive))" },
                }}
              />
            )}
            {thresholdY !== undefined && (
              <ReferenceLine
                y={thresholdY}
                stroke="hsl(var(--destructive))"
                strokeDasharray="5 5"
              />
            )}
            <Tooltip
              cursor={{ strokeDasharray: "3 3" }}
              contentStyle={{
                backgroundColor: "hsl(var(--popover))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "6px",
                fontSize: "12px",
              }}
              formatter={(value, name) => [value, name]}
            />
            <Scatter data={data} fill="hsl(var(--primary))">
              {data.map((entry, index) => (
                <Cell
                  key={index}
                  fill={
                    entry.category
                      ? categoryColorMap[entry.category] || "hsl(var(--primary))"
                      : "hsl(var(--primary))"
                  }
                />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default ScatterWidget;

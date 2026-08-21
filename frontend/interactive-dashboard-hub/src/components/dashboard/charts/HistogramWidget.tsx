import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Skeleton } from "@/components/ui/skeleton";

interface HistogramWidgetProps {
  data: Array<{
    range: string;
    count: number;
    min?: number;
    max?: number;
  }>;
  isLoading?: boolean;
  xAxisLabel?: string;
  yAxisLabel?: string;
  title?: string;
  onBarClick?: (data: { range: string; filters?: Record<string, string> }) => void;
}

const HistogramWidget = ({
  data,
  isLoading = false,
  xAxisLabel = "Range",
  yAxisLabel = "Count",
  title,
  onBarClick,
}: HistogramWidgetProps) => {
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
    data.some((d) => typeof d.count === "number" && d.count > 0);

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

  return (
    <div className="h-full w-full p-4 flex flex-col">
      {title && (
        <h3 className="text-sm font-medium text-foreground mb-2">{title}</h3>
      )}
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            margin={{ top: 10, right: 10, left: -10, bottom: 20 }}
          >
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis
              dataKey="range"
              tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
              tickLine={false}
              axisLine={false}
              label={{
                value: xAxisLabel,
                position: "bottom",
                offset: 0,
                style: { fontSize: 11, fill: "hsl(var(--muted-foreground))" },
              }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              tickLine={false}
              axisLine={false}
              allowDecimals={false}
              label={{
                value: yAxisLabel,
                angle: -90,
                position: "insideLeft",
                style: { fontSize: 11, fill: "hsl(var(--muted-foreground))" },
              }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--popover))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "6px",
                fontSize: "12px",
              }}
              formatter={(value: number) => [value, "Patients"]}
            />
            <Bar
              dataKey="count"
              fill="hsl(var(--primary))"
              radius={[4, 4, 0, 0]}
              onClick={(data: any) => {
                if (onBarClick && data && data.activePayload && data.activePayload[0]) {
                  const activeData = data.activePayload[0].payload;
                  onBarClick({
                    range: activeData.range,
                    filters: {
                      // For histogram, we can't filter by asymmetry range directly in the API
                      // But we can show all patients and they can sort by asymmetry
                    },
                  });
                }
              }}
              style={{ cursor: onBarClick ? "pointer" : "default" }}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default HistogramWidget;

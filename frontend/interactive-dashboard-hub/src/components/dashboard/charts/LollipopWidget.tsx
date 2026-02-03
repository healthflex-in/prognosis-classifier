import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from "recharts";
import { Skeleton } from "@/components/ui/skeleton";

interface LollipopWidgetProps {
  data: Array<{
    name: string;
    value: number;
    category?: string;
  }>;
  isLoading?: boolean;
  threshold?: number;
  thresholdLabel?: string;
  categoryColorMap?: Record<string, string>;
  title?: string;
  onBarClick?: (data: { name: string; filters?: Record<string, string> }) => void;
}

const defaultColorMap: Record<string, string> = {
  High: "hsl(var(--destructive))",
  Medium: "hsl(var(--chart-4))",
  Low: "hsl(var(--chart-3))",
};

const LollipopWidget = ({
  data,
  isLoading = false,
  threshold,
  thresholdLabel = "Threshold",
  categoryColorMap = defaultColorMap,
  title,
  onBarClick,
}: LollipopWidgetProps) => {
  if (isLoading) {
    return (
      <div className="h-full w-full p-4 flex flex-col gap-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="flex-1" />
      </div>
    );
  }

  // Sort data descending by value
  const sortedData = [...data].sort((a, b) => b.value - a.value);

  return (
    <div className="h-full w-full p-4 flex flex-col">
      {title && (
        <h3 className="text-sm font-medium text-foreground mb-2">{title}</h3>
      )}
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={sortedData}
            layout="vertical"
            margin={{ top: 10, right: 30, left: 60, bottom: 10 }}
          >
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" horizontal={false} />
            <XAxis
              type="number"
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              tickLine={false}
              axisLine={false}
              domain={[0, "auto"]}
            />
            <YAxis
              type="category"
              dataKey="name"
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              tickLine={false}
              axisLine={false}
              width={55}
            />
            {threshold !== undefined && (
              <ReferenceLine
                x={threshold}
                stroke="hsl(var(--destructive))"
                strokeDasharray="5 5"
                label={{
                  value: thresholdLabel,
                  position: "top",
                  style: { fontSize: 10, fill: "hsl(var(--destructive))" },
                }}
              />
            )}
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--popover))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "6px",
                fontSize: "12px",
              }}
              formatter={(value: number) => [`${value.toFixed(1)}%`, "Asymmetry"]}
            />
            <Bar 
              dataKey="value" 
              radius={[0, 4, 4, 0]} 
              barSize={12}
              onClick={(data: any) => {
                if (onBarClick && data && data.activePayload && data.activePayload[0]) {
                  const activeData = data.activePayload[0].payload;
                  onBarClick({
                    name: activeData.name,
                    filters: {
                      // For asymmetry lollipop, we can't filter by asymmetry value directly
                      // But we can show all patients and let them sort by asymmetry
                    },
                  });
                }
              }}
              style={{ cursor: onBarClick ? "pointer" : "default" }}
            >
              {sortedData.map((entry, index) => (
                <Cell
                  key={index}
                  fill={
                    entry.category
                      ? categoryColorMap[entry.category] || "hsl(var(--primary))"
                      : entry.value > (threshold || 15)
                      ? "hsl(var(--destructive))"
                      : "hsl(var(--primary))"
                  }
                  onClick={() => {
                    if (onBarClick) {
                      onBarClick({
                        name: entry.name,
                        filters: {},
                      });
                    }
                  }}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default LollipopWidget;

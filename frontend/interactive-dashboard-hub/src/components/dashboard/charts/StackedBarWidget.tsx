import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Cell,
} from "recharts";
import { Skeleton } from "@/components/ui/skeleton";

interface StackedBarWidgetProps {
  data: Array<Record<string, unknown>>;
  isLoading?: boolean;
  xAxisKey?: string;
  stackKeys: string[];
  colors?: string[];
  title?: string;
  onBarClick?: (data: { name: string; stackKey?: string; filters?: Record<string, string> }) => void;
}

const defaultColors = [
  "hsl(var(--chart-1))",
  "hsl(var(--chart-2))",
  "hsl(var(--chart-3))",
  "hsl(var(--chart-4))",
  "hsl(var(--chart-5))",
];

const StackedBarWidget = ({
  data,
  isLoading = false,
  xAxisKey = "name",
  stackKeys,
  colors = defaultColors,
  title,
  onBarClick,
}: StackedBarWidgetProps) => {
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
          <BarChart data={data} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis
              dataKey={xAxisKey}
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--popover))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "6px",
                fontSize: "12px",
              }}
            />
            <Legend wrapperStyle={{ fontSize: "11px" }} />
            {stackKeys.map((key, index) => (
              <Bar
                key={key}
                dataKey={key}
                stackId="stack"
                fill={colors[index % colors.length]}
                radius={index === stackKeys.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                onClick={(data: any) => {
                  if (onBarClick && data && data.activePayload && data.activePayload[0]) {
                    const activeData = data.activePayload[0].payload;
                    onBarClick({
                      name: activeData[xAxisKey],
                      stackKey: key,
                      filters: {
                        [xAxisKey === "name" ? "timeline" : xAxisKey.toLowerCase()]: activeData[xAxisKey],
                        criticality: key,
                      },
                    });
                  }
                }}
                style={{ cursor: onBarClick ? "pointer" : "default" }}
              >
                {data.map((entry: any, cellIndex: number) => (
                  <Cell
                    key={`cell-${cellIndex}`}
                    onClick={() => {
                      if (onBarClick) {
                        onBarClick({
                          name: entry[xAxisKey],
                          stackKey: key,
                          filters: {
                            [xAxisKey === "name" ? "timeline" : xAxisKey.toLowerCase()]: entry[xAxisKey],
                            criticality: key,
                          },
                        });
                      }
                    }}
                  />
                ))}
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default StackedBarWidget;

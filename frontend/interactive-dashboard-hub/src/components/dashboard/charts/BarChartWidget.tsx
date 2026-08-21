import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Skeleton } from "@/components/ui/skeleton";

interface BarChartWidgetProps {
  data: Array<{ name: string; value: number; category?: string }>;
  isLoading?: boolean;
  xAxisKey?: string;
  yAxisKey?: string;
  colors?: string[];
  title?: string;
  onBarClick?: (data: { name: string; filters?: Record<string, string> }) => void;
}

const defaultColors = [
  "hsl(var(--primary))",
  "hsl(var(--chart-2))",
  "hsl(var(--chart-3))",
  "hsl(var(--chart-4))",
  "hsl(var(--chart-5))",
];

const BarChartWidget = ({
  data,
  isLoading = false,
  xAxisKey = "name",
  yAxisKey = "value",
  colors = defaultColors,
  title,
  onBarClick,
}: BarChartWidgetProps) => {
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
    data.some((d) => {
      const value = (d as any)[yAxisKey];
      return typeof value === "number" && value > 0;
    });

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
            <Bar 
              dataKey={yAxisKey} 
              radius={[4, 4, 0, 0]}
              onClick={(data: any) => {
                if (onBarClick && data && data.activePayload && data.activePayload[0]) {
                  const activeData = data.activePayload[0].payload;
                  // Determine filter type based on widget title
                  const isTestingModality = title?.toLowerCase().includes("testing");
                  const isRisk = title?.toLowerCase().includes("risk");
                  const isCriticality = title?.toLowerCase().includes("criticality");
                  
                  const filters: Record<string, string> = {};
                  
                  if (isTestingModality) {
                    filters.testing_focus = activeData[xAxisKey];
                  } else if (isRisk) {
                    // Normalize risk value (remove " Risk" suffix if present)
                    const riskValue = activeData[xAxisKey].replace(' Risk', '').trim();
                    filters.risk = riskValue;
                  } else if (isCriticality) {
                    filters.criticality = activeData[xAxisKey];
                  } else {
                    // Default to criticality if unclear
                    filters.criticality = activeData[xAxisKey];
                  }
                  
                  onBarClick({
                    name: activeData[xAxisKey],
                    filters,
                  });
                }
              }}
              style={{ cursor: onBarClick ? "pointer" : "default" }}
            >
              {data.map((entry, index) => (
                <Cell 
                  key={index} 
                  fill={colors[index % colors.length]}
                  onClick={() => {
                    if (onBarClick) {
                      // Determine filter type based on widget title
                      const isTestingModality = title?.toLowerCase().includes("testing");
                      const isRisk = title?.toLowerCase().includes("risk");
                      const isCriticality = title?.toLowerCase().includes("criticality");
                      
                      const filters: Record<string, string> = {};
                      
                      if (isTestingModality) {
                        filters.testing_focus = entry[xAxisKey];
                      } else if (isRisk) {
                        // Normalize risk value (remove " Risk" suffix if present)
                        const riskValue = String(entry[xAxisKey]).replace(' Risk', '').trim();
                        filters.risk = riskValue;
                      } else if (isCriticality) {
                        filters.criticality = entry[xAxisKey];
                      } else {
                        // Default to criticality if unclear
                        filters.criticality = entry[xAxisKey];
                      }
                      
                      onBarClick({
                        name: entry[xAxisKey],
                        filters,
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

export default BarChartWidget;

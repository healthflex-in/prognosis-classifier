import { TrendingUp, TrendingDown } from "lucide-react";
import { StatsData } from "@/types/dashboard";

interface StatsWidgetProps {
  data: StatsData[];
}

const StatsWidget = ({ data }: StatsWidgetProps) => {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 h-full p-4">
      {data.map((stat, index) => (
        <div
          key={index}
          className={`p-4 rounded-lg ${
            index === 0 ? "bg-primary text-primary-foreground" : "bg-muted"
          }`}
        >
          <p className={`text-xs font-medium mb-1 ${
            index === 0 ? "text-primary-foreground/70" : "text-muted-foreground"
          }`}>
            {stat.label}
          </p>
          <p className="text-2xl font-bold mb-2">{stat.value}</p>
          <div className="flex items-center gap-1">
            {stat.trend >= 0 ? (
              <TrendingUp className={`h-3 w-3 ${
                index === 0 ? "text-success-foreground" : "text-success"
              }`} />
            ) : (
              <TrendingDown className={`h-3 w-3 ${
                index === 0 ? "text-destructive-foreground" : "text-destructive"
              }`} />
            )}
            <span className={`text-xs ${
              stat.trend >= 0 
                ? (index === 0 ? "text-success-foreground" : "text-success") 
                : (index === 0 ? "text-destructive-foreground" : "text-destructive")
            }`}>
              {stat.trend >= 0 ? "↑" : "↓"} {Math.abs(stat.trend)}%
            </span>
            <span className={`text-xs ${
              index === 0 ? "text-primary-foreground/60" : "text-muted-foreground"
            }`}>
              {stat.trendLabel}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
};

export default StatsWidget;

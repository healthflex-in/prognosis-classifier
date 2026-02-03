import { TrendingUp, RefreshCw, ArrowUpRight } from "lucide-react";
import { ProgressData } from "@/types/dashboard";

interface ProgressWidgetProps {
  data: ProgressData;
}

const ProgressWidget = ({ data }: ProgressWidgetProps) => {
  const circumference = 2 * Math.PI * 45;
  const strokeDashoffset = circumference - (data.value / 100) * circumference;

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex gap-1">
          <button className="p-1.5 rounded-lg hover:bg-muted transition-colors">
            <RefreshCw className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
          <button className="p-1.5 rounded-lg hover:bg-muted transition-colors">
            <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
        </div>
      </div>
      
      <div className="flex-1 flex flex-col items-center justify-center">
        <div className="relative">
          <svg className="w-24 h-24 transform -rotate-90">
            <circle
              cx="48"
              cy="48"
              r="45"
              stroke="hsl(var(--muted))"
              strokeWidth="6"
              fill="none"
            />
            <circle
              cx="48"
              cy="48"
              r="45"
              stroke="hsl(var(--primary))"
              strokeWidth="6"
              fill="none"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              className="transition-all duration-500"
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-xl font-bold text-foreground">{data.value}%</span>
          </div>
        </div>
        
        <div className="mt-3 text-center">
          <p className="text-sm font-medium text-foreground">{data.label}</p>
          <div className="flex items-center justify-center gap-1 mt-1">
            <TrendingUp className="h-3 w-3 text-success" />
            <span className="text-xs text-success">↑ {data.trend}%</span>
            <span className="text-xs text-muted-foreground">{data.trendLabel}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProgressWidget;

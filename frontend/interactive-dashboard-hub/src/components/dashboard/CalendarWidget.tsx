import { ChevronLeft, ChevronRight } from "lucide-react";
import { CalendarDay } from "@/types/dashboard";

interface CalendarWidgetProps {
  data: CalendarDay[];
  month?: string;
}

const CalendarWidget = ({ data, month = "September 2024" }: CalendarWidgetProps) => {
  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-4">
        <button className="p-1 rounded hover:bg-muted transition-colors">
          <ChevronLeft className="h-4 w-4 text-muted-foreground" />
        </button>
        <h3 className="font-semibold text-foreground text-sm">{month}</h3>
        <button className="p-1 rounded hover:bg-muted transition-colors">
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        </button>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <div className="flex gap-2">
          {data.map((day, index) => (
            <div
              key={index}
              className={`flex flex-col items-center p-2 rounded-lg min-w-[44px] ${
                day.isToday
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted transition-colors"
              }`}
            >
              <span className={`text-xs font-medium ${
                day.isToday ? "text-primary-foreground/70" : "text-muted-foreground"
              }`}>
                {day.day}
              </span>
              <span className={`text-lg font-bold ${
                day.isToday ? "text-primary-foreground" : "text-foreground"
              }`}>
                {day.date}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default CalendarWidget;

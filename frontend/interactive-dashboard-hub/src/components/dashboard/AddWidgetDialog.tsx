import {
  Plus,
  BarChart3,
  ScatterChart,
  Grid3X3,
  Activity,
  Users,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { WidgetType, WidgetTypeEnum } from "@/types/dashboard";

interface AddWidgetDialogProps {
  onAddWidget: (widget: WidgetType) => void;
  existingWidgets: string[];
}

interface WidgetOption {
  id: string;
  type: WidgetTypeEnum;
  title: string;
  minW: number;
  minH: number;
  icon: React.ComponentType<{ className?: string }>;
  category: "general" | "clinical";
}

const widgetOptions: WidgetOption[] = [
  // Clinical widgets only - removed general widgets (stats, chart, calendar, progress, table)
  { id: "bar", type: "bar", title: "Bar Chart", minW: 2, minH: 3, icon: BarChart3, category: "clinical" },
  { id: "stacked-bar", type: "stacked-bar", title: "Stacked Bar", minW: 2, minH: 3, icon: BarChart3, category: "clinical" },
  { id: "grouped-bar", type: "grouped-bar", title: "Grouped Bar", minW: 3, minH: 3, icon: BarChart3, category: "clinical" },
  { id: "scatter", type: "scatter", title: "Scatter Plot", minW: 3, minH: 3, icon: ScatterChart, category: "clinical" },
  { id: "lollipop", type: "lollipop", title: "Lollipop Chart", minW: 3, minH: 4, icon: Activity, category: "clinical" },
  { id: "histogram", type: "histogram", title: "Histogram", minW: 2, minH: 3, icon: BarChart3, category: "clinical" },
  { id: "heatmap", type: "heatmap", title: "Heatmap", minW: 2, minH: 3, icon: Grid3X3, category: "clinical" },
  { id: "patient-table", type: "patient-table", title: "Patient Table", minW: 6, minH: 4, icon: Users, category: "clinical" },
];

const AddWidgetDialog = ({ onAddWidget, existingWidgets }: AddWidgetDialogProps) => {
  const handleAddWidget = (option: WidgetOption) => {
    const uniqueId = `${option.type}-${Date.now()}`;
    onAddWidget({
      id: uniqueId,
      type: option.type,
      title: option.title,
      minW: option.minW,
      minH: option.minH,
    });
  };

  const clinicalWidgets = widgetOptions.filter((w) => w.category === "clinical");

  const renderWidgetGrid = (widgets: WidgetOption[]) => (
    <div className="grid grid-cols-2 gap-3">
      {widgets.map((option) => {
        const Icon = option.icon;
        return (
          <button
            key={option.id}
            onClick={() => handleAddWidget(option)}
            className="flex flex-col items-center gap-2 p-4 rounded-lg border border-border hover:border-primary hover:bg-accent transition-all"
          >
            <div className="p-3 rounded-lg bg-muted">
              <Icon className="h-5 w-5 text-foreground" />
            </div>
            <span className="text-sm font-medium text-foreground">{option.title}</span>
          </button>
        );
      })}
    </div>
  );

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <Plus className="h-4 w-4" />
          Add Widget
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Clinical Widget</DialogTitle>
        </DialogHeader>
        <div className="pt-4">
          {renderWidgetGrid(clinicalWidgets)}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default AddWidgetDialog;

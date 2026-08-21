import { X, GripVertical } from "lucide-react";
import { ReactNode } from "react";
import WidgetConfigDialog from "./WidgetConfigDialog";
import { QueryConfig } from "@/types/dashboard";

interface WidgetWrapperProps {
  children: ReactNode;
  onRemove: () => void;
  onConfigChange?: (config: QueryConfig) => void;
  queryConfig?: QueryConfig;
  widgetType?: string;
  title?: string;
}

const WidgetWrapper = ({
  children,
  onRemove,
  onConfigChange,
  queryConfig,
  widgetType,
  title,
}: WidgetWrapperProps) => {
  return (
    <div className="widget-card h-full flex flex-col group">
      <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity z-10 flex gap-1">
        {onConfigChange && widgetType && (
          <WidgetConfigDialog
            queryConfig={queryConfig}
            onSave={onConfigChange}
            widgetType={widgetType}
          />
        )}
        <button
          onClick={onRemove}
          className="p-1.5 rounded-md bg-card hover:bg-destructive hover:text-destructive-foreground transition-colors border border-border shadow-sm"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="absolute top-2 left-2 opacity-0 group-hover:opacity-100 transition-opacity z-10 cursor-grab active:cursor-grabbing drag-handle">
        <div className="p-1.5 rounded-md bg-card border border-border shadow-sm">
          <GripVertical className="h-3.5 w-3.5 text-muted-foreground" />
        </div>
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  );
};

export default WidgetWrapper;

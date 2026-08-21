import { useState } from "react";
import { Settings2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { QueryConfig, endpointOptions, filterOptions } from "@/types/dashboard";
import { ClinicalFilters } from "@/types/clinical";

interface WidgetConfigDialogProps {
  queryConfig?: QueryConfig;
  onSave: (config: QueryConfig) => void;
  widgetType: string;
}

const refreshIntervalOptions = [
  { value: "0", label: "None" },
  { value: "30", label: "30 seconds" },
  { value: "60", label: "1 minute" },
  { value: "300", label: "5 minutes" },
];

const WidgetConfigDialog = ({
  queryConfig,
  onSave,
  widgetType,
}: WidgetConfigDialogProps) => {
  const [open, setOpen] = useState(false);
  const [endpoint, setEndpoint] = useState(queryConfig?.endpoint || "");
  const [refreshInterval, setRefreshInterval] = useState(
    queryConfig?.refreshInterval?.toString() || "0"
  );
  const [filters, setFilters] = useState<ClinicalFilters>(queryConfig?.filters || {});

  // Filter endpoint options based on widget type
  const compatibleEndpoints = endpointOptions.filter((opt) =>
    opt.widgetTypes.includes(widgetType as never)
  );

  const handleSave = () => {
    const config: QueryConfig = {
      endpoint,
      refreshInterval: parseInt(refreshInterval) || undefined,
      filters: Object.keys(filters).length > 0 ? filters : undefined,
    };
    onSave(config);
    setOpen(false);
  };

  const handleFilterChange = (field: keyof ClinicalFilters, value: string) => {
    if (value === "all") {
      const newFilters = { ...filters };
      delete newFilters[field];
      setFilters(newFilters);
    } else {
      setFilters({ ...filters, [field]: value as never });
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          className="p-1.5 rounded-md bg-card hover:bg-accent transition-colors border border-border shadow-sm"
          title="Configure Widget"
        >
          <Settings2 className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Configure Widget</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Endpoint Selection */}
          <div className="space-y-2">
            <Label>Data Source</Label>
            {compatibleEndpoints.length > 0 ? (
              <Select value={endpoint} onValueChange={setEndpoint}>
                <SelectTrigger>
                  <SelectValue placeholder="Select data source" />
                </SelectTrigger>
                <SelectContent>
                  {compatibleEndpoints.map((opt) => (
                    <SelectItem key={opt.key} value={opt.endpoint}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input
                value={endpoint}
                onChange={(e) => setEndpoint(e.target.value)}
                placeholder="/api/your-endpoint"
              />
            )}
            <p className="text-xs text-muted-foreground">
              Endpoint: {endpoint || "Not configured"}
            </p>
          </div>

          {/* Filters */}
          <div className="space-y-3">
            <Label>Filters</Label>
            <div className="grid gap-2">
              {filterOptions.map((filter) => (
                <div key={filter.field} className="flex items-center gap-2">
                  <Label className="w-24 text-xs text-muted-foreground">
                    {filter.label}
                  </Label>
                  <Select
                    value={filters[filter.field] || "all"}
                    onValueChange={(value) => handleFilterChange(filter.field, value)}
                  >
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All</SelectItem>
                      {filter.options.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </div>
          </div>

          {/* Refresh Interval */}
          <div className="space-y-2">
            <Label>Refresh Interval</Label>
            <RadioGroup
              value={refreshInterval}
              onValueChange={setRefreshInterval}
              className="flex flex-wrap gap-3"
            >
              {refreshIntervalOptions.map((opt) => (
                <div key={opt.value} className="flex items-center space-x-2">
                  <RadioGroupItem value={opt.value} id={`interval-${opt.value}`} />
                  <Label
                    htmlFor={`interval-${opt.value}`}
                    className="text-sm font-normal cursor-pointer"
                  >
                    {opt.label}
                  </Label>
                </div>
              ))}
            </RadioGroup>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave}>Save Configuration</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default WidgetConfigDialog;

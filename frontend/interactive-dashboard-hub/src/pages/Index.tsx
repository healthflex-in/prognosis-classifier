import { useState, useRef, useEffect } from "react";
import { mockDashboardData, clinicalWidgets, clinicalDefaultLayout } from "@/data/mockData";
import { DashboardFilters, WidgetType, WidgetLayout, QueryConfig, endpointOptions } from "@/types/dashboard";
import DashboardHeader from "@/components/dashboard/DashboardHeader";
import DashboardGrid from "@/components/dashboard/DashboardGrid";
import { ProgressBar } from "@/components/dashboard/ProgressBar";
import { ChartSidebar } from "@/components/dashboard/ChartSidebar";
import { useQueryClient } from "@tanstack/react-query";

const STORAGE_KEY_LAYOUTS = "dashboard_layouts";
const STORAGE_KEY_WIDGETS = "dashboard_widgets";

const Index = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(1200);
  
  const [filters, setFilters] = useState<DashboardFilters>({
    period: "Month",
    dateRange: {
      start: "1 Sep 2024",
      end: "31 Sep 2024",
    },
  });

  // Load layouts and widgets from localStorage on mount (lazy initialization)
  const loadFromStorage = (): { layouts: WidgetLayout[]; widgets: WidgetType[] } => {
    try {
      const savedLayouts = localStorage.getItem(STORAGE_KEY_LAYOUTS);
      const savedWidgets = localStorage.getItem(STORAGE_KEY_WIDGETS);
      
      if (savedLayouts && savedWidgets) {
        const parsedLayouts = JSON.parse(savedLayouts) as WidgetLayout[];
        const parsedWidgets = JSON.parse(savedWidgets) as WidgetType[];
        
        // If there are any legacy widget types, reset to clinical defaults
        const hasLegacyWidgets = parsedWidgets.some(
          (w) =>
            w.type === "stats" ||
            w.type === "chart" ||
            w.type === "calendar" ||
            w.type === "progress" ||
            w.type === "table"
        );

        if (hasLegacyWidgets) {
          return { layouts: clinicalDefaultLayout, widgets: clinicalWidgets };
        }
        
        // Validate that saved data matches current widget IDs
        const savedWidgetIds = new Set(parsedWidgets.map(w => w.id));
        const defaultWidgetIds = new Set(clinicalWidgets.map(w => w.id));
        
        // If saved widgets match default widgets, use saved data
        if (savedWidgetIds.size === defaultWidgetIds.size && 
            [...savedWidgetIds].every(id => defaultWidgetIds.has(id))) {
          return { layouts: parsedLayouts, widgets: parsedWidgets };
        }
      }
    } catch (error) {
      console.error("Error loading dashboard state from localStorage:", error);
    }
    
    // Fall back to defaults
    return { layouts: clinicalDefaultLayout, widgets: clinicalWidgets };
  };
  
  // Use lazy initialization to load from localStorage only once on mount
  const [widgets, setWidgets] = useState<WidgetType[]>(() => loadFromStorage().widgets);
  const [layouts, setLayouts] = useState<WidgetLayout[]>(() => loadFromStorage().layouts);

  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.offsetWidth);
      }
    };

    updateWidth();
    window.addEventListener("resize", updateWidth);
    return () => window.removeEventListener("resize", updateWidth);
  }, []);

  // Save layouts to localStorage whenever they change
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY_LAYOUTS, JSON.stringify(layouts));
    } catch (error) {
      console.error("Error saving layouts to localStorage:", error);
    }
  }, [layouts]);

  // Save widgets to localStorage whenever they change
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY_WIDGETS, JSON.stringify(widgets));
    } catch (error) {
      console.error("Error saving widgets to localStorage:", error);
    }
  }, [widgets]);

  const handleLayoutChange = (newLayout: WidgetLayout[]) => {
    setLayouts(newLayout);
  };

  const handleAddWidget = (widget: WidgetType) => {
    setWidgets((prev) => {
      const updated = [...prev, widget];
      // Save immediately
      try {
        localStorage.setItem(STORAGE_KEY_WIDGETS, JSON.stringify(updated));
      } catch (error) {
        console.error("Error saving widgets to localStorage:", error);
      }
      return updated;
    });
    
    // Find position for new widget
    const maxY = layouts.reduce((max, l) => Math.max(max, l.y + l.h), 0);
    const newLayoutItem: WidgetLayout = {
      i: widget.id,
      x: 0,
      y: maxY,
      w: widget.minW || 2,
      h: widget.minH || 2,
      minW: widget.minW,
      minH: widget.minH,
    };
    setLayouts((prev) => {
      const updated = [...prev, newLayoutItem];
      // Save immediately
      try {
        localStorage.setItem(STORAGE_KEY_LAYOUTS, JSON.stringify(updated));
      } catch (error) {
        console.error("Error saving layouts to localStorage:", error);
      }
      return updated;
    });
  };

  const handleRemoveWidget = (widgetId: string) => {
    setWidgets((prev) => {
      const updated = prev.filter((w) => w.id !== widgetId);
      // Save immediately
      try {
        localStorage.setItem(STORAGE_KEY_WIDGETS, JSON.stringify(updated));
      } catch (error) {
        console.error("Error saving widgets to localStorage:", error);
      }
      return updated;
    });
    setLayouts((prev) => {
      const updated = prev.filter((l) => l.i !== widgetId);
      // Save immediately
      try {
        localStorage.setItem(STORAGE_KEY_LAYOUTS, JSON.stringify(updated));
      } catch (error) {
        console.error("Error saving layouts to localStorage:", error);
      }
      return updated;
    });
  };

  const handleConfigChange = (widgetId: string, config: QueryConfig) => {
    setWidgets((prev) =>
      prev.map((w) => {
        if (w.id !== widgetId) return w;

        // If endpoint matches a known option, update the widget title to that label
        const matchedEndpoint = endpointOptions.find(
          (opt) => opt.endpoint === config.endpoint
        );

        return {
          ...w,
          title: matchedEndpoint ? matchedEndpoint.label : w.title,
          queryConfig: config,
        };
      })
    );
  };

  const queryClient = useQueryClient();
  const [progress, setProgress] = useState<{ current: number; total: number; status: string; error?: string | null; message?: string | null } | null>(null);
  
  // Sidebar state
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarTitle, setSidebarTitle] = useState("");
  const [sidebarFilters, setSidebarFilters] = useState<{
    criticality?: string;
    timeline?: string;
    risk?: string;
    joint_group?: string;
    testing_focus?: string;
  }>({});

  const handleRefresh = () => {
    // Invalidate all queries to force refetch
    queryClient.invalidateQueries();
  };

  const handleProgressChange = (progressData: { current: number; total: number; status: string; error?: string | null; message?: string | null }) => {
    setProgress(progressData);
    // Clear progress when completed or error
    if (progressData.status === "completed" || progressData.status === "error") {
      setTimeout(() => setProgress(null), 3000);
    }
  };

  const handleChartClick = (data: { title: string; filters: Record<string, string> }) => {
    // Map filter keys to sidebar filter format (matching API parameter names)
    const mappedFilters: typeof sidebarFilters = {};
    
    if (data.filters.criticality) {
      mappedFilters.criticality = data.filters.criticality;
    }
    // Map "timeline" to "timeline" (API expects "timeline" not "timelineStatus" in query params)
    if (data.filters.timeline) {
      mappedFilters.timeline = data.filters.timeline;
    }
    if (data.filters.risk) {
      mappedFilters.risk = data.filters.risk;
    }
    if (data.filters.joint_group) {
      mappedFilters.joint_group = data.filters.joint_group;
    }
    if (data.filters.testing_focus) {
      mappedFilters.testing_focus = data.filters.testing_focus;
    }
    
    setSidebarTitle(data.title);
    setSidebarFilters(mappedFilters);
    setSidebarOpen(true);
  };

  return (
    <div className="min-h-screen bg-background">
      {progress && (
        <ProgressBar
          current={progress.current}
          total={progress.total}
          status={progress.status}
          error={progress.error}
          message={progress.message}
        />
      )}
      <DashboardHeader
        filters={filters}
        onFilterChange={setFilters}
        onAddWidget={handleAddWidget}
        existingWidgets={widgets.map((w) => w.id)}
        onRefresh={handleRefresh}
        onProgressChange={handleProgressChange}
      />

      <main className="p-6" ref={containerRef}>
        <DashboardGrid
          data={mockDashboardData}
          layouts={layouts}
          widgets={widgets}
          onLayoutChange={handleLayoutChange}
          onRemoveWidget={handleRemoveWidget}
          onConfigChange={handleConfigChange}
          width={containerWidth}
          onChartClick={handleChartClick}
        />
      </main>
      
      <ChartSidebar
        open={sidebarOpen}
        onOpenChange={setSidebarOpen}
        title={sidebarTitle}
        description={`Patients matching the selected criteria`}
        filters={sidebarFilters}
      />
    </div>
  );
};

export default Index;

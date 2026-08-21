import { useCallback } from "react";
import GridLayout from "react-grid-layout/legacy";
import "react-grid-layout/css/styles.css";

import { DashboardData, WidgetLayout, WidgetType, QueryConfig } from "@/types/dashboard";
import { useWidgetData } from "@/hooks/useWidgetData";
import { useTriageStatus } from "@/hooks/useTriageStatus";
import WidgetWrapper from "./WidgetWrapper";
import PatientTableWidget from "./PatientTableWidget";
import BarChartWidget from "./charts/BarChartWidget";
import StackedBarWidget from "./charts/StackedBarWidget";
import ScatterWidget from "./charts/ScatterWidget";
import LollipopWidget from "./charts/LollipopWidget";
import HistogramWidget from "./charts/HistogramWidget";
import HeatmapWidget from "./charts/HeatmapWidget";

import {
  mockCriticalityData,
  mockTimelineData,
  mockRiskData,
  mockJointGroupData,
  mockTestingFocusData,
  mockAsymmetryData,
  mockAsymmetryForceData,
  mockDistributionData,
  mockRiskCriticalityMatrix,
  mockPatientData,
} from "@/data/mockData";

interface DashboardGridProps {
  data: DashboardData;
  layouts: WidgetLayout[];
  widgets: WidgetType[];
  onLayoutChange: (layout: WidgetLayout[]) => void;
  onRemoveWidget: (widgetId: string) => void;
  onConfigChange: (widgetId: string, config: QueryConfig) => void;
  width: number;
  onChartClick?: (filters: { title: string; filters: Record<string, string> }) => void;
}

const DashboardGrid = ({
  data,
  layouts,
  widgets,
  onLayoutChange,
  onRemoveWidget,
  onConfigChange,
  width,
  onChartClick,
}: DashboardGridProps) => {
  // Render widget component - separate component to use hooks properly
  const WidgetRenderer = ({ widget }: { widget: WidgetType }) => {
    const hasQueryConfig = widget.queryConfig?.endpoint;
    const triageStatus = useTriageStatus();
    const isTriageRunning = triageStatus.data?.status === "running";
    
    // Debug logging for patient table
    if (widget.type === "patient-table") {
      console.log("🔍 Patient Table Widget Debug:", {
        hasQueryConfig,
        endpoint: widget.queryConfig?.endpoint,
        widgetId: widget.id,
        fullQueryConfig: widget.queryConfig,
        apiUrl: import.meta.env.VITE_API_URL || "http://localhost:8013"
      });
    }
    
    switch (widget.type) {
      // Legacy widgets removed - only clinical widgets are supported
      // If legacy widgets exist, show a message to remove them
      case "stats":
      case "chart":
      case "calendar":
      case "progress":
      case "table":
        return (
          <div className="flex items-center justify-center h-full p-4 text-muted-foreground text-sm">
            Legacy widget type "{widget.type}" is no longer supported. Please remove this widget and add a clinical widget instead.
          </div>
        );

      // Clinical widgets with API integration
      case "bar": {
        if (hasQueryConfig) {
          const { data: apiData, isLoading } = useWidgetData<Array<{ name: string; value: number }>>({
            queryConfig: widget.queryConfig!,
            fallbackData: mockCriticalityData,
          });
          return (
            <BarChartWidget
              data={apiData || mockCriticalityData}
              isLoading={isLoading}
              title={widget.title}
              onBarClick={(clickData) => {
                if (onChartClick) {
                  // Determine filter type based on widget title
                  const isTestingModality = widget.title?.toLowerCase().includes("testing");
                  const isRisk = widget.title?.toLowerCase().includes("risk");
                  const filters: Record<string, string> = {};
                  
                  if (isTestingModality && clickData.name) {
                    filters.testing_focus = clickData.name;
                  } else if (isRisk && clickData.name) {
                    // Normalize risk value (remove " Risk" suffix if present)
                    const riskValue = String(clickData.name).replace(' Risk', '').trim();
                    filters.risk = riskValue;
                  } else if (clickData.name) {
                    filters.criticality = clickData.name;
                  }
                  
                  onChartClick({
                    title: `${widget.title}: ${clickData.name}`,
                    filters,
                  });
                }
              }}
            />
          );
        }
        return (
          <BarChartWidget
            data={mockCriticalityData}
            title={widget.title}
            onBarClick={(clickData) => {
              if (onChartClick) {
                const isTestingModality = widget.title?.toLowerCase().includes("testing");
                const isRisk = widget.title?.toLowerCase().includes("risk");
                const filters: Record<string, string> = {};
                
                if (isTestingModality && clickData.name) {
                  filters.testing_focus = clickData.name;
                } else if (isRisk && clickData.name) {
                  // Normalize risk value (remove " Risk" suffix if present)
                  const riskValue = String(clickData.name).replace(' Risk', '').trim();
                  filters.risk = riskValue;
                } else if (clickData.name) {
                  filters.criticality = clickData.name;
                }
                
                onChartClick({
                  title: `${widget.title}: ${clickData.name}`,
                  filters,
                });
              }
            }}
          />
        );
      }

      case "stacked-bar": {
        if (hasQueryConfig) {
          const { data: apiData, isLoading } = useWidgetData<Array<{ name: string; value: number; High?: number; Medium?: number; Low?: number }>>({
            queryConfig: widget.queryConfig!,
            fallbackData: mockTimelineData,
          });
          const stackKeys = apiData && apiData[0] ? 
            Object.keys(apiData[0]).filter(k => k !== 'name' && k !== 'value') : 
            ["High", "Medium", "Low"];
          return (
            <StackedBarWidget
              data={apiData || mockTimelineData}
              stackKeys={stackKeys}
              isLoading={isLoading}
              title={widget.title}
              onBarClick={(clickData) => {
                if (onChartClick) {
                  // Determine filter type based on widget title
                  const isTimeline = widget.title?.toLowerCase().includes("timeline");
                  const filters: Record<string, string> = {};
                  
                  if (isTimeline) {
                    filters.timeline = clickData.name;
                    if (clickData.stackKey) {
                      filters.criticality = clickData.stackKey;
                    }
                  } else {
                    // For other stacked bars, use the name and stackKey
                    if (clickData.name) {
                      filters[widget.title?.toLowerCase().includes("joint") ? "joint_group" : "criticality"] = clickData.name;
                    }
                    if (clickData.stackKey) {
                      filters.criticality = clickData.stackKey;
                    }
                  }
                  
                  onChartClick({
                    title: `${widget.title}: ${clickData.name}${clickData.stackKey ? ` (${clickData.stackKey})` : ''}`,
                    filters,
                  });
                }
              }}
            />
          );
        }
        return (
          <StackedBarWidget
            data={mockTimelineData}
            stackKeys={["High", "Medium", "Low"]}
            title={widget.title}
            onBarClick={(clickData) => {
              if (onChartClick) {
                const isTimeline = widget.title?.toLowerCase().includes("timeline");
                const filters: Record<string, string> = {};
                
                if (isTimeline) {
                  filters.timeline = clickData.name;
                  if (clickData.stackKey) {
                    filters.criticality = clickData.stackKey;
                  }
                }
                
                onChartClick({
                  title: `${widget.title}: ${clickData.name}${clickData.stackKey ? ` (${clickData.stackKey})` : ''}`,
                  filters,
                });
              }
            }}
          />
        );
      }

      case "grouped-bar": {
        if (hasQueryConfig) {
          const { data: apiData, isLoading } = useWidgetData<Array<{ name: string; value: number; ForceFrame?: number; ForceDeck?: number; Standard?: number }>>({
            queryConfig: widget.queryConfig!,
            fallbackData: mockJointGroupData,
          });
          return (
            <StackedBarWidget
              data={apiData || mockJointGroupData}
              stackKeys={["ForceFrame", "ForceDeck", "Standard"]}
              isLoading={isLoading}
              title={widget.title}
              onBarClick={(clickData) => {
                if (onChartClick) {
                  const filters: Record<string, string> = {};
                  if (clickData.name) {
                    filters.joint_group = clickData.name;
                  }
                  if (clickData.stackKey) {
                    filters.testing_focus = clickData.stackKey;
                  }
                  onChartClick({
                    title: `${widget.title}: ${clickData.name}${clickData.stackKey ? ` (${clickData.stackKey})` : ''}`,
                    filters,
                  });
                }
              }}
            />
          );
        }
        return (
          <StackedBarWidget
            data={mockJointGroupData}
            stackKeys={["ForceFrame", "ForceDeck", "Standard"]}
            title={widget.title}
            onBarClick={(clickData) => {
              if (onChartClick) {
                const filters: Record<string, string> = {};
                if (clickData.name) {
                  filters.joint_group = clickData.name;
                }
                if (clickData.stackKey) {
                  filters.testing_focus = clickData.stackKey;
                }
                onChartClick({
                  title: `${widget.title}: ${clickData.name}${clickData.stackKey ? ` (${clickData.stackKey})` : ''}`,
                  filters,
                });
              }
            }}
          />
        );
      }

      case "scatter": {
        if (hasQueryConfig) {
          const { data: apiData, isLoading } = useWidgetData<Array<{ x: number; y: number; name: string; category?: string }>>({
            queryConfig: widget.queryConfig!,
            fallbackData: mockAsymmetryForceData,
          });
          return (
            <ScatterWidget
              data={apiData || mockAsymmetryForceData}
              xAxisLabel="Asymmetry %"
              yAxisLabel="Force Level"
              thresholdX={15}
              isLoading={isLoading}
              title={widget.title}
            />
          );
        }
        return (
          <ScatterWidget
            data={mockAsymmetryForceData}
            xAxisLabel="Asymmetry %"
            yAxisLabel="Force Level"
            thresholdX={15}
            title={widget.title}
          />
        );
      }

      case "lollipop": {
        if (hasQueryConfig) {
          const { data: apiData, isLoading } = useWidgetData<Array<{ name: string; value: number; category?: string }>>({
            queryConfig: widget.queryConfig!,
            fallbackData: mockAsymmetryData,
          });
          return (
            <LollipopWidget
              data={apiData || mockAsymmetryData}
              threshold={15}
              thresholdLabel="15% threshold"
              isLoading={isLoading}
              title={widget.title}
              onBarClick={(clickData) => {
                if (onChartClick) {
                  // For lollipop (asymmetry), we show all patients since we can't filter by exact asymmetry value
                  // Users can sort by asymmetry in the table
                  onChartClick({
                    title: `${widget.title}: ${clickData.name}`,
                    filters: {},
                  });
                }
              }}
            />
          );
        }
        return (
          <LollipopWidget
            data={mockAsymmetryData}
            threshold={15}
            thresholdLabel="15% threshold"
            title={widget.title}
            onBarClick={(clickData) => {
              if (onChartClick) {
                onChartClick({
                  title: `${widget.title}: ${clickData.name}`,
                  filters: {},
                });
              }
            }}
          />
        );
      }

      case "histogram": {
        if (hasQueryConfig) {
          const { data: apiData, isLoading } = useWidgetData<Array<{ range: string; min: number; max: number; count: number }>>({
            queryConfig: widget.queryConfig!,
            fallbackData: mockDistributionData,
          });
          return (
            <HistogramWidget
              data={apiData || mockDistributionData}
              xAxisLabel="Asymmetry %"
              yAxisLabel="Patients"
              isLoading={isLoading}
              title={widget.title}
              onBarClick={(clickData) => {
                if (onChartClick) {
                  // For histogram (asymmetry distribution), we show all patients
                  // Users can sort by asymmetry in the table to see patients in that range
                  onChartClick({
                    title: `${widget.title}: ${clickData.range}`,
                    filters: {},
                  });
                }
              }}
            />
          );
        }
        return (
          <HistogramWidget
            data={mockDistributionData}
            xAxisLabel="Asymmetry %"
            yAxisLabel="Patients"
            title={widget.title}
            onBarClick={(clickData) => {
              if (onChartClick) {
                onChartClick({
                  title: `${widget.title}: ${clickData.range}`,
                  filters: {},
                });
              }
            }}
          />
        );
      }

      case "heatmap": {
        if (hasQueryConfig) {
          const { data: apiData, isLoading } = useWidgetData<Array<{ xLabel: string; yLabel: string; value: number }>>({
            queryConfig: widget.queryConfig!,
            fallbackData: mockRiskCriticalityMatrix,
          });
          // Transform API response to heatmap format
          const heatmapData = apiData ? apiData.map(item => ({
            xLabel: item.xLabel,
            yLabel: item.yLabel,
            value: item.value,
          })) : mockRiskCriticalityMatrix;
          return (
            <HeatmapWidget
              data={heatmapData}
              xLabels={["High", "Medium", "Low"]}
              yLabels={["Low", "High"]}
              isLoading={isLoading}
              title={widget.title}
              onCellClick={(clickData) => {
                if (onChartClick) {
                  onChartClick({
                    title: `${widget.title}: ${clickData.xLabel} / ${clickData.yLabel}`,
                    filters: clickData.filters || {},
                  });
                }
              }}
            />
          );
        }
        return (
          <HeatmapWidget
            data={mockRiskCriticalityMatrix}
            xLabels={["High", "Medium"]}
            yLabels={["Low", "High"]}
            title={widget.title}
            onCellClick={(clickData) => {
              if (onChartClick) {
                onChartClick({
                  title: `${widget.title}: ${clickData.xLabel} / ${clickData.yLabel}`,
                  filters: clickData.filters || {},
                });
              }
            }}
          />
        );
      }

      case "patient-table": {
        if (hasQueryConfig) {
          // Use faster polling when triage is running (every 2 seconds instead of 60)
          const dynamicQueryConfig = {
            ...widget.queryConfig!,
            refreshInterval: isTriageRunning ? 2 : widget.queryConfig!.refreshInterval || 60,
          };
          
          const { data: apiData, isLoading, isError, error } = useWidgetData<Array<{
            id: string;
            patientName: string;
            provisionalDiagnosis?: string | null;
            canonicalDiagnosis?: string | null;
            primaryJoint?: string | null;
            functionalRegion?: string | null;
            occupationCategory?: string | null;
            activityProfile?: string | null;
            activitySubtype?: string | null;
            clinicalStage?: string | null;
            painInterference?: string | null;
            nprsAvailable: boolean;
            nprsScore?: number | null;
            intentCategory?: string | null;
            strengthAsymmetry?: number | null;
            absoluteForceLevel?: string | null;
            romAsymmetryDegrees?: number | null;
          }>>({
            queryConfig: dynamicQueryConfig,
            fallbackData: undefined, // Don't use fallback - force API data only
          });
          
          // Check if we have valid API data
          const hasApiData = apiData && Array.isArray(apiData) && apiData.length > 0;
          
          // Check if it's mock data (by checking for known mock patient names)
          const mockPatientNames = ["Michael T", "Emma L", "Sarah K", "Aria", "Marcus", "Sofia", "James"];
          const isMockData = hasApiData && apiData.some(p => mockPatientNames.includes(p.patientName));
          
          if (isLoading) {
            console.log("⏳ Patient table: Loading API data...");
            return (
              <PatientTableWidget
                data={[]}
                isLoading={true}
                title={widget.title}
              />
            );
          }
          
          if (isError) {
            console.error("❌ Patient table: API error:", error);
            console.error("   Endpoint:", widget.queryConfig?.endpoint);
            console.error("   API URL:", import.meta.env.VITE_API_URL || "http://localhost:8013");
            return (
              <PatientTableWidget
                data={[]}
                isLoading={false}
                title={widget.title}
              />
            );
          }
          
          if (!hasApiData) {
            console.warn("⚠️ Patient table: No API data received");
            return (
              <PatientTableWidget
                data={[]}
                isLoading={false}
                title={widget.title}
              />
            );
          }
          
          if (isMockData) {
            console.error("❌ Patient table: API returned mock data! This should not happen.");
            console.error("   Received data:", apiData);
            return (
              <PatientTableWidget
                data={[]}
                isLoading={false}
                title={widget.title}
              />
            );
          }
          
          console.log(`✅ Patient table: Using API data (${apiData.length} real patients)`);
          return (
            <PatientTableWidget
              data={apiData}
              isLoading={false}
              title={widget.title}
            />
          );
        }
        // No queryConfig - show empty or message
        console.warn("⚠️ Patient table: No queryConfig, cannot fetch data");
        return (
          <PatientTableWidget
            data={[]}
            isLoading={false}
            title={widget.title}
          />
        );
      }

      default:
        return <div className="p-4">Unknown widget type: {widget.type}</div>;
    }
  };

  const renderWidget = useCallback(
    (widget: WidgetType) => {
      return <WidgetRenderer widget={widget} />;
    },
    [data]
  );

  return (
    <GridLayout
      className="layout"
      layout={layouts}
      cols={6}
      rowHeight={80}
      width={width}
      onLayoutChange={(newLayout) => onLayoutChange(newLayout as WidgetLayout[])}
      draggableHandle=".drag-handle"
      isResizable={true}
      isDraggable={true}
      margin={[16, 16]}
      containerPadding={[0, 0]}
      compactType="vertical"
    >
      {widgets.map((widget) => (
        <div key={widget.id} className="relative">
          <WidgetWrapper
            onRemove={() => onRemoveWidget(widget.id)}
            onConfigChange={(config) => onConfigChange(widget.id, config)}
            queryConfig={widget.queryConfig}
            widgetType={widget.type}
          >
            {renderWidget(widget)}
          </WidgetWrapper>
        </div>
      ))}
    </GridLayout>
  );
};

export default DashboardGrid;

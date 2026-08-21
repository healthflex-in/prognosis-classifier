import { ClinicalFilters } from "./clinical";

export type WidgetTypeEnum =
  | "stats"
  | "chart"
  | "calendar"
  | "progress"
  | "table"
  | "bar"
  | "stacked-bar"
  | "grouped-bar"
  | "scatter"
  | "lollipop"
  | "histogram"
  | "heatmap"
  | "patient-table";

export interface FilterOption {
  field: keyof ClinicalFilters;
  label: string;
  options: { value: string; label: string }[];
}

export interface QueryConfig {
  endpoint: string;
  params?: Record<string, string>;
  refreshInterval?: number; // in seconds
  filters?: ClinicalFilters;
  availableFilters?: FilterOption[];
}

export interface WidgetType {
  id: string;
  type: WidgetTypeEnum;
  title: string;
  minW?: number;
  minH?: number;
  queryConfig?: QueryConfig;
}

export interface StatsData {
  label: string;
  value: string;
  trend: number;
  trendLabel: string;
}

export interface ChartDataPoint {
  name: string;
  value: number;
  category?: string;
}

export interface TableRow {
  id: string;
  courseName: string;
  studentName: string;
  studentId: string;
  amount: string;
  status: "Paid" | "Pending" | "Failed";
}

export interface CalendarDay {
  day: string;
  date: number;
  isToday?: boolean;
}

export interface ProgressData {
  label: string;
  value: number;
  trend: number;
  trendLabel: string;
}

export interface DashboardFilters {
  period: "Day" | "Week" | "Month" | "Year";
  dateRange: {
    start: string;
    end: string;
  };
}

export interface DashboardData {
  stats: StatsData[];
  chartData: ChartDataPoint[];
  tableData: TableRow[];
  calendarData: CalendarDay[];
  progressData: ProgressData;
}

export interface WidgetLayout {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
}

// Predefined endpoint options for widget configuration - Master Prompt Classification
export const endpointOptions = [
  {
    key: "patients",
    label: "Patient List",
    endpoint: "/api/patients",
    widgetTypes: ["patient-table", "table"] as WidgetTypeEnum[],
  },
  {
    key: "diagnosis",
    label: "Diagnosis Distribution",
    endpoint: "/api/stats/diagnosis",
    widgetTypes: ["bar", "stacked-bar"] as WidgetTypeEnum[],
  },
  {
    key: "joint-region",
    label: "Joint & Functional Region",
    endpoint: "/api/stats/joint-region",
    widgetTypes: ["bar", "grouped-bar"] as WidgetTypeEnum[],
  },
  {
    key: "occupation",
    label: "Occupational Categories",
    endpoint: "/api/stats/occupation",
    widgetTypes: ["bar"] as WidgetTypeEnum[],
  },
  {
    key: "activity-profile",
    label: "Activity Profile Distribution",
    endpoint: "/api/stats/activity-profile",
    widgetTypes: ["bar", "stacked-bar"] as WidgetTypeEnum[],
  },
  {
    key: "activity-recreational",
    label: "Recreational Activity Subtypes",
    endpoint: "/api/stats/activity-recreational",
    widgetTypes: ["bar"] as WidgetTypeEnum[],
  },
  {
    key: "clinical-stage",
    label: "Clinical Stage Distribution",
    endpoint: "/api/stats/clinical-stage",
    widgetTypes: ["bar", "stacked-bar"] as WidgetTypeEnum[],
  },
  {
    key: "pain-interference",
    label: "Pain Interference Levels",
    endpoint: "/api/stats/pain-interference",
    widgetTypes: ["bar"] as WidgetTypeEnum[],
  },
  {
    key: "nprs-availability",
    label: "NPRS Availability",
    endpoint: "/api/stats/nprs-availability",
    widgetTypes: ["stats", "bar"] as WidgetTypeEnum[],
  },
  {
    key: "nprs-distribution",
    label: "NPRS Distribution",
    endpoint: "/api/stats/nprs-distribution",
    widgetTypes: ["histogram", "bar"] as WidgetTypeEnum[],
  },
  {
    key: "pain-nprs-matrix",
    label: "Pain Interference × NPRS Matrix",
    endpoint: "/api/matrix/pain-nprs",
    widgetTypes: ["heatmap"] as WidgetTypeEnum[],
  },
  {
    key: "intent",
    label: "Outcome Intent Distribution",
    endpoint: "/api/stats/intent",
    widgetTypes: ["bar"] as WidgetTypeEnum[],
  },
] as const;

export const filterOptions: FilterOption[] = [
  {
    field: "criticality",
    label: "Criticality",
    options: [
      { value: "High", label: "High" },
      { value: "Medium", label: "Medium" },
      { value: "Low", label: "Low" },
    ],
  },
  {
    field: "timelineStatus",
    label: "Timeline",
    options: [
      { value: "Acute", label: "Acute" },
      { value: "Sub-Acute", label: "Sub-Acute" },
      { value: "Chronic", label: "Chronic" },
    ],
  },
  {
    field: "riskLevel",
    label: "Risk Level",
    options: [
      { value: "Low", label: "Low" },
      { value: "High", label: "High" },
    ],
  },
  {
    field: "jointGroup",
    label: "Joint Group",
    options: [
      { value: "Posterior Chain Dominant", label: "Posterior Chain" },
      { value: "Anterior Chain Dominant", label: "Anterior Chain" },
      { value: "Other", label: "Other" },
    ],
  },
  {
    field: "testingFocus",
    label: "Testing Focus",
    options: [
      { value: "ForceFrame", label: "ForceFrame" },
      { value: "ForceDeck", label: "ForceDeck" },
      { value: "Standard", label: "Standard" },
    ],
  },
];

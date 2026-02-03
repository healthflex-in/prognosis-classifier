import { PatientData } from "@/types/clinical";
import { DashboardData, WidgetType, WidgetLayout } from "@/types/dashboard";

// Original mock data for legacy widgets
export const mockDashboardData: DashboardData = {
  stats: [
    {
      label: "Total Revenue",
      value: "$23,902",
      trend: 4.2,
      trendLabel: "from last month",
    },
    {
      label: "Active Users",
      value: "16,815",
      trend: 1.7,
      trendLabel: "from last month",
    },
    {
      label: "New Users",
      value: "1,457",
      trend: -2.9,
      trendLabel: "from last month",
    },
    {
      label: "Total Mentors",
      value: "2,023",
      trend: 0.9,
      trendLabel: "from last month",
    },
  ],
  chartData: [
    { name: "Jan", value: 4000 },
    { name: "Feb", value: 6000 },
    { name: "Mar", value: 8500 },
    { name: "Apr", value: 3000 },
    { name: "May", value: 5500 },
    { name: "Jun", value: 7000 },
  ],
  tableData: [
    {
      id: "1",
      courseName: "Digital Marketing",
      studentName: "Aria",
      studentId: "#3456791",
      amount: "$372.00",
      status: "Paid",
    },
    {
      id: "2",
      courseName: "Web Development",
      studentName: "Marcus",
      studentId: "#3456792",
      amount: "$450.00",
      status: "Pending",
    },
    {
      id: "3",
      courseName: "UI/UX Design",
      studentName: "Sofia",
      studentId: "#3456793",
      amount: "$299.00",
      status: "Paid",
    },
    {
      id: "4",
      courseName: "Data Science",
      studentName: "James",
      studentId: "#3456794",
      amount: "$520.00",
      status: "Failed",
    },
  ],
  calendarData: [
    { day: "Tue", date: 17 },
    { day: "Wed", date: 18 },
    { day: "Thu", date: 19, isToday: true },
    { day: "Fri", date: 20 },
    { day: "Sat", date: 21 },
  ],
  progressData: {
    label: "Community Growth",
    value: 65,
    trend: 0.9,
    trendLabel: "from last month",
  },
};

// Clinical patient mock data
export const mockPatientData: PatientData[] = [
  {
    id: "1",
    patientName: "Premanka M",
    criticality: "Medium",
    goal: "RTA",
    timelineStatus: "Chronic",
    riskLevel: "Low",
    jointGroup: "Posterior Chain Dominant",
    primaryJoint: "L knee",
    testingFocus: "ForceFrame",
    strengthAsymmetry: 36.9,
    absoluteForceLevel: "Medium",
  },
  {
    id: "2",
    patientName: "Prathyush R",
    criticality: "High",
    goal: "RTS",
    timelineStatus: "Acute",
    riskLevel: "Low",
    jointGroup: "Other",
    primaryJoint: "Knee",
    testingFocus: "Standard",
    strengthAsymmetry: null,
    absoluteForceLevel: null,
  },
  {
    id: "3",
    patientName: "Avinash P",
    criticality: "High",
    goal: "RTA",
    timelineStatus: "Acute",
    riskLevel: "High",
    jointGroup: "Anterior Chain Dominant",
    primaryJoint: "Knee (PFJ)",
    testingFocus: "ForceDeck",
    strengthAsymmetry: 16.4,
    absoluteForceLevel: "Low",
  },
  {
    id: "4",
    patientName: "Sarah K",
    criticality: "Medium",
    goal: "RTS",
    timelineStatus: "Sub-Acute",
    riskLevel: "Low",
    jointGroup: "Posterior Chain Dominant",
    primaryJoint: "R hip",
    testingFocus: "ForceFrame",
    strengthAsymmetry: 22.3,
    absoluteForceLevel: "Medium",
  },
  {
    id: "5",
    patientName: "Michael T",
    criticality: "High",
    goal: "RTA",
    timelineStatus: "Chronic",
    riskLevel: "Low",
    jointGroup: "Anterior Chain Dominant",
    primaryJoint: "L ankle",
    testingFocus: "ForceDeck",
    strengthAsymmetry: 8.7,
    absoluteForceLevel: "High",
  },
  {
    id: "6",
    patientName: "Emma L",
    criticality: "Medium",
    goal: "RTS",
    timelineStatus: "Acute",
    riskLevel: "Low",
    jointGroup: "Other",
    primaryJoint: "Shoulder",
    testingFocus: "Standard",
    strengthAsymmetry: 12.1,
    absoluteForceLevel: "Medium",
  },
];

// Mock data generators for clinical widgets
export const mockCriticalityData = [
  { name: "High", value: 3 },
  { name: "Medium", value: 3 },
];

export const mockTimelineData = [
  { name: "Acute", value: 3, High: 1, Medium: 2 },
  { name: "Sub-Acute", value: 1, High: 0, Medium: 1 },
  { name: "Chronic", value: 2, High: 1, Medium: 1 },
];

export const mockRiskData = [
  { name: "Low", value: 5 },
  { name: "High", value: 1 },
];

export const mockJointGroupData = [
  { name: "Posterior Chain", value: 2, ForceFrame: 2, ForceDeck: 0, Standard: 0 },
  { name: "Anterior Chain", value: 2, ForceFrame: 0, ForceDeck: 2, Standard: 0 },
  { name: "Other", value: 2, ForceFrame: 0, ForceDeck: 0, Standard: 2 },
];

export const mockTestingFocusData = [
  { name: "ForceFrame", value: 2 },
  { name: "ForceDeck", value: 2 },
  { name: "Standard", value: 2 },
];

export const mockAsymmetryData = mockPatientData
  .filter((p) => p.strengthAsymmetry !== null)
  .map((p) => ({
    name: p.patientName,
    value: p.strengthAsymmetry!,
    category: p.criticality,
  }));

export const mockAsymmetryForceData = mockPatientData
  .filter((p) => p.strengthAsymmetry !== null && p.absoluteForceLevel !== null)
  .map((p) => ({
    x: p.strengthAsymmetry!,
    y: p.absoluteForceLevel === "High" ? 3 : p.absoluteForceLevel === "Medium" ? 2 : 1,
    name: p.patientName,
    category: p.criticality,
  }));

export const mockDistributionData = [
  { range: "0-10%", min: 0, max: 10, count: 1 },
  { range: "10-20%", min: 10, max: 20, count: 2 },
  { range: "20-30%", min: 20, max: 30, count: 1 },
  { range: "30-40%", min: 30, max: 40, count: 1 },
];

export const mockRiskCriticalityMatrix = [
  { xLabel: "High", yLabel: "Low", value: 2 },
  { xLabel: "Medium", yLabel: "Low", value: 3 },
  { xLabel: "High", yLabel: "High", value: 1 },
  { xLabel: "Medium", yLabel: "High", value: 0 },
];

export const availableWidgets: WidgetType[] = [
  { id: "stats-1", type: "stats", title: "Statistics", minW: 4, minH: 2 },
  { id: "chart-1", type: "chart", title: "Revenue Chart", minW: 3, minH: 3 },
  { id: "calendar-1", type: "calendar", title: "Calendar", minW: 2, minH: 3 },
  { id: "progress-1", type: "progress", title: "Progress", minW: 2, minH: 3 },
  { id: "table-1", type: "table", title: "Course Purchases", minW: 4, minH: 3 },
];

export const defaultLayout: WidgetLayout[] = [
  { i: "stats-1", x: 0, y: 0, w: 6, h: 2, minW: 4, minH: 2 },
  { i: "chart-1", x: 0, y: 2, w: 3, h: 4, minW: 3, minH: 3 },
  { i: "calendar-1", x: 3, y: 2, w: 2, h: 4, minW: 2, minH: 3 },
  { i: "progress-1", x: 5, y: 2, w: 1, h: 4, minW: 1, minH: 3 },
  { i: "table-1", x: 0, y: 6, w: 6, h: 3, minW: 4, minH: 3 },
];

// Clinical widget defaults - Master Prompt Classification
export const clinicalWidgets: WidgetType[] = [
  {
    id: "diagnosis-1",
    type: "bar",
    title: "Diagnosis Distribution",
    minW: 2,
    minH: 3,
    queryConfig: {
      endpoint: "/api/stats/diagnosis",
      refreshInterval: 60,
    },
  },
  {
    id: "clinical-stage-1",
    type: "bar",
    title: "Clinical Stage",
    minW: 2,
    minH: 3,
    queryConfig: {
      endpoint: "/api/stats/clinical-stage",
      refreshInterval: 60,
    },
  },
  {
    id: "pain-interference-1",
    type: "bar",
    title: "Pain Interference",
    minW: 2,
    minH: 3,
    queryConfig: {
      endpoint: "/api/stats/pain-interference",
      refreshInterval: 60,
    },
  },
  {
    id: "activity-profile-1",
    type: "bar",
    title: "Activity Profile",
    minW: 2,
    minH: 3,
    queryConfig: {
      endpoint: "/api/stats/activity-profile",
      refreshInterval: 60,
    },
  },
  {
    id: "nprs-distribution-1",
    type: "histogram",
    title: "NPRS Distribution",
    minW: 2,
    minH: 3,
    queryConfig: {
      endpoint: "/api/stats/nprs-distribution",
      refreshInterval: 60,
    },
  },
  {
    id: "pain-nprs-matrix-1",
    type: "heatmap",
    title: "Pain Interference × NPRS",
    minW: 3,
    minH: 3,
    queryConfig: {
      endpoint: "/api/matrix/pain-nprs",
      refreshInterval: 60,
    },
  },
  {
    id: "intent-1",
    type: "bar",
    title: "Outcome Intent",
    minW: 2,
    minH: 3,
    queryConfig: {
      endpoint: "/api/stats/intent",
      refreshInterval: 60,
    },
  },
  {
    id: "patient-table-1",
    type: "patient-table",
    title: "Patient List",
    minW: 6,
    minH: 4,
    queryConfig: {
      endpoint: "/api/patients",
      refreshInterval: 60,
    },
  },
];

export const clinicalDefaultLayout: WidgetLayout[] = [
  { i: "diagnosis-1", x: 0, y: 0, w: 2, h: 3, minW: 2, minH: 3 },
  { i: "clinical-stage-1", x: 2, y: 0, w: 2, h: 3, minW: 2, minH: 3 },
  { i: "pain-interference-1", x: 4, y: 0, w: 2, h: 3, minW: 2, minH: 3 },
  { i: "activity-profile-1", x: 0, y: 3, w: 2, h: 3, minW: 2, minH: 3 },
  { i: "nprs-distribution-1", x: 2, y: 3, w: 2, h: 3, minW: 2, minH: 3 },
  { i: "pain-nprs-matrix-1", x: 4, y: 3, w: 2, h: 3, minW: 3, minH: 3 },
  { i: "intent-1", x: 0, y: 6, w: 2, h: 3, minW: 2, minH: 3 },
  { i: "patient-table-1", x: 2, y: 6, w: 4, h: 4, minW: 4, minH: 4 },
];

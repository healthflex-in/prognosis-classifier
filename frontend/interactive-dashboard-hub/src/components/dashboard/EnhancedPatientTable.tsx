import { useState, useMemo } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { PatientMasterView } from "@/types/clinical";
import { cn } from "@/lib/utils";
import { ArrowUpDown, Download, Settings2 } from "lucide-react";
// @ts-ignore - xlsx types may not be perfect
import * as XLSX from "xlsx";

interface Column {
  key: keyof PatientMasterView | "actions";
  label: string;
  visible: boolean;
  sortable: boolean;
  render?: (value: any, patient: PatientMasterView) => React.ReactNode;
}

interface EnhancedPatientTableProps {
  data: PatientMasterView[];
  isLoading?: boolean;
  title?: string;
}

type SortField = keyof PatientMasterView | null;
type SortDirection = "asc" | "desc" | null;

const getClinicalStageVariant = (stage: string) => {
  switch (stage) {
    case "Acute":
      return "destructive";
    case "Subacute":
      return "secondary";
    case "Chronic":
      return "outline";
    default:
      return "outline";
  }
};

const defaultColumns: Column[] = [
  { key: "patientName", label: "Patient", visible: true, sortable: true },
  { key: "canonicalDiagnosis", label: "Diagnosis", visible: true, sortable: true },
  { key: "primaryJoint", label: "Joint", visible: true, sortable: true },
  { key: "functionalRegion", label: "Region", visible: true, sortable: true },
  { key: "clinicalStage", label: "Stage", visible: true, sortable: true },
  { key: "painInterference", label: "Pain Interference", visible: true, sortable: true },
  { key: "nprsScore", label: "NPRS", visible: true, sortable: true },
  { key: "intentCategory", label: "Intent", visible: true, sortable: true },
  { key: "absoluteForceLevel", label: "Force Level", visible: true, sortable: true },
];

const EnhancedPatientTable = ({
  data,
  isLoading = false,
  title,
}: EnhancedPatientTableProps) => {
  const [columns, setColumns] = useState<Column[]>(defaultColumns);
  const [sortField, setSortField] = useState<SortField>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);

  // Toggle column visibility
  const toggleColumn = (key: string) => {
    setColumns((prev) =>
      prev.map((col) =>
        col.key === key ? { ...col, visible: !col.visible } : col
      )
    );
  };

  // Handle sorting
  const handleSort = (field: keyof PatientMasterView) => {
    if (sortField === field) {
      // Toggle direction
      if (sortDirection === "asc") {
        setSortDirection("desc");
      } else if (sortDirection === "desc") {
        setSortField(null);
        setSortDirection(null);
      } else {
        setSortDirection("asc");
      }
    } else {
      setSortField(field);
      setSortDirection("asc");
    }
  };

  // Sort data
  const sortedData = useMemo(() => {
    if (!sortField || !sortDirection) return data;

    return [...data].sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];

      // Handle null/undefined values
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;

      // Handle numbers
      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDirection === "asc" ? aVal - bVal : bVal - aVal;
      }

      // Handle strings
      const aStr = String(aVal);
      const bStr = String(bVal);
      if (sortDirection === "asc") {
        return aStr.localeCompare(bStr);
      } else {
        return bStr.localeCompare(aStr);
      }
    });
  }, [data, sortField, sortDirection]);

  // Export to Excel
  const exportToExcel = () => {
    // Get visible columns
    const visibleColumns = columns.filter((col) => col.visible && col.key !== "actions");

    // Prepare data for export
    const exportData = sortedData.map((patient) => {
      const row: Record<string, any> = {};
      visibleColumns.forEach((col) => {
        const value = patient[col.key as keyof PatientMasterView];
        if (col.key === "nprsScore") {
          row[col.label] = patient.nprsAvailable && value !== null ? `${value}/10` : "–";
        } else if (col.key === "functionalRegion") {
          row[col.label] = typeof value === "string" ? value : (value?.value || "–");
        } else {
          row[col.label] = value ?? "–";
        }
      });
      return row;
    });

    // Create workbook and worksheet
    const ws = XLSX.utils.json_to_sheet(exportData);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Patients");

    // Generate filename with timestamp
    const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, "-");
    const filename = `patients_${timestamp}.xlsx`;

    // Write file
    XLSX.writeFile(wb, filename);
  };

  const visibleColumns = columns.filter((col) => col.visible);

  const renderCell = (column: Column, patient: PatientMasterView) => {
    const value = patient[column.key as keyof PatientMasterView];

    switch (column.key) {
      case "clinicalStage":
        return (
          <Badge
            variant={getClinicalStageVariant((value as string) || "Unclear")}
            className="text-[10px] px-1.5 py-0"
          >
            {value || "Unclear"}
          </Badge>
        );
      case "primaryJoint":
        return (
          <span className="text-xs truncate max-w-[80px]" title={value as string || "Unclear"}>
            {value || "Unclear"}
          </span>
        );
      case "functionalRegion":
        const regionValue = typeof value === "string" ? value : (value as any)?.value;
        return (
          <span className="text-xs">{regionValue || "Unclear"}</span>
        );
      case "nprsScore":
        return (
          <span className="text-xs">
            {patient.nprsAvailable && value !== null && value !== undefined
              ? `${value}/10`
              : "–"}
          </span>
        );
      case "canonicalDiagnosis":
      case "painInterference":
      case "intentCategory":
        return (
          <span className="text-xs truncate max-w-[120px]" title={value as string || "Unclear"}>
            {value || "Unclear"}
          </span>
        );
      default:
        return <span className="text-xs">{value ?? "–"}</span>;
    }
  };

  return (
    <div className="h-full w-full flex flex-col overflow-hidden">
      {/* Header with controls */}
      <div className="flex items-center justify-between mb-4 px-1">
        {title && (
          <h3 className="text-sm font-medium text-foreground">{title}</h3>
        )}
        <div className="flex items-center gap-2 ml-auto">
          {/* Column visibility dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="h-8">
                <Settings2 className="h-4 w-4 mr-2" />
                Columns
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuLabel>Toggle Columns</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {columns
                .filter((col) => col.key !== "actions")
                .map((column) => (
                  <DropdownMenuCheckboxItem
                    key={column.key}
                    checked={column.visible}
                    onCheckedChange={() => toggleColumn(column.key)}
                  >
                    {column.label}
                  </DropdownMenuCheckboxItem>
                ))}
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Export button */}
          <Button
            variant="outline"
            size="sm"
            className="h-8"
            onClick={exportToExcel}
            disabled={sortedData.length === 0}
          >
            <Download className="h-4 w-4 mr-2" />
            Export
          </Button>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto min-h-0 border rounded-md">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              {visibleColumns.map((column) => (
                <TableHead
                  key={column.key}
                  className={cn(
                    "text-xs",
                    column.sortable && "cursor-pointer hover:bg-muted/50"
                  )}
                  onClick={() => {
                    if (column.sortable && column.key !== "actions") {
                      handleSort(column.key as keyof PatientMasterView);
                    }
                  }}
                >
                  <div className="flex items-center gap-1">
                    {column.label}
                    {column.sortable && column.key !== "actions" && (
                      <ArrowUpDown className="h-3 w-3 opacity-50" />
                    )}
                    {sortField === column.key && (
                      <span className="text-[10px] opacity-70">
                        {sortDirection === "asc" ? "↑" : "↓"}
                      </span>
                    )}
                  </div>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedData.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={visibleColumns.length}
                  className="text-center text-sm text-muted-foreground py-8"
                >
                  No patients found
                </TableCell>
              </TableRow>
            ) : (
              sortedData.map((patient) => (
                <TableRow
                  key={patient.id}
                  className={cn(
                    patient.clinicalStage === "Acute" && "bg-destructive/5"
                  )}
                >
                  {visibleColumns.map((column) => (
                    <TableCell
                      key={column.key}
                      className="text-xs"
                    >
                      {renderCell(column, patient)}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Footer with count */}
      <div className="mt-2 px-1 text-xs text-muted-foreground">
        Showing {sortedData.length} patient{sortedData.length !== 1 ? "s" : ""}
      </div>
    </div>
  );
};

export default EnhancedPatientTable;

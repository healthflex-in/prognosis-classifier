import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { PatientMasterView } from "@/types/clinical";
import { cn } from "@/lib/utils";

interface PatientTableWidgetProps {
  data: PatientMasterView[];
  isLoading?: boolean;
  title?: string;
}

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

const PatientTableWidget = ({
  data,
  isLoading = false,
  title,
}: PatientTableWidgetProps) => {
  if (isLoading) {
    return (
      <div className="h-full w-full p-4 flex flex-col gap-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-full" />
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="h-full w-full p-4 flex flex-col items-center justify-center">
        {title && (
          <h3 className="text-sm font-medium text-foreground mb-3">{title}</h3>
        )}
        <div className="text-center text-muted-foreground text-sm">
          <p>No patient data available</p>
          <p className="text-xs mt-2">Run triage classification to generate data</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full p-4 flex flex-col overflow-hidden">
      {title && (
        <h3 className="text-sm font-medium text-foreground mb-3">{title}</h3>
      )}
      <div className="flex-1 overflow-auto min-h-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="text-xs">Patient</TableHead>
              <TableHead className="text-xs">Diagnosis</TableHead>
              <TableHead className="text-xs">Joint</TableHead>
              <TableHead className="text-xs">Region</TableHead>
              <TableHead className="text-xs">Stage</TableHead>
              <TableHead className="text-xs">Pain</TableHead>
              <TableHead className="text-xs">NPRS</TableHead>
              <TableHead className="text-xs">Intent</TableHead>
              <TableHead className="text-xs">Force</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((patient) => (
              <TableRow
                key={patient.id}
                className={cn(
                  patient.clinicalStage === "Acute" && "bg-destructive/5"
                )}
              >
                <TableCell className="text-xs font-medium">
                  {patient.patientName}
                </TableCell>
                <TableCell className="text-xs truncate max-w-[100px]" title={patient.canonicalDiagnosis || "Unclear"}>
                  {patient.canonicalDiagnosis || "Unclear"}
                </TableCell>
                <TableCell className="text-xs truncate max-w-[80px]">
                  {patient.primaryJoint || "Unclear"}
                </TableCell>
                <TableCell className="text-xs">
                  {typeof patient.functionalRegion === "string" 
                    ? patient.functionalRegion 
                    : (patient.functionalRegion?.value || "Unclear")}
                </TableCell>
                <TableCell>
                  <Badge
                    variant={getClinicalStageVariant(patient.clinicalStage || "Unclear")}
                    className="text-[10px] px-1.5 py-0"
                  >
                    {patient.clinicalStage || "Unclear"}
                  </Badge>
                </TableCell>
                <TableCell className="text-xs truncate max-w-[100px]" title={patient.painInterference || "Unclear"}>
                  {patient.painInterference || "Unclear"}
                </TableCell>
                <TableCell className="text-xs">
                  {patient.nprsAvailable && patient.nprsScore !== null
                    ? `${patient.nprsScore}/10`
                    : "–"}
                </TableCell>
                <TableCell className="text-xs truncate max-w-[100px]" title={patient.intentCategory || "Unclear"}>
                  {patient.intentCategory || "Unclear"}
                </TableCell>
                <TableCell className="text-xs">
                  {patient.absoluteForceLevel || "–"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
};

export default PatientTableWidget;

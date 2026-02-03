import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import EnhancedPatientTable from "./EnhancedPatientTable";
import { PatientMasterView } from "@/types/clinical";
import { useWidgetData } from "@/hooks/useWidgetData";
import { QueryConfig } from "@/types/dashboard";

interface ChartSidebarProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  filters?: {
    canonical_diagnosis?: string;
    primary_joint?: string;
    functional_region?: string;
    clinical_stage?: string;
    pain_interference?: string;
    intent_category?: string;
  };
}

export const ChartSidebar = ({
  open,
  onOpenChange,
  title,
  description,
  filters,
}: ChartSidebarProps) => {
  // Build query config with filters
  const queryConfig: QueryConfig | undefined = filters
    ? {
        endpoint: "/api/patients",
        params: {
          canonical_diagnosis: filters.canonical_diagnosis,
          primary_joint: filters.primary_joint,
          functional_region: filters.functional_region,
          clinical_stage: filters.clinical_stage,
          pain_interference: filters.pain_interference,
          intent_category: filters.intent_category,
        },
      }
    : undefined;

  const { data: patients, isLoading } = useWidgetData<PatientMasterView[]>({
    queryConfig: queryConfig!,
    enabled: open && !!queryConfig,
    fallbackData: [],
  });

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-4xl flex flex-col">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          {description && <SheetDescription>{description}</SheetDescription>}
        </SheetHeader>
        <div className="mt-6 flex-1 min-h-0 flex flex-col">
          {isLoading ? (
            <div className="flex items-center justify-center h-64">
              <p className="text-sm text-muted-foreground">Loading patients...</p>
            </div>
          ) : patients && patients.length > 0 ? (
            <EnhancedPatientTable data={patients} isLoading={isLoading} />
          ) : (
            <div className="flex items-center justify-center h-64">
              <p className="text-sm text-muted-foreground">No patients found matching the selected criteria.</p>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
};

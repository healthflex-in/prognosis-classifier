import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface TriageRunDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRun: (monthsBack: number | null, limit: number | null) => void;
}

const TriageRunDialog = ({
  open,
  onOpenChange,
  onRun,
}: TriageRunDialogProps) => {
  const [monthsBack, setMonthsBack] = useState<string>("");
  const [limit, setLimit] = useState<string>("");

  const handleSubmit = () => {
    // Convert to numbers, or null if empty
    const monthsBackValue = monthsBack.trim() 
      ? parseInt(monthsBack.trim()) 
      : null;
    const limitValue = limit.trim() 
      ? parseInt(limit.trim()) 
      : null;

    // Validate monthsBack if provided
    if (monthsBackValue !== null && (isNaN(monthsBackValue) || monthsBackValue < 1)) {
      return; // Don't submit if invalid
    }

    // Validate limit if provided
    if (limitValue !== null && (isNaN(limitValue) || limitValue < 1)) {
      return; // Don't submit if invalid
    }

    onRun(monthsBackValue, limitValue);
    onOpenChange(false);
    
    // Reset form
    setMonthsBack("");
    setLimit("");
  };

  const handleCancel = () => {
    onOpenChange(false);
    setMonthsBack("");
    setLimit("");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Run Triage Classification</DialogTitle>
          <DialogDescription>
            Configure the classification parameters. Leave fields empty to process all patients.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="months-back">Months Back</Label>
            <Input
              id="months-back"
              type="number"
              min="1"
              placeholder="e.g., 5 (leave empty for all)"
              value={monthsBack}
              onChange={(e) => setMonthsBack(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Number of months to look back for First Assessment records. Leave empty to process all available records.
            </p>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="limit">Number of Patients</Label>
            <Input
              id="limit"
              type="number"
              min="1"
              placeholder="e.g., 100 (leave empty for all)"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Maximum number of patients to process. Leave empty to process all eligible patients.
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={handleCancel}>
            Cancel
          </Button>
          <Button onClick={handleSubmit}>
            Run Classification
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default TriageRunDialog;

import { ArrowUpRight, RefreshCw } from "lucide-react";
import { TableRow } from "@/types/dashboard";
import { Badge } from "@/components/ui/badge";

interface TableWidgetProps {
  data: TableRow[];
  title?: string;
}

const TableWidget = ({ data, title = "Course Purchases" }: TableWidgetProps) => {
  const getStatusVariant = (status: TableRow["status"]) => {
    switch (status) {
      case "Paid":
        return "default";
      case "Pending":
        return "secondary";
      case "Failed":
        return "destructive";
      default:
        return "secondary";
    }
  };

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-foreground">{title}</h3>
        <div className="flex gap-1">
          <button className="p-1.5 rounded-lg hover:bg-muted transition-colors">
            <RefreshCw className="h-4 w-4 text-muted-foreground" />
          </button>
          <button className="p-1.5 rounded-lg hover:bg-muted transition-colors">
            <ArrowUpRight className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>
      </div>
      
      <div className="flex-1 overflow-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left text-xs font-medium text-muted-foreground pb-3">Course Name</th>
              <th className="text-left text-xs font-medium text-muted-foreground pb-3">Student Name</th>
              <th className="text-left text-xs font-medium text-muted-foreground pb-3">Student ID</th>
              <th className="text-left text-xs font-medium text-muted-foreground pb-3">Amount</th>
              <th className="text-left text-xs font-medium text-muted-foreground pb-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.id} className="border-b border-border/50 last:border-0">
                <td className="py-3">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center">
                      <span className="text-xs font-medium text-muted-foreground">
                        {row.courseName.charAt(0)}
                      </span>
                    </div>
                    <span className="text-sm font-medium text-foreground">{row.courseName}</span>
                  </div>
                </td>
                <td className="py-3 text-sm text-foreground">{row.studentName}</td>
                <td className="py-3 text-sm text-muted-foreground">{row.studentId}</td>
                <td className="py-3 text-sm font-medium text-foreground">{row.amount}</td>
                <td className="py-3">
                  <Badge variant={getStatusVariant(row.status)} className="text-xs">
                    {row.status}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default TableWidget;

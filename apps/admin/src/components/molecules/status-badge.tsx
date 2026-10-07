import { Badge } from "@/components/atoms/badge";
export function StatusBadge({ value }: { value: string }) {
  return (
    <Badge variant="outline" className="capitalize">
      {value.replaceAll("_", " ")}
    </Badge>
  );
}

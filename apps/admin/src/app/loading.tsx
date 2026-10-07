import { QueryState } from "@/components/molecules/query-state";
export default function Loading() {
  return (
    <div className="p-6">
      <QueryState pending error={null} />
    </div>
  );
}

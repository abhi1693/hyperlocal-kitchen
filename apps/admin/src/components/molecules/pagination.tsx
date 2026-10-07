import { Button } from "@/components/atoms/button";
export function Pagination({
  total,
  offset,
  limit = 30,
  onPage,
}: {
  total: number;
  offset: number;
  limit?: number;
  onPage: (value: number) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
      <p className="text-muted-foreground">
        {total ? `${offset + 1}–${Math.min(offset + limit, total)} of ${total}` : "0 results"}
      </p>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={offset === 0}
          onClick={() => onPage(Math.max(0, offset - limit))}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={offset + limit >= total}
          onClick={() => onPage(offset + limit)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}

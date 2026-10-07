import { Skeleton } from "@/components/atoms/skeleton";
import { Button } from "@/components/atoms/button";
export function QueryState({
  pending,
  error,
  retry,
}: {
  pending: boolean;
  error: Error | null;
  retry?: () => void;
}) {
  if (pending)
    return (
      <div aria-label="Loading" aria-busy="true" className="space-y-3">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  if (error)
    return (
      <div role="alert" className="rounded-lg border p-6">
        <p>{error.message}</p>
        {retry && (
          <Button variant="outline" className="mt-4" onClick={retry}>
            Try again
          </Button>
        )}
      </div>
    );
  return null;
}

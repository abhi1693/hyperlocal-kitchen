import { ApiError } from "@/lib/api/client";
export function FormError({ error }: { error: Error | null }) {
  if (!error) return null;
  return (
    <div role="alert" className="rounded-md border bg-muted p-3 text-sm">
      <p>{error.message}</p>
      {error instanceof ApiError && Object.keys(error.fields).length > 0 && (
        <ul className="mt-2 list-inside list-disc">
          {Object.entries(error.fields).map(([field, message]) => (
            <li key={field}>
              {field.replaceAll("_", " ")}: {message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

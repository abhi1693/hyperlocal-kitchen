"use client";
import { Button } from "@/components/atoms/button";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <div role="alert" className="mx-auto max-w-md space-y-4 p-8">
      <h1 className="text-xl font-semibold">Unable to load this page</h1>
      <p className="text-sm text-muted-foreground">
        Please try again. If the issue continues, sign in again.
      </p>
      <Button onClick={reset}>Try again</Button>
      <Button asChild variant="outline">
        <a href="/login">Sign in</a>
      </Button>
    </div>
  );
}

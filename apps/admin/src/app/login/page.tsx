import { redirect } from "next/navigation";
import { authConfiguration, currentAdmin } from "@/lib/server/session";
import { Button } from "@/components/atoms/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/atoms/card";
export const dynamic = "force-dynamic";
export default async function Login({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; signed_out?: string }>;
}) {
  let enabled = false;
  let unavailable = false;
  let admin = null;
  try {
    admin = await currentAdmin();
    enabled = (await authConfiguration()).enabled;
  } catch {
    unavailable = true;
  }
  if (admin) redirect("/start");
  const { error, signed_out } = await searchParams;
  return (
    <main className="flex min-h-dvh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Hyperlocal Kitchen</CardTitle>
          <CardDescription>Sign in to administer your communities.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {unavailable ? (
            <p role="alert" className="text-sm">
              The admin service is unavailable. Please try again shortly.
            </p>
          ) : error ? (
            <p role="alert" className="text-sm">
              {error === "access_denied"
                ? "Your account does not have platform administrator access."
                : "Sign-in was not completed. Please try again."}
            </p>
          ) : signed_out ? (
            <p className="text-sm">You have signed out.</p>
          ) : null}
          {enabled ? (
            <Button asChild className="w-full">
              <a href="/api/v1/auth/login">Sign in</a>
            </Button>
          ) : (
            !unavailable && (
              <p className="text-sm text-muted-foreground">
                Administrator sign-in has not been configured.
              </p>
            )
          )}
        </CardContent>
      </Card>
    </main>
  );
}

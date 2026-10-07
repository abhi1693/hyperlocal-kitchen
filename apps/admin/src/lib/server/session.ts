import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { AdminPrincipal, AuthConfig } from "@/lib/api/generated/models";
import { adminApiOrigin } from "./config";
export async function currentAdmin(): Promise<AdminPrincipal | null> {
  const jar = await cookies();
  const session = jar.get("__Host-kitchen_admin_session") ?? jar.get("kitchen_admin_session");
  if (!session) return null;
  const response = await fetch(`${adminApiOrigin()}/api/v1/auth/me`, {
    headers: { Cookie: `${session.name}=${session.value}` },
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(10000),
  });
  if ([401, 403].includes(response.status)) return null;
  if (!response.ok) throw new Error("The admin service is unavailable.");
  return response.json();
}
export async function requireAdmin() {
  const admin = await currentAdmin();
  if (!admin) redirect("/login");
  return admin;
}
export async function authConfiguration(): Promise<AuthConfig> {
  const response = await fetch(`${adminApiOrigin()}/api/v1/auth/config`, {
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) throw new Error("The admin service is unavailable.");
  return response.json();
}

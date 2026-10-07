"use client";
import { createContext, useContext, useEffect } from "react";
import type { AdminPrincipal } from "@/lib/api/generated/models";
import { setCsrfToken } from "@/lib/api/client";
const Context = createContext<AdminPrincipal | null>(null);
export function AdminSession({
  admin,
  children,
}: {
  admin: AdminPrincipal;
  children: React.ReactNode;
}) {
  useEffect(() => {
    setCsrfToken(admin.csrf_token);
    return () => setCsrfToken(undefined);
  }, [admin.csrf_token]);
  return <Context.Provider value={admin}>{children}</Context.Provider>;
}
export function useAdmin() {
  const admin = useContext(Context);
  if (!admin) throw new Error("Administrator session required");
  return admin;
}

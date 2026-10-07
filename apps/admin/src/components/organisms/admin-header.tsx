"use client";
import { useState } from "react";
import { useTheme } from "next-themes";
import { Moon, Sun, LogOut } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/atoms/button";
import { useAdmin } from "@/components/molecules/admin-session";
import { setCsrfToken } from "@/lib/api/client";
import { logoutApiV1AuthLogoutPost } from "@/lib/api/generated/admin";
export function AdminHeader() {
  const admin = useAdmin();
  const { resolvedTheme, setTheme } = useTheme();
  const client = useQueryClient();
  const [leaving, setLeaving] = useState(false);
  async function logout() {
    setLeaving(true);
    try {
      await logoutApiV1AuthLogoutPost();
      setCsrfToken(undefined);
      client.clear();
      window.location.replace("/login?signed_out=1");
    } catch (error) {
      toast.error((error as Error).message);
      setLeaving(false);
    }
  }
  return (
    <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b bg-card px-4 sm:px-6">
      <div>
        <p className="font-semibold tracking-tight">Hyperlocal Kitchen</p>
        <p className="text-xs text-muted-foreground">Administration</p>
      </div>
      <div className="flex items-center gap-2">
        <span className="hidden text-sm text-muted-foreground sm:inline">
          {admin.name ?? admin.email ?? "Administrator"}
        </span>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Toggle light or dark theme"
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
        >
          <Sun className="dark:hidden" />
          <Moon className="hidden dark:block" />
        </Button>
        <Button variant="outline" size="sm" loading={leaving} onClick={logout}>
          <LogOut />
          Sign out
        </Button>
      </div>
    </header>
  );
}

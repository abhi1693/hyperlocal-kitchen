import type { AdminPrincipal } from "@/lib/api/generated/models";
import { AdminSession } from "@/components/molecules/admin-session";
import { AdminHeader } from "@/components/organisms/admin-header";
import { Sidebar } from "@/components/organisms/sidebar";
export function AdminLayout({
  admin,
  children,
}: {
  admin: AdminPrincipal;
  children: React.ReactNode;
}) {
  return (
    <AdminSession admin={admin}>
      <div className="flex min-h-dvh flex-col">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-background focus:p-4"
        >
          Skip to content
        </a>
        <AdminHeader />
        <div className="flex flex-1 flex-col lg:flex-row">
          <Sidebar />
          <main id="main" className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">
            <div className="mx-auto max-w-6xl space-y-6">{children}</div>
          </main>
        </div>
      </div>
    </AdminSession>
  );
}

"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Building2,
  ChefHat,
  ClipboardList,
  Users,
  House,
  Menu,
  X,
  UserRoundCheck,
} from "lucide-react";
import { Button } from "@/components/atoms/button";
const items = [
  { href: "/start", label: "Overview", icon: House },
  { href: "/communities", label: "Communities", icon: Building2 },
  { href: "/users", label: "Users", icon: Users },
  { href: "/memberships", label: "Memberships", icon: UserRoundCheck },
  { href: "/kitchens", label: "Kitchens", icon: ChefHat },
  { href: "/orders", label: "Orders", icon: ClipboardList },
];
export function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  return (
    <>
      <div className="border-b px-4 py-2 lg:hidden">
        <Button
          variant="outline"
          size="sm"
          aria-controls="admin-navigation"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {open ? <X /> : <Menu />} Navigation
        </Button>
      </div>
      <aside
        id="admin-navigation"
        className={`${open ? "block" : "hidden"} border-b bg-card p-4 lg:block lg:w-56 lg:shrink-0 lg:border-b-0 lg:border-r`}
      >
        <nav aria-label="Administration" className="space-y-1">
          {items.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                onClick={() => setOpen(false)}
                className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm ${active ? "bg-muted font-medium" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}
              >
                <item.icon className="size-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
    </>
  );
}

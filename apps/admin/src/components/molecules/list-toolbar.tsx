import { Search } from "lucide-react";
import { Input } from "@/components/atoms/input";
export function ListToolbar({
  search,
  onSearch,
  children,
}: {
  search: string;
  onSearch: (value: string) => void;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="relative w-full sm:max-w-xs">
        <Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" aria-hidden />
        <Input
          aria-label="Search"
          placeholder="Search…"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          className="pl-9"
        />
      </div>
      {children}
    </div>
  );
}

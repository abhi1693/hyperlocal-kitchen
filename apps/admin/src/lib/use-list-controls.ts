"use client";
import { useEffect, useState } from "react";
export function useListControls() {
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    const timer = setTimeout(() => setQ(search.trim()), 250);
    return () => clearTimeout(timer);
  }, [search]);
  return {
    search,
    q,
    offset,
    setOffset,
    onSearch: (value: string) => {
      setSearch(value);
      setOffset(0);
    },
    params: { q, offset, limit: 30 },
  };
}

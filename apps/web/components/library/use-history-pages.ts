"use client";
import { useEffect, useRef, useState } from "react";
import { LibraryError, readJSON } from "./api";
import type { Page } from "./types";

// Mount this hook in a component keyed by resource/revision; no page can outlive its owner.
export function useHistoryPages<T extends { id: string }>(path: string, initial: Page<T> | null, onUnavailable: (error: LibraryError) => void) {
  const [page, setPage] = useState(initial);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const active = useRef(false); const pending = useRef(false);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  async function load() {
    if (pending.current) return;
    pending.current = true; setLoading(true); setError("");
    try {
      const result = await readJSON<Page<T>>(`${path}${page?.next_cursor ? `?cursor=${encodeURIComponent(page.next_cursor)}` : ""}`);
      if (!active.current) return;
      if (!Array.isArray(result?.items)) throw new LibraryError(502, "记录暂不可读取，请重试。");
      setPage(previous => ({ items: [...(previous?.items ?? []), ...result.items.filter(item => !previous?.items.some(old => old.id === item.id))], next_cursor: result.next_cursor ?? null }));
    } catch (failure) {
      if (!active.current) return;
      if (failure instanceof LibraryError && [401, 403, 404].includes(failure.status)) onUnavailable(failure);
      setError((failure as Error).message);
    } finally { pending.current = false; if (active.current) setLoading(false); }
  }
  return { page, loading, error, load };
}

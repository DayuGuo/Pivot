"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { LibraryError, readJSON } from "./api";
import type { DocumentImportItem } from "./types";
import styles from "./library.module.css";

export default function ImportHistory({ dossierId, revision, onUnavailable }: { dossierId: string; revision: number; onUnavailable: (error: LibraryError) => void }) {
  const [items, setItems] = useState<DocumentImportItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const active = useRef(true);
  const pending = useRef(false);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  async function load() {
    if (pending.current) return;
    pending.current = true; setLoading(true); setError("");
    try {
      const result = await readJSON<{ items: DocumentImportItem[] }>(`/api/dossiers/${encodeURIComponent(dossierId)}/imports`);
      if (!active.current) return;
      if (!Array.isArray(result.items)) throw new LibraryError(502, "导入记录暂不可读取，请重试。");
      setItems(result.items);
    } catch (failure) {
      if (!active.current) return;
      if (failure instanceof LibraryError && [401, 403, 404].includes(failure.status)) onUnavailable(failure);
      setError((failure as Error).message);
    } finally { pending.current = false; if (active.current) setLoading(false); }
  }
  return <details className={styles.importHistory} onToggle={event => { if (event.currentTarget.open && items === null && !loading && !error) void load(); }}><summary>导入记录</summary>
    {loading && <p role="status">正在读取导入记录…</p>}
    {error && <div><p role="alert">{error}</p><button type="button" disabled={loading} onClick={() => void load()}>重试导入记录</button></div>}
    {items?.length === 0 && <p className={styles.hint}>尚未导入 PDF 或 Word 稿件。</p>}
    {items?.map(item => <Link key={item.id} href={`/library/imports/${item.id}?dossier=${dossierId}`}><strong>{item.filename}</strong><span>{item.confirmed_version_id ? "已导入" : item.base_revision === revision ? "待核对" : "待核对 · 当前资料已更新"}</span><small>{new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.created_at))}</small></Link>)}
  </details>;
}

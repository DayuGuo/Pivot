"use client";

import { useEffect, useRef, useState } from "react";
import { LibraryError, readJSON } from "./api";
import type { Dossier, Session } from "./types";
import styles from "./library.module.css";

export default function MetadataExport({ detail, session, onDenied }: {
  detail: Dossier; session: Session; onDenied: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const mounted = useRef(true);
  const lock = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function authorize() {
    const actual = await readJSON<Session>("/api/publishing/session");
    if (actual.user.id !== session.user.id || actual.journal.id !== session.journal.id || actual.user.role !== session.user.role || actual.csrf_token !== session.csrf_token) throw new LibraryError(401, "登录身份已变化，请重新载入资料后导出。");
  }
  async function download() {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError("");
    try {
      await authorize();
      if (!mounted.current) return;
      const value = await readJSON<{ schema: string; dossier_id: string; version_id: string; content_digest: string }>(`/api/dossiers/${detail.id}/versions/${detail.version_id}/metadata-export`);
      await authorize();
      if (!mounted.current) return;
      if (value.schema !== "dossier-metadata-export.v1" || value.dossier_id !== detail.id || value.version_id !== detail.version_id || value.content_digest !== detail.content_digest) throw new LibraryError(409, "导出与当前显示的版本不一致，请重新载入。");
      const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json;charset=utf-8" }));
      const link = document.createElement("a"); link.href = url; link.download = `pivot-metadata-${detail.version_id}.json`; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) {
      if (!mounted.current) return;
      if (failure instanceof LibraryError && [401, 403, 404].includes(failure.status)) { onDenied(); return; }
      setError((failure as Error).message);
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <><button type="button" disabled={busy} onClick={() => void download()}>{busy ? "正在导出…" : "导出资料与缺项"}</button>{error && <p className={styles.fieldError} role="alert">{error}</p>}</>;
}

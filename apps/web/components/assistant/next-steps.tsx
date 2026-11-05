"use client";
import { useEffect, useRef, useState } from 'react';
import styles from './next-steps.module.css';

type Hint = { id: string; label: string; prompt: string; reason: string };
type Context = { objectId: string | null; versionId: string | null; revision: number | null; role: string };
type Hints = { schema: string; object_id: string | null; version_id: string | null; revision: number | null; role: string; suggestions: Hint[] };
type Props = Context & { url: string; disabled: boolean; onChoose: (prompt: string) => void };

function matches(data: unknown, context: Context): data is Hints {
  if (!data || typeof data !== 'object') return false;
  const result = data as Partial<Hints>;
  return result.schema === 'next-steps.v1' && result.object_id === context.objectId
    && result.version_id === context.versionId && result.revision === context.revision
    && result.role === context.role && Array.isArray(result.suggestions) && result.suggestions.length <= 3
    && result.suggestions.every(h => h && typeof h.id === 'string' && typeof h.label === 'string'
      && h.label.length > 0 && h.label.length <= 20 && typeof h.reason === 'string'
      && typeof h.prompt === 'string' && h.prompt.length > 0 && h.prompt.length <= 2000);
}

export default function NextSteps({ url, objectId, versionId, revision, role, disabled, onChoose }: Props) {
  const [result, setResult] = useState<Hints | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const alive = useRef(true);
  useEffect(() => {
    let ignore = false;
    alive.current = true;
    fetch(url, { credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(15000) })
      .then(r => { if (!r.ok) throw Error('建议未载入'); return r.json(); })
      .then(data => { if (!ignore && matches(data, { objectId, versionId, revision, role })) setResult(data); })
      // Optional hints cannot block the authorized manuscript or its conversation.
      .catch(() => {});
    return () => { ignore = true; alive.current = false; };
  }, [url, objectId, versionId, revision, role]);

  async function refresh() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(15000) });
      if (!response.ok) throw Error('建议暂不可用，请稍后重新载入。');
      const data = await response.json();
      if (!alive.current) return;
      if (!matches(data, { objectId, versionId, revision, role })) throw Error('稿件版本或身份已变化，请重新载入工作区。');
      setResult(data);
    } catch (e) {
      if (alive.current) { setResult(null); setError((e as Error).message); }
    } finally {
      if (alive.current) setBusy(false);
    }
  }

  if ((!result || !result.suggestions.length) && !error) return null;
  return <aside className={styles.hints} aria-label="下一步建议" aria-busy={busy}>
    <div className={styles.heading}>
      <p aria-live="polite">{error || result?.suggestions[0]?.reason}</p>
      <button type="button" disabled={busy || disabled} aria-label="刷新下一步建议" onClick={() => void refresh()}>{busy ? '载入中…' : '刷新'}</button>
    </div>
    {result && <div className={styles.choices}>{result.suggestions.map(h =>
      <button type="button" key={h.id} disabled={disabled || busy} title={h.reason} onClick={() => onChoose(h.prompt)}>{h.label}</button>)}</div>}
  </aside>;
}

"use client";
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import type { FeedbackContext } from './claim-feedback';
import { LibraryError, readJSON, requireLibrarySession } from './api';
import type { EvaluationOverview } from './evaluation-types';
import styles from './library.module.css';
export default function EvaluationOverviewPanel({ context, answerId, versionId }: {
    context: FeedbackContext;
    answerId: string;
    versionId: string;
}) {
    const [open, setOpen] = useState(false), [data, setData] = useState<EvaluationOverview | null>(null), [code, setCode] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false);
    const alive = useRef(true), running = useRef(false), pending = useRef<{
        code: string;
        id: string;
    } | null>(null);
    const url = `/api/dossiers/${context.dossierId}/answers/${answerId}/evaluations`;
    useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
    function fail(e: unknown) { if (!alive.current)
        return; setError((e as Error).message); if (e instanceof LibraryError && [401, 403, 404].includes(e.status))
        context.onDenied(); }
    async function load() { if (running.current)
        return; running.current = true; setBusy(true); setError(''); try {
        const next = await readJSON<EvaluationOverview>(url);
        if (!alive.current)
            return;
        if (next.version_id !== versionId)
            throw new LibraryError(409, '评价版本不一致，请重新载入');
        setData(next);
    }
    catch (e) {
        fail(e);
    }
    finally {
        running.current = false;
        if (alive.current)
            setBusy(false);
    } }
    async function issue() { if (!data || running.current)
        return; running.current = true; setBusy(true); setError(''); if (pending.current?.code !== code)
        pending.current = { code, id: crypto.randomUUID() }; try {
        await requireLibrarySession(context.session);
        if (!alive.current)
            return;
        const result = await readJSON<{
            id: string;
            version_id: string;
        }>(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': context.session.csrf_token }, body: JSON.stringify({ request_id: pending.current.id, evaluator_code: code, content_digest: data.content_digest }) });
        if (!alive.current)
            return;
        if (!/^[0-9a-f-]{36}$/i.test(result.id) || result.version_id !== versionId)
            throw new LibraryError(502, '未完整收到登记回执；保持代号不变，再次登记以恢复同一请求。');
        setData({ ...data, packages: [...data.packages.filter(p => p.id !== result.id), { id: result.id, evaluator_code: code, latest: null }] });
        pending.current = null;
        setCode('');
        const refreshed = await readJSON<EvaluationOverview>(url);
        if (alive.current && refreshed.version_id === versionId) setData(refreshed);
    }
    catch (e) {
        fail(e);
    }
    finally {
        running.current = false;
        if (alive.current)
            setBusy(false);
    } }
    return <section aria-label="独立评价回传"><button type="button" aria-expanded={open} onClick={() => { setOpen(!open); if (!open && !data)
        void load(); }}>独立评价回传</button>{open && <div className={styles.references}>
 <p className={styles.hint}>v{data?.version_no ?? ''} 的评价代号由负责人指定，不代表身份认证。旧版未登记的下载包不能回传。</p>
 {data && <><ul>{data.packages.map(p => <li key={p.id}><Link href={`/library/evaluation/${p.id}?dossier=${context.dossierId}`}>{p.evaluator_code} · {p.latest ? `已确认第 ${p.latest.return_no} 次` : '下载与核对回传'}</Link></li>)}</ul>
 <form className={styles.form} onSubmit={e => { e.preventDefault(); void issue(); }}><label>评价代号<input name="evaluator-code" autoComplete="off" spellCheck={false} placeholder="例如 reader-a" pattern="[a-z0-9][a-z0-9_-]{0,39}" required maxLength={40} disabled={busy} value={code} onChange={e => { setCode(e.target.value); pending.current = null; }}/></label><button type="submit" disabled={busy}>{busy ? '处理中…' : '登记评价包'}</button></form>
 <h3>已确认评价的分歧</h3><p>{data.summary.confirmed_slots} / {data.summary.registered_slots} 个代号已回传；{data.summary.disputed_claims} 条存在有依据/无依据分歧。</p>
 {data.summary.claims.map(c => <div key={`${c.claim_bucket}:${c.claim_index}`}><p>{c.text}</p><p>有依据 {c.supported} · 无依据 {c.unsupported} · 待核对 {c.uncertain} · 未评价 {c.unanswered}</p><details><summary>查看各代号意见</summary>{c.opinions.map(o => <p key={o.evaluator_code}>{o.evaluator_code}：{o.verdict === 'supported' ? '有依据' : o.verdict === 'unsupported' ? '无依据' : o.verdict === 'uncertain' ? '待核对' : '未评价'} {o.note}</p>)}</details></div>)}<p className={styles.hint}>每个代号仅统计最新确认；不按多数意见自动作出出版决定。</p></>}
 {error && <p role="alert">{error}</p>}<button type="button" disabled={busy} onClick={() => void load()}>刷新分歧汇总</button></div>}</section>;
}

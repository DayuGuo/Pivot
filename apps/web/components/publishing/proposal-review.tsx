"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Snapshot } from "./intake";
import { EditorialSnapshot, editorialConfirmationLabel } from "./decisions";
import ProductionSnapshot, { productionAcknowledgment, productionConfirmationLabel } from "./production-snapshot";
import { StageReviewSummary, confirmationLabel, stageLabels } from "./stage-actions";
import { PeerReviewSnapshot, peerReviewConfirmationLabel, peerReviewAcknowledgment } from "./review-snapshot";
import type { Proposal } from "./types";
import { dateText } from "./types";
import { APIError, usePublishing } from "./workspace";
import styles from "./publishing.module.css";

export default function ProposalReview({ proposalId }: { proposalId: string }) {
  const { session, mutate, refresh, setReviewContext } = usePublishing();
  const [proposal, setProposal] = useState<Proposal | null>(null); const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const [confirmed, setConfirmed] = useState(false); const [stale, setStale] = useState(false);
  const [loading, setLoading] = useState(false); const sequence = useRef(0);
  const activeLoad = useRef<{ id: string; controller: AbortController } | null>(null);
  const load = useCallback(async () => {
    if (activeLoad.current?.id === proposalId) return;
    activeLoad.current?.controller.abort();
    const controller = new AbortController(); const generation = ++sequence.current;
    activeLoad.current = { id: proposalId, controller };
    setLoading(true); setProposal(null); setAcknowledged(false); setConfirmed(false); setStale(false); setError("");
    try {
      const response = await fetch(`/api/publishing/proposals/${encodeURIComponent(proposalId)}`, { cache: "no-store", credentials: "same-origin", signal: controller.signal });
      const body = await response.json();
      if (controller.signal.aborted || generation !== sequence.current) return;
      if (!response.ok) throw new APIError(response.status, typeof body.detail === "string" ? body.detail : "无法读取审核材料，请返回稿件重新准备。");
      setProposal(body); setStale(body.status === "expired"); setConfirmed(body.status === "confirmed");
    } catch (failure) {
      if (controller.signal.aborted || generation !== sequence.current) return;
      setProposal(null); setAcknowledged(false); setError((failure as Error).message);
    } finally {
      if (generation === sequence.current) { activeLoad.current = null; setLoading(false); }
    }
  }, [proposalId]);
  // Restore this immutable server snapshot on route changes.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load(); return () => { sequence.current += 1; activeLoad.current?.controller.abort(); activeLoad.current = null; }; }, [load]);
  useEffect(() => { setReviewContext(proposal?.manuscript_id ?? null); return () => setReviewContext(null); }, [proposal?.manuscript_id, setReviewContext]);
  async function confirm() {
    if (!proposal || proposal.id !== proposalId || !acknowledged || loading || busy || stale) return; setBusy(true); setError("");
    try { await mutate(`/proposals/${proposal.id}/confirmations`, { expected_revision: proposal.base_revision, digest: proposal.digest, acknowledged: true }); setConfirmed(true); await refresh(); await load(); }
    catch (failure) { setError((failure as Error).message); if (failure instanceof APIError && failure.status === 409) setStale(true); if (failure instanceof APIError && [401, 403, 404].includes(failure.status)) { setProposal(null); setAcknowledged(false); } } finally { setBusy(false); }
  }
  const peerLabel = proposal ? productionConfirmationLabel(proposal) ?? editorialConfirmationLabel(proposal) ?? peerReviewConfirmationLabel(proposal) : null;
  const reviewerOperation = proposal?.action_type === "respond_review_invitation" || proposal?.action_type === "submit_review";
  const title = peerLabel ?? (proposal?.action_type === "submit" ? "确认投稿" : proposal?.action_type === "assign_editor" ? "确认分派责任编辑" : proposal?.payload.check ? `${stageLabels[proposal.payload.check.kind] ?? "当前关口"}审核` : "确认业务操作");
  return <section className={styles.panel}><header className={styles.panelHeader}><h1>负责人审核</h1>{proposal && <Link href={`/publishing?manuscript=${proposal.manuscript_id}`}>返回稿件</Link>}</header>{error && <div className={styles.error} role="alert">{error}{!stale && <button onClick={() => void load()} disabled={busy || loading}>重新载入</button>}</div>}{!proposal ? <p role="status">{error ? "材料未载入。请重试或从左侧选择工作。" : "正在载入不可变审核快照…"}</p> : <><div className={styles.reviewHeading}><h2>{proposal.number} · {title}</h2><p>当前负责人：{session.user.name} · 基于修订 {proposal.base_revision}</p><p>有效至 {dateText(proposal.expires_at)}</p></div>{confirmed ? <p className={styles.success} role="status">此操作已由负责人确认，结果已保存。{proposal.confirmation && `确认时间：${dateText(proposal.confirmation.confirmed_at)}`}</p> : stale ? <div className={styles.notice} role="alert">此快照已失效，不能继续确认。请返回稿件检查最新资料并重新准备审核。<Link href={`/publishing?manuscript=${proposal.manuscript_id}`}>返回稿件并重新准备</Link></div> : <p className={styles.notice}>请核对以下完整资料与文件。确认会执行此业务操作；对话中的建议不等于你的确认。</p>}
    <ProductionSnapshot proposal={proposal} />
    <EditorialSnapshot proposal={proposal} />
    <PeerReviewSnapshot proposal={proposal} />
    <StageReviewSummary proposal={proposal} />
    {!reviewerOperation && proposal.payload.version && <Snapshot version={proposal.payload.version} reviewSnapshot />}
    {!reviewerOperation && <details className={styles.section}><summary>完整操作内容与证据</summary><pre className={styles.json}>{JSON.stringify({ payload: proposal.payload, evidence: proposal.evidence }, null, 2)}</pre></details>}<p className={styles.hash}>快照 SHA-256：<code>{proposal.digest}</code></p>
    {!confirmed && !stale && <div className={styles.confirmation}><label className={styles.checkbox}><input type="checkbox" name="human_acknowledgment" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} disabled={busy} />{productionAcknowledgment(proposal) ?? peerReviewAcknowledgment(proposal) ?? "我已核对完整资料、声明和附件，并以当前负责人的身份确认此操作"}</label><button className={styles.primary} disabled={busy || !acknowledged} onClick={() => void confirm()}>{busy ? "正在确认…" : (peerLabel ?? confirmationLabel(proposal))}</button></div>}</>}</section>;
}

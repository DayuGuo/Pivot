"use client";

import type { Proposal } from "./types";
import { dateText } from "./types";
import { ProductionMetadataView, ProofFileView } from "./production";
import styles from "./publishing.module.css";

export function productionConfirmationLabel(proposal: Proposal): string | null {
  if (proposal.action_type === "send_proof") return "确认交作者校样";
  if (proposal.action_type === "confirm_proof") return proposal.payload.proof_response?.outcome === "approve" ? "确认通过本包校样" : "确认要求校样更正";
  if (proposal.action_type === "prepare_local_preview") return "确认生成鉴权本地预览";
  return null;
}

export function productionAcknowledgment(proposal: Proposal): string | null {
  if (proposal.action_type === "send_proof") return "我已核对冻结录用元数据与本次正文校样，并确认交作者校样";
  if (proposal.action_type === "confirm_proof") return "我已核对本包校样与冻结元数据，并确认本人的校样结果";
  if (proposal.action_type === "prepare_local_preview") return "我已核对作者通过的确切校样与冻结元数据，并确认仅生成鉴权本地预览";
  return null;
}

export default function ProductionSnapshot({ proposal }: { proposal: Proposal }) {
  if (!["send_proof", "confirm_proof", "prepare_local_preview"].includes(proposal.action_type)) return null;
  const { proof_package: proof, proof_response: response, preview } = proposal.payload;
  return <section aria-label="校样与本地预览审核"><h2>{productionConfirmationLabel(proposal)}</h2><p className={styles.notice}>校样只更正正文，录用元数据保持冻结；本地预览始终需要登录，不代表正式发表。</p>
    {response && <section className={styles.snapshot}><h3>{response.outcome === "approve" ? "作者通过本包校样" : "作者要求正文更正"}</h3><p className={styles.preserve}>{response.notes || "未附加意见"}</p><p>{"declarations" in response ? response.declarations.proof_reviewed ? "作者已明确声明阅读本包实际校样。" : "尚无作者已阅读校样的声明。" : `作者已于 ${dateText(response.responded_at)} 确认本包校样结果。`}</p><p className={styles.hash}>回应绑定校样包 SHA-256：<code>{response.package_digest}</code></p></section>}
    {proof && <section><h3>固定校样包 {proof.package_no}</h3><ProofFileView file={proof.file} downloadURL={proposal.payload.proof_download_url} /><p className={styles.hash}>校样包 SHA-256：<code>{proof.material_digest}</code></p>{!preview && <ProductionMetadataView metadata={proof.metadata_snapshot} />}</section>}
    {preview && <section><h3>鉴权本地预览</h3><p>引用作者已通过的确切校样与固定元数据，不发送邮件或公开发布。</p><ProofFileView file={preview.file} downloadURL={proposal.payload.proof_download_url} /><ProductionMetadataView metadata={preview.metadata_snapshot} /><p className={styles.hash}>预览 SHA-256：<code>{preview.content_digest}</code></p></section>}
  </section>;
}

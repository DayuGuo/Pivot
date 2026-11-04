import type { Author, MetadataIssue } from "./types";

export function uncertaintyText(reason: string) {
  const labels: Record<string, string> = {
    author_link_missing: "未识别到可确认的作者机构关联，请对照原稿补充。",
    author_link_unresolved: "未取得该字段属于此作者的明确依据，已留空；请对照原稿核对。",
    corresponding_link_unresolved: "未取得此人为通讯作者的明确依据，请由负责人选择。",
    carried_forward: "沿用此前录入的内容，本次原稿未重新识别到；请核对。",
    duplicate_name: "存在同名作者，请核对是否为同一人；系统不自动合并。",
    duplicate_orcid: "同一 ORCID 被填写给多位作者，请修正或清空后再核对。",
    shared_email: "多位作者共用这个邮箱，邮箱相同不能证明身份相同。",
  };
  return labels[reason] ?? "关联依据不足，请对照原稿人工核对。";
}

export function currentAuthorIssues(authors: Author[]): MetadataIssue[] {
  return ([['name', 'duplicate_name'], ['email', 'shared_email'], ['orcid', 'duplicate_orcid']] as const).flatMap(([field, reason]) => {
    const values = authors.map(a => (a[field] || "").replace(/^https?:\/\/(?:www\.)?orcid\.org\//i, "").replace(/\/$/, "").replace(/\s+/g, " ").trim().toLocaleLowerCase());
    return values.flatMap((value, i) => value && values.filter(v => v === value).length > 1 ? [{ field_path: `authors.${i}.${field}`, reason }] : []);
  });
}

export function supportText(status: string, reason?: string) {
  const reasons: Record<string, string> = {
    contradiction: "结论与引文上下文矛盾。", unrelated_evidence: "引文仅主题相关，不能支持该结论。",
    unsupported_detail: "结论包含引文未支持的细节。", qualifier_lost: "结论强化了原文的限定语。",
    causal_upgrade: "结论把关联或可能性升级为因果。", quantity_mismatch: "数字、单位或比较对象与原文不一致。",
    identity_not_authenticated: "来源记录不能证明作者身份已认证。", mixed_claim: "部分分句没有原文支持。",
  };
  return status === "supported" ? "AI 判断引文支持此结论，仍须人工复核。" : status === "not_checked" ? "模拟结果，未运行语义支持检查。" : `${status === "contradicted" ? "与原文矛盾" : "证据不足"}：${reasons[reason || ""] || "暂不作为审阅结论，请核对引文。"}`;
}

export function originalIssueLabel(path: string, authors: Author[]): string {
  const parts = path.split(".");
  if (parts[0] !== "authors") return "原候选资料";
  const position = Number(parts[1]);
  return `原候选作者 ${position + 1}${authors[position]?.name ? `（${authors[position].name}）` : ""}`;
}

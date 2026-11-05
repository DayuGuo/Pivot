export function fieldLabel(path: string) {
  const names: Record<string, string> = { title: "题名", abstract: "摘要", language: "语言", keywords: "关键词", name: "姓名", email: "邮箱", orcid: "ORCID", affiliations: "机构", corresponding: "通讯作者", contributions: "作者贡献", source_note: "来源", article_type: "文章类型（原文）", funding_statement: "基金原文", declarations_text: "声明原文" };
  const parts = path.split(".");
  return parts[0] === "document_metadata" ? names[parts[1]] || "稿件资料" : parts[0] === "authors" && /^\d+$/.test(parts[1] || "") ? `作者 ${Number(parts[1]) + 1} · ${names[parts[2]] || "资料"}` : names[parts[0]] || "候选资料";
}

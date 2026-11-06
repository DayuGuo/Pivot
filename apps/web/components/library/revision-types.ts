export type RevisionMaterialKind = "base" | "revised" | "response";
export type RevisionCitation = {
  kind: RevisionMaterialKind; file_id: string; version_id: string; version_no: number;
  sha256: string; start: number; end: number; quote: string; line_start: number; line_end: number;
  filename: string; download_url: string | null; source_type?: "pasted_text";
  original?: { filename: string; sha256: string; download_url: string; locations: { kind: "pdf_page" | "docx_paragraph"; number: number; start: number; end: number; quote: string }[] };
};
export type RevisionReview = {
  id: string; point_id: string; response_verdict: "addressed" | "not_addressed" | "uncertain";
  implementation_verdict: "changed" | "partial" | "unchanged" | "not_located" | "uncertain";
  editor_verdict: "sufficient" | "follow_up" | "needs_judgment"; reason: string;
  review_no: number; reviewed_by: string; created_at: string;
};
export type RevisionPacket = {
  schema: "dossier-revision-check.v1"; id: string; dossier_id: string; digest: string;
  base_version_id: string; revised_version_id: string; base_version_no: number; revised_version_no: number;
  revision: number; is_current: boolean; created_at: string; created_by: string;
  materials: { base_complete: boolean; revised_complete: boolean; requirements_complete: boolean; response_complete: boolean; response_text: string; source_note: string };
  report: { provider: "mock" | "deepseek"; coverage: Record<RevisionMaterialKind, { read_characters: number; total_characters: number; complete: boolean; source_complete: boolean }>; rows: { point_id: string; status: string; reason: string; point: { text: string; original_context: string }; citations: RevisionCitation[] }[] };
  reviews: Record<string, RevisionReview>; human_feedback_is_not_publication_approval: true;
};
export type RevisionHistoryItem = { id: string; provider: string; point_count: number; is_current: boolean; created_at: string };

export const responseLabels = { addressed: "已回应", not_addressed: "尚未回应", uncertain: "待核对" };
export const implementationLabels = { changed: "已找到相应修改", partial: "部分落实", unchanged: "正文未改", not_located: "尚未定位到修改", uncertain: "材料不足，待核对" };
export const editorLabels = { sufficient: "本项无需进一步处理", follow_up: "需要进一步处理", needs_judgment: "保留判断" };
export const findingLabels: Record<string, string> = { resolved: "修改有证据", explained: "解释但未改动", partial: "部分回应", not_addressed: "尚未回应", uncertain: "证据不足，待核对", not_applicable: "非修改要求，供核对" };
export const materialLabels = { base: "原稿", revised: "修订稿", response: "作者回复" };
export const uuid = (value: unknown): value is string => typeof value === "string" && /^[0-9a-f-]{36}$/i.test(value);
const sha = (value: unknown) => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
function validCitation(value: RevisionCitation) {
  return value && Object.hasOwn(materialLabels, value.kind) && uuid(value.version_id) && typeof value.file_id === "string" && sha(value.sha256) && typeof value.quote === "string" && Number.isSafeInteger(value.start) && Number.isSafeInteger(value.end) && value.start >= 0 && value.end > value.start && Number.isSafeInteger(value.version_no) && value.version_no > 0 && (!value.original || (sha(value.original.sha256) && typeof value.original.download_url === "string" && Array.isArray(value.original.locations) && value.original.locations.every(location => ["pdf_page", "docx_paragraph"].includes(location.kind) && Number.isSafeInteger(location.start) && Number.isSafeInteger(location.end) && location.end > location.start && Number.isSafeInteger(location.number) && location.number > 0 && typeof location.quote === "string")));
}
export function validPacket(value: RevisionPacket, dossierId: string, checkId?: string): boolean {
  return value?.schema === "dossier-revision-check.v1" && uuid(value.id) && value.dossier_id === dossierId && (!checkId || value.id === checkId) && sha(value.digest) && uuid(value.base_version_id) && uuid(value.revised_version_id) && Number.isSafeInteger(value.base_version_no) && Number.isSafeInteger(value.revised_version_no) && typeof value.is_current === "boolean" && typeof value.materials?.response_text === "string" && typeof value.materials.source_note === "string" && ["base_complete", "revised_complete", "requirements_complete", "response_complete"].every(key => typeof value.materials[key as keyof RevisionPacket["materials"]] === "boolean") && ["mock", "deepseek"].includes(value.report?.provider) && value.report.coverage && Object.keys(materialLabels).every(kind => { const coverage = value.report.coverage[kind as RevisionMaterialKind]; return coverage && Number.isSafeInteger(coverage.read_characters) && Number.isSafeInteger(coverage.total_characters) && coverage.read_characters >= 0 && coverage.read_characters <= coverage.total_characters && typeof coverage.complete === "boolean" && typeof coverage.source_complete === "boolean"; }) && Array.isArray(value.report?.rows) && value.report.rows.length > 0 && value.report.rows.length <= 8 && new Set(value.report.rows.map(row => row.point_id)).size === value.report.rows.length && value.report.rows.every(row => /^P0[1-8]$/.test(row.point_id) && typeof row.point?.text === "string" && typeof row.point.original_context === "string" && typeof row.reason === "string" && Object.hasOwn(findingLabels, row.status) && Array.isArray(row.citations) && row.citations.every(validCitation)) && !!value.reviews && !Array.isArray(value.reviews) && Object.entries(value.reviews).every(([pointId, review]) => validReview(review, pointId)) && value.human_feedback_is_not_publication_approval === true;
}
export function validReview(value: RevisionReview, pointId: string) {
  return uuid(value?.id) && value.point_id === pointId && Object.hasOwn(responseLabels, value.response_verdict) && Object.hasOwn(implementationLabels, value.implementation_verdict) && Object.hasOwn(editorLabels, value.editor_verdict) && typeof value.reason === "string" && Number.isSafeInteger(value.review_no) && value.review_no > 0;
}

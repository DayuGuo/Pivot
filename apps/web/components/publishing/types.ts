export type Author = { name: string; email: string; orcid: string | null; affiliations: string[]; corresponding: boolean; contributions: string[] };
export type IntakeData = {
  title: string; abstract: string; language: "zh" | "en"; article_type: "research_article";
  keywords: string[]; authors: Author[]; funding_statement: string;
  declarations: { originality: boolean; copyright: boolean; competing_interests: "unanswered" | "none" | "declared"; competing_interests_text: string; ethics: "unanswered" | "not_applicable" | "approved"; ethics_reference: string };
};
export type ModelStatus = { provider: string; model?: string; available?: boolean; error_code?: string };
export type PublishingSession = { user: { id: string; name: string; email: string; role: string }; journal: { id: string; name: string }; csrf_token: string; model: ModelStatus; email_send_enabled: false; synthetic_only: true };
export type Task = { id: string; manuscript_id: string; number: string; title: string; kind: string; label: string; status: string; due_at: string | null; priority: number; blocking: boolean; version_id: string | null };
export type AllowedAction = { action: string; label: string; requires_human: boolean };
export type Summary = { id: string; number: string; title: string; stage: string; stage_label: string; revision: number; is_legacy: boolean; is_owner: boolean; capabilities: string[]; current_version_id: string | null; draft_version_id: string | null; accepted_version_id: string | null; own_tasks: Task[]; created_at: string; submitted_at: string | null; allowed_actions?: AllowedAction[] };
export type VersionFile = { id: string; purpose: string; visibility: string; name: string; sha256: string; byte_size: number; media_type: string; check_method: string; scan_status: string; download_url: string };
export type Version = { id: string; version_no: number; data: IntakeData; files: VersionFile[]; frozen_at: string | null; provenance: string };
export type Detail = Summary & { versions: { id: string; version_no: number; title: string; frozen_at: string | null; provenance: string }[]; version: Version | null; missing: { field: string; message: string }[]; can_edit_intake: boolean; field_sources: Record<string, unknown>; timeline: { id: string; step: string; label: string; status: string; cycle: number; completed_at: string | null }[]; allowed_actions: AllowedAction[] };
export type Workspace = { submissions: Summary[]; tasks: Task[]; counts: { actionable: number; waiting: number }; synthetic_only: true };
export type Proposal = { id: string; manuscript_id: string; number: string; action_type: string; digest: string; base_revision: number; payload: { action: string; stage: string; version: Version; schema_version: number; synthetic_only: boolean; [key: string]: unknown }; evidence: Record<string, unknown>; created_at: string; expires_at: string; status: "pending" | "expired" | "confirmed"; confirmation: { id: string; outcome: string; confirmed_at: string } | null };
export type ChatMessage = { id: string; role: "user" | "assistant"; content: string; created_at: string; provider: string; context?: { manuscript_id?: string | null; version_id?: string | null }; references: { label: string; manuscript_id: string; version_id?: string; file_id?: string; quote?: string }[]; tool_receipts: { tool: string; status: string; manuscript_id?: string }[]; action: null | { type: "select"; manuscript_id: string } | { type: "review"; proposal_id: string; manuscript_id: string } };
export function fileURL(file: VersionFile): string | undefined { return /^\/api\/publishing\/files\/[0-9a-f-]{36}$/.test(file.download_url) ? file.download_url : undefined; }
export const roleLabels: Record<string, string> = { author: "作者", editor: "编辑", chief_editor: "主编", reviewer: "审稿人", production_editor: "出版编辑" };
export const purposeLabels: Record<string, string> = { manuscript: "完整稿件", blinded_manuscript: "匿名稿件", response: "修回说明", similarity_report: "查重报告", proof: "校样" };
export function dateText(value: string | null) { return value ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—"; }

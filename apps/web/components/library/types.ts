export type Session = {
  user: { id: string; name: string; email: string; role: string };
  journal: { id: string; name: string };
  csrf_token: string;
};
export type Author = { name: string; email: string; orcid: string | null; affiliations: string[]; corresponding: boolean; contributions?: string[]; source_note: string };
export type DossierData = { title: string; abstract: string; language: "zh" | "en"; keywords: string[]; authors: Author[]; source_kind: "synthetic" | "public_authorized"; source_note: string };
export type DossierItem = { id: string; title: string; revision: number; version_id: string; version_no: number; verified: boolean; updated_at: string };
export type Citation = {
  source_id: string; kind: "text" | "metadata"; quote: string; source_text: string; label: string;
  version_id: string; version_no: number; content_digest: string; file_sha256: string | null;
  start: number; end: number; line_start: number | null; line_end: number | null; field_path: string | null;
  document?: { origin_digest: string; sha256: string; filename: string; media_type: string; download_url: string; locations: DocumentLocation[]; source_start?: number; source_end?: number; source_quote?: string };
};
export type DocumentLocation = { kind: "pdf_page" | "docx_paragraph"; number: number; start: number; end: number };
export type DocumentSegment = DocumentLocation & { text: string; part?: string };
export type DossierDocument = {
  import_id: string; filename: string; media_type: string; sha256: string; byte_size: number; download_url: string;
  parser: string; origin_digest: string; segments: DocumentSegment[]; warnings: string[]; approval: { id: string; by: string; at: string };
};
export type DocumentImport = {
  id: string; dossier_id: string; base_revision: number; base_version_id: string; digest: string;
  filename: string; media_type: string; byte_size: number; sha256: string; original_download_url: string; parser: string;
  text: string; segments: DocumentSegment[]; warnings: string[]; proposed_data: DossierData;
  field_sources: { field_path: string; value: unknown; quote: string; start: number; end: number; kind: DocumentLocation["kind"]; number: number }[];
  metadata_provider: "deepseek" | "mock"; metadata_model: string; telemetry: unknown[];
  confirmed_version_id: string | null; editable: boolean;
};
export type DocumentImportItem = { id: string; filename: string; created_at: string; confirmed_version_id: string | null; base_revision: number };
export type ExternalReference = {
  status: "verified_metadata"; doi: string; title: string; authors: string[]; year: number | null;
  url: string; source_url: string; retrieved_at: string; scope: "bibliographic_metadata_only";
};
export type Coverage = { total_chunks: number; read_chunks: number; total_characters: number; read_characters: number; complete: boolean; fulltext_available?: boolean };
export type ModelStatus = { provider: "deepseek" | "mock" | "unavailable"; model: string; ready: boolean };
export type Message = {
  id: string; question: string; answer: string; provider: "rules" | "deepseek" | "mock"; version_id: string; version_no: number;
  model?: string; claims?: { text: string; citations: Citation[] }[]; questions?: string[]; external_references?: ExternalReference[]; coverage?: Coverage;
};
export type Dossier = {
  id: string; revision: number; version_id: string; version_no: number; content_digest: string; is_current: boolean; verified: boolean;
  verification: null | { id: string; by: string; at: string };
  data: DossierData;
  file: null | { filename: string; sha256: string; byte_size: number; media_type: string; text: string; download_url: string };
  missing: { field: string; message: string }[];
  versions: { id: string; number: number; title: string; created_at: string; verified: boolean }[];
  messages: Message[];
  model?: ModelStatus;
  document?: DossierDocument | null;
};
export type Upload = { filename: string; content_base64: string };

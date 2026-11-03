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
};
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
};
export type Upload = { filename: string; content_base64: string };

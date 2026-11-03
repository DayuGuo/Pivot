export type Session = {
  user: { id: string; name: string; email: string; role: string };
  journal: { id: string; name: string };
  csrf_token: string;
};
export type Author = { name: string; email: string; orcid: string | null; affiliations: string[]; corresponding: boolean; contributions?: string[]; source_note: string };
export type DossierData = { title: string; abstract: string; language: "zh" | "en"; keywords: string[]; authors: Author[]; source_kind: "synthetic" | "public_authorized"; source_note: string };
export type DossierItem = { id: string; title: string; revision: number; version_id: string; version_no: number; verified: boolean; updated_at: string };
export type Message = { id: string; question: string; answer: string; provider: "rules"; version_id: string; version_no: number };
export type Dossier = {
  id: string; revision: number; version_id: string; version_no: number; content_digest: string; is_current: boolean; verified: boolean;
  verification: null | { id: string; by: string; at: string };
  data: DossierData;
  file: null | { filename: string; sha256: string; byte_size: number; media_type: string; text: string; download_url: string };
  missing: { field: string; message: string }[];
  versions: { id: string; number: number; title: string; created_at: string; verified: boolean }[];
  messages: Message[];
};
export type Upload = { filename: string; content_base64: string };

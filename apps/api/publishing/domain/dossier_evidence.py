"""Deterministic full-document indexing and exact, version-bound quotation checks."""

import re
from dataclasses import dataclass

from packages.model_gateway.gateway import GatewayError
from packages.review_sources import normalize_doi

CHUNK_SIZE = 1200
READ_CHARACTERS = 32000
KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s<>\"\u3000\u3002\uff0c\uff1b]+", re.I)


def credential_like(value: str) -> bool:
    return bool(KEY_PATTERN.search(value))


def leaf_fields(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaf_fields(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from leaf_fields(child, f"{path}.{index}")
    elif isinstance(value, str) and value.strip():
        yield path, value
    elif type(value) is bool:
        yield path, "true" if value else "false"


def source_label(path: str | None):
    labels = {
        "title": "题名",
        "abstract": "摘要",
        "language": "语言",
        "source_kind": "资料类型",
        "source_note": "资料来源",
        "name": "姓名",
        "email": "邮箱",
        "orcid": "ORCID",
        "corresponding": "通讯作者标记",
        "affiliations": "机构",
        "contributions": "贡献",
        "keywords": "关键词",
    }
    if path is None:
        return "完整正文"
    parts = path.split(".")
    if parts[0] == "authors" and len(parts) >= 3:
        return f"作者{int(parts[1]) + 1} · {labels.get(parts[2], parts[2])}"
    return labels.get(parts[0], parts[0])


@dataclass(frozen=True)
class Source:
    source_id: str
    kind: str
    text: str
    label: str
    start: int
    end: int
    field_path: str | None
    line_start: int | None
    line_end: int | None

    def projection(self):
        return vars(self).copy()


class EvidenceIndex:
    def __init__(self, data: dict, text: str | None, question: str):
        self.sources: dict[str, Source] = {}
        self.issued: dict[str, Source] = {}
        self.text = text
        self.fields = dict(leaf_fields(data))
        for path, value in self.fields.items():
            self._split("metadata", value, path)
        if text is not None:
            self._split("text", text, None)
        self.units = list(self.sources.values())
        material = "\n".join([question, text or "", *self.fields.values()])
        self.has_credentials = credential_like(material)
        self.allowed_dois = set()
        for match in DOI_PATTERN.finditer(material):
            raw = match.group().rstrip(".,;:!?)\uff09\u3011]")
            value = normalize_doi(raw)
            if value:
                self.allowed_dois.add(value)

    def _split(self, kind: str, value: str, path: str | None):
        start = 0
        while start < len(value):
            end = min(len(value), start + CHUNK_SIZE)
            if end < len(value):
                split = value.rfind("\n", start + CHUNK_SIZE // 2, end)
                if split != -1:
                    end = split + 1
            identifier = f"S{len(self.sources) + 1:05d}"
            self.sources[identifier] = Source(
                identifier,
                kind,
                value[start:end],
                source_label(path),
                start,
                end,
                path,
                value.count("\n", 0, start) + 1 if kind == "text" else None,
                value.count("\n", 0, max(start, end - 1)) + 1 if kind == "text" else None,
            )
            start = end

    def coverage(self):
        return {
            "total_chunks": len(self.sources),
            "read_chunks": len(self.issued),
            "total_characters": sum(len(s.text) for s in self.units),
            "read_characters": sum(len(s.text) for s in self.issued.values()),
            "complete": len(self.sources) == len(self.issued),
            "fulltext_available": self.text is not None,
        }

    def issue(self, sources):
        result, size = [], 0
        for source in sources:
            if size + len(source.text) > READ_CHARACTERS:
                break
            self.issued[source.source_id] = source
            result.append(source.projection())
            size += len(source.text)
        return {"sources": result, "coverage": self.coverage()}

    def read(self, start_chunk=0, count=32):
        return self.issue(self.units[start_chunk : start_chunk + count])

    def search(self, query: str):
        terms = set(re.findall(r"[a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{1,}", query.lower()))
        # CJK bigrams support questions whose phrasing differs from paragraph wording.
        terms |= {
            term[i : i + 2] for term in tuple(terms) if len(term) > 2 for i in range(len(term) - 1)
        }
        scored = [
            (sum(min(s.text.lower().count(t), 5) for t in terms), i, s)
            for i, s in enumerate(self.units)
        ]
        best = sorted((item for item in scored if item[0] > 0), key=lambda x: (-x[0], x[1]))[:12]
        return self.issue([item[2] for item in best])

    def citation(self, source_id, quote, *, version_id, version_no, content_digest, file_sha256):
        source = self.issued.get(source_id)
        if not source or not quote.strip() or quote not in source.text:
            raise GatewayError("dossier_evidence_invalid")
        if source.kind == "text" and len(quote.strip()) < 8:
            raise GatewayError("dossier_evidence_invalid")
        start = source.start + source.text.index(quote)
        end = start + len(quote)
        return {
            "source_id": source_id,
            "kind": source.kind,
            "quote": quote,
            "source_text": source.text,
            "label": source.label,
            "version_id": version_id,
            "version_no": version_no,
            "content_digest": content_digest,
            "file_sha256": file_sha256 if source.kind == "text" else None,
            "start": start,
            "end": end,
            "field_path": source.field_path,
            "line_start": self.text.count("\n", 0, start) + 1 if source.kind == "text" else None,
            "line_end": self.text.count("\n", 0, max(start, end - 1)) + 1
            if source.kind == "text"
            else None,
        }

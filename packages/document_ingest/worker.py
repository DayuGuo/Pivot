"""Executed by a fixed Python subprocess, with no inherited service environment."""

import io
import json
import logging
import posixpath
import resource
import stat
import sys
import unicodedata
import zipfile
from urllib.parse import urlsplit

# Apply bounds before importing the third-party parsers, not in preexec_fn of a
# multithreaded API. These are resource controls, not an OS sandbox.
MEMORY = 512 * 1024 * 1024
resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
resource.setrlimit(resource.RLIMIT_FSIZE, (6 * 1024 * 1024, 6 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))

from defusedxml import ElementTree as ET  # noqa: E402
from pypdf import PdfReader  # noqa: E402
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject  # noqa: E402

logging.disable(logging.CRITICAL)
MAX_BYTES = 5 * 1024 * 1024
MAX_TEXT = 1024 * 1024
MAX_XML = 4 * 1024 * 1024
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


class Rejected(Exception):
    pass


def prohibit_external_effects(event, args):
    if event.startswith("socket.") or event in {
        "subprocess.Popen",
        "os.system",
        "os.fork",
        "os.posix_spawn",
        "os.exec",
    }:
        raise Rejected("document_active_content")


sys.addaudithook(prohibit_external_effects)


def clean_text(value):
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if "\ufffd" in value or any(unicodedata.category(c) == "Cc" and c not in "\t\n" for c in value):
        raise Rejected("document_text_incomplete")
    if any(c in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069" for c in value):
        raise Rejected("document_text_incomplete")
    return value


def result(parts, kind, parser, warnings):
    if not parts:
        raise Rejected("document_text_missing")
    if len(parts) > 5000:
        raise Rejected("document_text_limit")
    text, segments, size, cursor = [], [], 0, 0
    for index, (value, part) in enumerate(parts):
        value = clean_text(value)
        if not value:
            raise Rejected("document_text_missing")
        size += len(value.encode("utf-8")) + (2 if index else 0)
        if size > MAX_TEXT:
            raise Rejected("document_text_limit")
        if index:
            cursor += 2
        segment = {
            "kind": kind,
            "number": index + 1,
            "start": cursor,
            "end": cursor + len(value),
            "text": value,
        }
        if part:
            segment["part"] = part
        text.append(value)
        segments.append(segment)
        cursor = segment["end"]
    return {
        "text": "\n\n".join(text),
        "segments": segments,
        "parser": parser,
        "warnings": sorted(set(warnings)),
        "page_count": len(parts) if kind == "pdf_page" else None,
        "paragraph_count": len(parts) if kind == "docx_paragraph" else None,
    }


def check_pdf_graph(reader):
    seen = set()
    count = 0

    def walk(value, depth=0):
        nonlocal count
        if depth > 100:
            raise Rejected("document_resource_limit")
        if isinstance(value, IndirectObject):
            key = (value.idnum, value.generation)
            if key in seen:
                return
            seen.add(key)
            value = value.get_object()
        if not isinstance(value, (DictionaryObject, ArrayObject)):
            return
        marker = id(value)
        if marker in seen:
            return
        seen.add(marker)
        count += 1
        if count > 10000:
            raise Rejected("document_resource_limit")
        if isinstance(value, DictionaryObject):
            banned = {
                "/JavaScript",
                "/JS",
                "/AA",
                "/OpenAction",
                "/EmbeddedFiles",
                "/EF",
                "/AF",
                "/AcroForm",
                "/XFA",
                "/RichMediaContent",
                "/RichMediaSettings",
            }
            if banned.intersection(value) or value.get("/Subtype") in {
                "/FileAttachment",
                "/RichMedia",
            }:
                raise Rejected("document_active_content")
            if value.get("/S") in {
                "/JavaScript",
                "/Launch",
                "/SubmitForm",
                "/ImportData",
                "/GoToR",
                "/GoToE",
            }:
                raise Rejected("document_active_content")
            for child in value.values():
                walk(child, depth + 1)
        else:
            for child in value:
                walk(child, depth + 1)

    walk(reader.trailer)


def pdf(raw):
    reader = PdfReader(io.BytesIO(raw), strict=True)
    if reader.is_encrypted:
        raise Rejected("document_encrypted")
    if not 1 <= len(reader.pages) <= 60:
        raise Rejected("document_page_limit")
    check_pdf_graph(reader)
    parts = []
    warnings = [
        "pdf_text_reading_order_requires_review",
        "figures_images_and_equations_not_interpreted",
    ]
    for page in reader.pages:
        value = page.extract_text(extraction_mode="plain")
        if not value or not value.strip():
            raise Rejected("document_text_missing")
        parts.append((value, None))
    return result(parts, "pdf_page", "pypdf-6.21.4-text-v1", warnings)


def xml(data):
    if len(data) > MAX_XML:
        raise Rejected("document_archive_limits")
    try:
        return ET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except Exception:
        raise Rejected("document_xml_invalid") from None


def paragraph_text(paragraph):
    output = []
    for node in paragraph.iter():
        if node.tag == W + "t":
            output.append(node.text or "")
        elif node.tag == W + "tab":
            output.append("\t")
        elif node.tag in {W + "br", W + "cr"}:
            output.append("\n")
    return "".join(output)


def docx(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if not 1 <= len(entries) <= 500:
            raise Rejected("document_archive_limits")
        names, total = set(), 0
        for entry in entries:
            name = entry.filename
            if (
                not name
                or name.startswith(("/", "\\"))
                or "\\" in name
                or ":" in name
                or any(p in {".", ".."} for p in name.split("/"))
                or any(unicodedata.category(c).startswith("C") for c in name)
            ):
                raise Rejected("document_archive_invalid")
            lowered = name.lower()
            if (
                lowered in names
                or stat.S_ISLNK(entry.external_attr >> 16)
                or entry.flag_bits & 1
                or entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
            ):
                raise Rejected("document_archive_invalid")
            names.add(lowered)
            total += entry.file_size
            if (
                entry.file_size > 10 * 1024 * 1024
                or total > 20 * 1024 * 1024
                or (entry.file_size > 65536 and entry.file_size > max(entry.compress_size, 1) * 100)
            ):
                raise Rejected("document_archive_limits")
            if (
                lowered.endswith(".bin")
                or "/embeddings/" in lowered
                or "vbaproject" in lowered
                or lowered.endswith(".docm")
            ):
                raise Rejected("document_active_content")
        if not {"[content_types].xml", "_rels/.rels", "word/document.xml"} <= names:
            raise Rejected("document_archive_invalid")
        parsed = {}
        for entry in entries:
            if entry.filename.endswith((".xml", ".rels")):
                parsed[entry.filename] = xml(archive.read(entry))
        types = parsed.get("[Content_Types].xml")
        if types is None or any(
            any(
                token in str(n.attrib).lower()
                for token in ("macroenabled", "activex", "vbaproject", "oleobject")
            )
            for n in types
        ):
            raise Rejected("document_active_content")
        overrides = {node.get("PartName"): node.get("ContentType") for node in types}
        if (
            overrides.get("/word/document.xml")
            != "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        ):
            raise Rejected("document_archive_invalid")
        warnings = [
            "docx_paragraph_numbers_are_extraction_order_not_page_numbers",
            "tables_notes_headers_footers_are_linearized",
        ]
        for name, root in parsed.items():
            if name.endswith(".rels"):
                for rel in root:
                    target = rel.get("Target", "")
                    relationship_type = rel.get("Type", "").lower()
                    relationship_name = relationship_type.rsplit("/", 1)[-1]
                    if relationship_name.startswith(
                        ("vba", "activex", "control")
                    ) or relationship_name in {
                        "oleobject",
                        "attachedtemplate",
                        "package",
                        "afchunk",
                    }:
                        raise Rejected("document_active_content")
                    external = rel.get("TargetMode", "").lower() == "external"
                    if (
                        external
                        and rel.tag == REL + "Relationship"
                        and rel.get("Type")
                        == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
                    ):
                        destination = urlsplit(target)
                        scheme = destination.scheme.lower()
                        display_only = (
                            scheme in {"http", "https"} and bool(destination.hostname)
                        ) or (
                            scheme == "mailto" and bool(destination.path) and not destination.netloc
                        )
                        if display_only and not any(
                            unicodedata.category(c).startswith("C") for c in target
                        ):
                            warnings.append("external_hyperlink_targets_ignored")
                            continue
                    if (
                        rel.tag != REL + "Relationship"
                        or external
                        or urlsplit(target).scheme
                        or target.startswith(("/", "\\"))
                        or "\\" in target
                        or posixpath.normpath(target).startswith("../")
                    ):
                        raise Rejected("document_unsafe_relationship")
            for node in root.iter():
                if node.tag in {W + "ins", W + "del", W + "moveFrom", W + "moveTo"}:
                    raise Rejected("document_tracked_changes")
                if node.tag in {W + "object", W + "altChunk", W + "instrText", W + "fldSimple"}:
                    raise Rejected("document_active_content")
                if node.tag == W + "txbxContent":
                    raise Rejected("document_layout_unsupported")
                if node.tag in {W + "drawing", W + "pict"}:
                    warnings.append("docx_images_and_figures_not_interpreted")
                if node.tag == W + "comment":
                    raise Rejected("document_annotations_unsupported")
        document = parsed.get("word/document.xml")
        if document is None or document.tag != W + "document" or document.find(W + "body") is None:
            raise Rejected("document_archive_invalid")
        parts = []
        sources = [("word/document.xml", document)]
        relationships = parsed.get("word/_rels/document.xml.rels")
        targets = (
            {
                rel.get("Id"): (
                    rel.get("Type", ""),
                    posixpath.normpath("word/" + rel.get("Target", "")),
                )
                for rel in relationships
            }
            if relationships is not None
            else {}
        )
        used = {"word/document.xml"}
        for node in document.iter():
            if node.tag in {W + "headerReference", W + "footerReference"}:
                relation = targets.get(node.get(R + "id"))
                if not relation or relation[1] not in parsed:
                    raise Rejected("document_text_incomplete")
                if relation[1] not in used:
                    sources.append((relation[1], parsed[relation[1]]))
                    used.add(relation[1])
        for kind in ("footnote", "endnote"):
            ids = {node.get(W + "id") for node in document.iter(W + kind + "Reference")}
            if not ids:
                continue
            relation = next(
                (pair for pair in targets.values() if pair[0].endswith("/" + kind + "s")), None
            )
            if not relation or relation[1] not in parsed:
                raise Rejected("document_text_incomplete")
            found = set()
            for note in parsed[relation[1]]:
                if note.tag == W + kind and note.get(W + "id") in ids:
                    sources.append((relation[1], note))
                    found.add(note.get(W + "id"))
            if found != ids:
                raise Rejected("document_text_incomplete")
        for name, root in sources:
            for paragraph in root.iter(W + "p"):
                value = paragraph_text(paragraph)
                if value.strip():
                    parts.append((value, name))
        return result(
            parts,
            "docx_paragraph",
            "defusedxml-0.7.1-ooxml-v1",
            warnings,
        )


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        if not 1 <= len(raw) <= MAX_BYTES:
            raise Rejected("document_size_invalid")
        extension = sys.argv[1] if len(sys.argv) == 2 else ""
        if extension == "pdf":
            output = pdf(raw)
        elif extension == "docx":
            output = docx(raw)
        else:
            raise Rejected("document_format_unsupported")
        encoded = json.dumps(output, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > 6 * 1024 * 1024:
            raise Rejected("document_text_limit")
    except Rejected as error:
        encoded = json.dumps({"error": str(error)}).encode()
    except MemoryError:
        encoded = b'{"error":"document_resource_limit"}'
    except Exception:
        encoded = b'{"error":"document_parse_failed"}'
    sys.stdout.buffer.write(encoded)


if __name__ == "__main__":
    main()

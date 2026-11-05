"""Executed by a fixed Python subprocess, with no inherited service environment."""

import io
import json
import logging
import posixpath
import re
import resource
import stat
import sys
import unicodedata
import zipfile
from urllib.parse import unquote, urlsplit

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
from pypdf.generic import (  # noqa: E402
    ArrayObject,
    DictionaryObject,
    FloatObject,
    IndirectObject,
    NameObject,
    NullObject,
    NumberObject,
)

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


def passive_pdf_destination(value):
    """Only an explicit local page/fit array, never an action dictionary or URI."""
    if isinstance(value, IndirectObject):
        value = value.get_object()
    if not isinstance(value, ArrayObject) or len(value) < 2:
        return False
    page = value[0].get_object() if isinstance(value[0], IndirectObject) else value[0]
    arities = {
        "/XYZ": 5,
        "/Fit": 2,
        "/FitH": 3,
        "/FitV": 3,
        "/FitR": 6,
        "/FitB": 2,
        "/FitBH": 3,
        "/FitBV": 3,
    }
    return (
        isinstance(page, DictionaryObject)
        and page.get("/Type") == "/Page"
        and len(value) == arities.get(value[1])
        and all(isinstance(v, (NumberObject, FloatObject, NullObject)) for v in value[2:])
    )


def check_pdf_graph(reader):
    seen = set()
    count = 0
    fonts = []

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
            if (
                value.get("/Subtype") in {"/Type1", "/MMType1", "/TrueType"}
                and value.get("/Encoding") == "/WinAnsiEncoding"
                and "/ToUnicode" not in value
            ):
                fonts.append(value)
            banned = {
                "/JavaScript",
                "/JS",
                "/AA",
                "/EmbeddedFiles",
                "/EF",
                "/AF",
                "/AcroForm",
                "/XFA",
                "/RichMediaContent",
                "/RichMediaSettings",
            }
            if "/OpenAction" in value and not passive_pdf_destination(value["/OpenAction"]):
                raise Rejected("document_active_content")
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
    return fonts


def pdf(raw):
    reader = PdfReader(io.BytesIO(raw), strict=True)
    if reader.is_encrypted:
        raise Rejected("document_encrypted")
    if not 1 <= len(reader.pages) <= 60:
        raise Rejected("document_page_limit")
    fonts = check_pdf_graph(reader)
    parts = []
    warnings = [
        "pdf_text_reading_order_requires_review",
        "figures_images_and_equations_not_interpreted",
    ]
    # PDF WinAnsi differs from Windows CP1252: the unused slots below are
    # bullets, not C1 controls (PDF Reference Appendix D; PDFBOX-1713).
    # Only normalize an explicit WinAnsi font without a ToUnicode override.
    # Validate the entire input graph before changing this in-memory encoding.
    for font in fonts:
        differences = ArrayObject()
        for code in (127, 129, 141, 143, 144, 157):
            differences.extend([NumberObject(code), NameObject("/bullet")])
        font[NameObject("/Encoding")] = DictionaryObject(
            {
                NameObject("/BaseEncoding"): NameObject("/WinAnsiEncoding"),
                NameObject("/Differences"): differences,
            }
        )
    if fonts:
        warnings.append("pdf_winansi_bullet_encoding_normalized")
    if "/OpenAction" in reader.trailer["/Root"]:
        warnings.append("pdf_initial_page_destination_ignored")
    for page in reader.pages:
        value = page.extract_text(extraction_mode="plain")
        if not value or not value.strip():
            raise Rejected("document_text_missing")
        parts.append((value, None))
    return result(parts, "pdf_page", "pypdf-6.21.4-text-v3", warnings)


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


def internal_target(rels_name, target):
    """Resolve OPC part URIs inside the ZIP namespace, never filesystem paths."""
    destination = urlsplit(target)
    if (
        not target
        or destination.scheme
        or destination.netloc
        or destination.query
        or "\\" in target
        or any(unicodedata.category(c).startswith("C") for c in target)
    ):
        raise Rejected("document_unsafe_relationship")
    path = unquote(destination.path)
    if "\\" in path or any(unicodedata.category(c).startswith("C") for c in path):
        raise Rejected("document_unsafe_relationship")
    if rels_name == "_rels/.rels":
        base = ""
    elif "/_rels/" in rels_name and rels_name.endswith(".rels"):
        base = rels_name.rsplit("/_rels/", 1)[0]
    else:
        raise Rejected("document_unsafe_relationship")
    resolved = posixpath.normpath(
        path.lstrip("/") if path.startswith("/") else base + "/" + path if base else path
    )
    if resolved in {"", ".", ".."} or resolved.startswith(("../", "/")):
        raise Rejected("document_unsafe_relationship")
    return resolved


def cached_field_kind(instruction):
    instruction = instruction.strip()
    if re.fullmatch(r"(?:PAGE|NUMPAGES)(?:\s+\\\*\s+[A-Za-z]+)*", instruction, re.I):
        return "pagination"
    match = re.match(r"ADDIN\s+(EN\.(?:CITE(?:\.DATA)?|REFLIST))(?:\s|$)", instruction, re.I)
    if match:
        return "data" if match[1].upper() == "EN.CITE.DATA" else "citation"
    raise Rejected("document_active_content")


def validate_cached_fields(root, warnings):
    """Do not evaluate fields: only accept structured cached pagination/EndNote text."""
    stack = []
    for node in root.iter():
        if node.tag == W + "fldSimple":
            kind = cached_field_kind(node.get(W + "instr", ""))
            if not any((n.text or "").strip() for n in node.iter(W + "t")):
                if kind != "pagination":
                    raise Rejected("document_text_incomplete")
                warnings.append("docx_pagination_not_rendered")
            warnings.append("docx_cached_fields_not_updated")
        elif node.tag == W + "fldChar":
            state = node.get(W + "fldCharType")
            if state == "begin":
                if len(stack) >= 16:
                    raise Rejected("document_resource_limit")
                stack.append({"code": [], "result": False, "visible": False})
            elif state == "separate":
                if not stack or stack[-1]["result"]:
                    raise Rejected("document_active_content")
                cached_field_kind("".join(stack[-1]["code"]))
                stack[-1]["result"] = True
            elif state == "end":
                if not stack:
                    raise Rejected("document_active_content")
                field = stack.pop()
                kind = cached_field_kind("".join(field["code"]))
                if kind != "data" and (not field["result"] or not field["visible"]):
                    raise Rejected("document_text_incomplete")
                warnings.append("docx_cached_fields_not_updated")
            else:
                raise Rejected("document_active_content")
        elif node.tag == W + "instrText":
            if not stack or stack[-1]["result"]:
                raise Rejected("document_active_content")
            stack[-1]["code"].append(node.text or "")
        elif node.tag == W + "t" and stack:
            if any(not f["result"] for f in stack):
                raise Rejected("document_active_content")
            if (node.text or "").strip():
                for field in stack:
                    field["visible"] = True
    if stack:
        raise Rejected("document_text_incomplete")


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
                    if rel.tag != REL + "Relationship" or external:
                        raise Rejected("document_unsafe_relationship")
                    resolved = internal_target(name, target)
                    if resolved not in archive.namelist():
                        raise Rejected("document_unsafe_relationship")
            validate_cached_fields(root, warnings)
            for node in root.iter():
                if node.tag in {W + "ins", W + "del", W + "moveFrom", W + "moveTo"}:
                    raise Rejected("document_tracked_changes")
                if node.tag in {W + "object", W + "altChunk"}:
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
                    internal_target("word/_rels/document.xml.rels", rel.get("Target", "")),
                )
                for rel in relationships
                if rel.get("TargetMode", "").lower() != "external"
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
                if paragraph.find(W + "pPr/" + W + "numPr") is not None:
                    warnings.append("docx_list_markers_not_rendered")
                if value.strip():
                    parts.append((value, name))
        return result(
            parts,
            "docx_paragraph",
            "defusedxml-0.7.1-ooxml-v2",
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

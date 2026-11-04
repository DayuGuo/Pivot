"""No database, credentials or model access. Untrusted bytes go to a bounded worker."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024
MAX_RESULT_BYTES = 6 * 1024 * 1024
WALL_SECONDS = 15
SAFE_CODES = frozenset(
    {
        "document_format_unsupported",
        "document_filename_invalid",
        "document_size_invalid",
        "document_signature_invalid",
        "document_parse_failed",
        "document_parse_timeout",
        "document_resource_limit",
        "document_worker_unavailable",
        "document_encrypted",
        "document_page_limit",
        "document_text_missing",
        "document_text_incomplete",
        "document_text_limit",
        "document_active_content",
        "document_archive_limits",
        "document_archive_invalid",
        "document_unsafe_relationship",
        "document_xml_invalid",
        "document_tracked_changes",
        "document_annotations_unsupported",
        "document_layout_unsupported",
    }
)


class DocumentError(ValueError):
    """Only a fixed code, never parser messages, file contents, names or host paths."""

    def __init__(self, code):
        self.code = code if type(code) is str and code in SAFE_CODES else "document_parse_failed"
        super().__init__(self.code)


def _extension(filename):
    if (
        not isinstance(filename, str)
        or not 1 <= len(filename) <= 255
        or filename != filename.strip()
        or filename in {".", ".."}
        or any(char in filename for char in "/\\:\x00")
        or any(unicodedata.category(char).startswith("C") for char in filename)
        or filename.endswith((".", " "))
        or filename.split(".", 1)[0].upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *[f"COM{i}" for i in range(1, 10)],
            *[f"LPT{i}" for i in range(1, 10)],
        }
    ):
        raise DocumentError("document_filename_invalid")
    extension = Path(filename).suffix.lower()
    if extension not in {".pdf", ".docx"}:
        raise DocumentError("document_format_unsupported")
    return extension[1:]


def _checked_result(result, extension):
    if not isinstance(result, dict):
        raise DocumentError("document_parse_failed")
    if "error" in result:
        raise DocumentError(result["error"])
    expected = {"text", "segments", "parser", "warnings", "page_count", "paragraph_count"}
    if set(result) != expected or not isinstance(result["text"], str):
        raise DocumentError("document_parse_failed")
    text = result["text"]
    if not text.strip() or len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise DocumentError("document_text_limit")
    parser_name = "pypdf-6.21.4-text-v2" if extension == "pdf" else "defusedxml-0.7.1-ooxml-v2"
    if (
        not isinstance(result["segments"], list)
        or not 1 <= len(result["segments"]) <= 5000
        or result["parser"] != parser_name
    ):
        raise DocumentError("document_parse_failed")
    cursor = 0
    for index, segment in enumerate(result["segments"]):
        if not isinstance(segment, dict) or not {"kind", "number", "start", "end", "text"} <= set(
            segment
        ):
            raise DocumentError("document_parse_failed")
        if (
            segment["kind"] != ("pdf_page" if extension == "pdf" else "docx_paragraph")
            or type(segment["number"]) is not int
            or segment["number"] != index + 1
            or type(segment["start"]) is not int
            or segment["start"] != cursor
            or type(segment["end"]) is not int
            or segment["end"] <= cursor
            or type(segment["text"]) is not str
            or text[segment["start"] : segment["end"]] != segment["text"]
        ):
            raise DocumentError("document_parse_failed")
        cursor = segment["end"]
        if index + 1 < len(result["segments"]):
            if text[cursor : cursor + 2] != "\n\n":
                raise DocumentError("document_parse_failed")
            cursor += 2
    if cursor != len(text):
        raise DocumentError("document_parse_failed")
    if not isinstance(result["warnings"], list) or any(
        type(x) is not str or len(x) > 100 for x in result["warnings"]
    ):
        raise DocumentError("document_parse_failed")
    count = len(result["segments"])
    if type(result["page_count"] if extension == "pdf" else result["paragraph_count"]) is not int:
        raise DocumentError("document_parse_failed")
    if (result["page_count"], result["paragraph_count"]) != (
        (count, None) if extension == "pdf" else (None, count)
    ):
        raise DocumentError("document_parse_failed")
    return result


def extract_document(filename: str, raw: bytes) -> dict:
    """Extract locally without OCR. Resource limits are not an OS security sandbox."""
    extension = _extension(filename)
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_DOCUMENT_BYTES:
        raise DocumentError("document_size_invalid")
    if not raw.startswith(b"%PDF-" if extension == "pdf" else b"PK\x03\x04"):
        raise DocumentError("document_signature_invalid")
    worker = Path(__file__).with_name("worker.py").resolve()
    try:
        with (
            tempfile.TemporaryDirectory(prefix="pivot-document-") as cwd,
            tempfile.TemporaryFile() as output,
        ):
            process = subprocess.Popen(
                [sys.executable, "-I", "-B", str(worker), extension],
                stdin=subprocess.PIPE,
                stdout=output,
                stderr=subprocess.DEVNULL,
                cwd=cwd,
                env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC"},
                close_fds=True,
                start_new_session=True,
            )
            try:
                process.communicate(input=raw, timeout=WALL_SECONDS)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                raise DocumentError("document_parse_timeout") from None
            if process.returncode:
                raise DocumentError(
                    "document_resource_limit" if process.returncode < 0 else "document_parse_failed"
                )
            output.seek(0)
            encoded = output.read(MAX_RESULT_BYTES + 1)
            if len(encoded) > MAX_RESULT_BYTES:
                raise DocumentError("document_text_limit")
        parsed = json.loads(encoded)
        result = _checked_result(parsed, extension)
        return result
    except DocumentError:
        raise
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise DocumentError("document_parse_failed") from None

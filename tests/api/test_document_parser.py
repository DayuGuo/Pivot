"""Real local parsers and adversarial containers; all documents are synthetic."""

import io
import json
import subprocess
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject

from packages.document_ingest import DocumentError, extract_document, parser

FIXTURES = Path(__file__).resolve().parents[1] / "documents"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def bytes_for(extension):
    return (FIXTURES / f"synthetic-manuscript.{extension}").read_bytes()


def write_pdf(writer):
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def changed_docx(changes=None, additions=None, delete=()):
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bytes_for("docx"))) as original:
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as output:
            for entry in original.infolist():
                if entry.filename in delete:
                    continue
                value = original.read(entry)
                if changes and entry.filename in changes:
                    value = changes[entry.filename](value)
                output.writestr(entry.filename, value)
            for name, value in (additions or {}).items():
                output.writestr(name, value)
    return buffer.getvalue()


def rejected(raw, extension, code):
    with pytest.raises(DocumentError) as captured:
        extract_document("synthetic." + extension, raw)
    assert captured.value.code == code
    assert str(captured.value) == code


@pytest.mark.parametrize("extension", ["pdf", "docx"])
def test_actual_synthetic_file_has_complete_text_and_exact_source_offsets(extension):
    result = extract_document("synthetic." + extension, bytes_for(extension))
    assert "Synthetic Editorial Review Manuscript" in result["text"]
    assert "Synthetic Author Alpha" in result["text"]
    assert "Synthetic Author Beta" in result["text"]
    assert "alpha@synthetic.test" in result["text"]
    assert "0000-0002-1825-0097" in result["text"]
    assert result["text"].endswith("END-OF-SYNTHETIC-DOCUMENT-TRACE-2026")
    assert result["text"] == "\n\n".join(item["text"] for item in result["segments"])
    for index, segment in enumerate(result["segments"]):
        assert segment["number"] == index + 1
        assert result["text"][segment["start"] : segment["end"]] == segment["text"]
    if extension == "pdf":
        assert result["page_count"] == 2 and result["paragraph_count"] is None
        assert result["segments"][-1]["number"] == 2
        assert "pdf_text_reading_order_requires_review" in result["warnings"]
    else:
        assert result["paragraph_count"] == 23 and result["page_count"] is None
        assert "中文合成正文" in result["text"] and "Synthetic table value" in result["text"]
        assert all(segment["part"] == "word/document.xml" for segment in result["segments"])
        assert "external_hyperlink_targets_ignored" in result["warnings"]


@pytest.mark.parametrize("filename", ["a.doc", "a.docm", "a.txt", "a.odt", "a.zip"])
def test_unsupported_format_is_explicit(filename):
    with pytest.raises(DocumentError, match="^document_format_unsupported$"):
        extract_document(filename, b"synthetic")


@pytest.mark.parametrize(
    "filename",
    [
        "../a.pdf",
        "a/b.pdf",
        "a\\b.docx",
        " a.pdf",
        "a.pdf ",
        "a\x00.pdf",
        "a\u202e.pdf",
        "CON.pdf",
        "a:foo.docx",
        "x" * 260 + ".pdf",
    ],
)
def test_filename_does_not_become_a_path_or_ambiguous_download(filename):
    with pytest.raises(DocumentError, match="^document_filename_invalid$"):
        extract_document(filename, b"synthetic")


@pytest.mark.parametrize("raw", [b"", b"x" * (5 * 1024 * 1024 + 1), bytearray(b"%PDF-test")])
def test_binary_size_and_type_are_bounded_before_worker(raw):
    rejected(raw, "pdf", "document_size_invalid")


@pytest.mark.parametrize(
    "extension,raw",
    [("pdf", b"PK\x03\x04bad"), ("docx", b"%PDF-1.7"), ("pdf", b"<html>bad</html>")],
)
def test_extension_and_magic_must_match(extension, raw):
    rejected(raw, extension, "document_signature_invalid")


def test_encrypted_pdf_is_rejected_without_requesting_a_password():
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(bytes_for("pdf"))))
    writer.encrypt("synthetic-not-a-real-password")
    rejected(write_pdf(writer), "pdf", "document_encrypted")


def test_any_empty_or_scanned_pdf_page_prevents_claiming_complete_extraction():
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(bytes_for("pdf"))))
    writer.add_blank_page(width=595, height=842)
    rejected(write_pdf(writer), "pdf", "document_text_missing")


def test_pdf_page_limit_applies_before_text_extraction():
    writer = PdfWriter()
    for _ in range(61):
        writer.add_blank_page(width=595, height=842)
    rejected(write_pdf(writer), "pdf", "document_page_limit")


@pytest.mark.parametrize("active", ["javascript", "open_action", "file_attachment", "launch"])
def test_active_pdf_features_fail_closed(active):
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(bytes_for("pdf"))))
    if active == "javascript":
        writer.add_js("app.alert('synthetic')")
    elif active == "open_action":
        writer._root_object[NameObject("/OpenAction")] = DictionaryObject(
            {NameObject("/S"): NameObject("/GoTo")}
        )
    elif active == "file_attachment":
        writer.add_attachment("synthetic.txt", b"synthetic attachment")
    else:
        writer.pages[0][NameObject("/A")] = DictionaryObject(
            {NameObject("/S"): NameObject("/Launch")}
        )
    rejected(write_pdf(writer), "pdf", "document_active_content")


@pytest.mark.parametrize(
    "extension,raw", [("pdf", b"%PDF-1.7\nmalformed-data"), ("docx", b"PK\x03\x04malformed-data")]
)
def test_malformed_parser_error_does_not_reflect_input(extension, raw):
    rejected(raw, extension, "document_parse_failed")


@pytest.mark.parametrize(
    "name", ["../evil.xml", "/absolute.xml", "word/../evil.xml", "word\\evil.xml"]
)
def test_docx_zip_paths_are_never_extracted_or_traversed(name):
    rejected(changed_docx(additions={name: b"<x/>"}), "docx", "document_archive_invalid")


@pytest.mark.parametrize(
    "name", ["word/vbaProject.bin", "word/embeddings/oleObject1.bin", "word/evil.docm"]
)
def test_docx_macros_and_embedded_objects_are_rejected(name):
    rejected(changed_docx(additions={name: b"synthetic"}), "docx", "document_active_content")


def test_docx_zip_bomb_is_rejected_before_decompression():
    rejected(
        changed_docx(additions={"word/huge.xml": b"x" * 1000000}), "docx", "document_archive_limits"
    )


def test_docx_entry_count_is_bounded():
    rejected(
        changed_docx(additions={f"synthetic/{i}.xml": b"<x/>" for i in range(501)}),
        "docx",
        "document_archive_limits",
    )


def test_docx_duplicate_entry_is_rejected():
    with pytest.warns(UserWarning, match="Duplicate"):
        raw = changed_docx(additions={"word/document.xml": b"<x/>"})
    rejected(raw, "docx", "document_archive_invalid")


@pytest.mark.parametrize("xml_part", ["word/document.xml", "docProps/core.xml"])
def test_docx_dtd_and_entities_are_rejected_in_all_xml_parts(xml_part):
    malicious = b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///never-read">]><x>&secret;</x>'
    rejected(changed_docx(changes={xml_part: lambda _: malicious}), "docx", "document_xml_invalid")


@pytest.mark.parametrize(
    "kind,target",
    [
        ("attachedTemplate", "https://example.test/template.dotm"),
        ("image", "https://example.test/linked.png"),
        ("oleObject", "file:///secret"),
        ("hyperlink", "javascript:synthetic"),
        ("hyperlink", "file:///secret"),
    ],
)
def test_external_relationships_except_http_hyperlink_fail_closed(kind, target):
    rel = f'<Relationships xmlns="{REL}"><Relationship Id="rIdS" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{kind}" TargetMode="External" Target="{target}"/></Relationships>'.encode()
    rejected(
        changed_docx(additions={"word/_rels/synthetic.xml.rels": rel}),
        "docx",
        "document_active_content"
        if kind in {"attachedTemplate", "oleObject"}
        else "document_unsafe_relationship",
    )


def test_harmless_hyperlink_preserves_display_text_but_never_returns_target():
    target = "https://example.test/UNRETURNED-SYNTHETIC-TARGET"
    rel = f'<Relationships xmlns="{REL}"><Relationship Id="rIdS" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" TargetMode="External" Target="{target}"/></Relationships>'.encode()
    result = extract_document(
        "synthetic.docx", changed_docx(additions={"word/_rels/synthetic.xml.rels": rel})
    )
    assert "10.1371/journal.pmed.0020124" in result["text"]
    assert target not in json.dumps(result)
    assert "external_hyperlink_targets_ignored" in result["warnings"]


@pytest.mark.parametrize(
    "node,code",
    [
        ("ins", "document_tracked_changes"),
        ("del", "document_tracked_changes"),
        ("object", "document_active_content"),
        ("altChunk", "document_active_content"),
        ("instrText", "document_active_content"),
        ("fldSimple", "document_active_content"),
        ("txbxContent", "document_layout_unsupported"),
        ("comment", "document_annotations_unsupported"),
    ],
)
def test_docx_unreviewed_revision_and_unsupported_content_are_explicit(node, code):
    def add(data):
        return data.replace(b"</w:body>", f"<w:{node}/></w:body>".encode())

    rejected(changed_docx(changes={"word/document.xml": add}), "docx", code)


def test_docx_note_and_header_text_are_not_silently_lost():
    parts = {
        "word/footnotes.xml": f'<w:footnotes xmlns:w="{W}"><w:footnote w:id="1"><w:p><w:r><w:t>Included synthetic footnote</w:t></w:r></w:p></w:footnote></w:footnotes>'.encode(),
        "word/header1.xml": f'<w:hdr xmlns:w="{W}"><w:p><w:r><w:t>Included synthetic header</w:t></w:r></w:p></w:hdr>'.encode(),
    }

    def refs(data):
        data = data.replace(b"</w:p>", b'<w:r><w:footnoteReference w:id="1"/></w:r></w:p>', 1)
        return data.replace(
            b"<w:sectPr>",
            b'<w:sectPr><w:headerReference w:type="default" r:id="rIdHeaderSynthetic"/>',
            1,
        )

    def rels(data):
        return data.replace(
            b"</Relationships>",
            b'<Relationship Id="rIdHeaderSynthetic" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/></Relationships>',
        )

    result = extract_document(
        "synthetic.docx",
        changed_docx(
            changes={"word/document.xml": refs, "word/_rels/document.xml.rels": rels},
            additions=parts,
            delete=tuple(parts),
        ),
    )
    assert "Included synthetic footnote" in result["text"]
    assert "Included synthetic header" in result["text"]
    assert {s["part"] for s in result["segments"]} >= set(parts)


def test_docx_extracted_text_limit_has_no_prefix_success():
    text = " ".join(str(i) for i in range(200000))
    xml = f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>'.encode()
    rejected(
        changed_docx(changes={"word/document.xml": lambda _: xml}), "docx", "document_text_limit"
    )


def test_worker_has_minimal_environment_fixed_command_and_no_shell(monkeypatch):
    result = extract_document("synthetic.pdf", bytes_for("pdf"))
    seen = {}

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            seen.update(command=command, **kwargs)
            kwargs["stdout"].write(json.dumps(result).encode())

        def communicate(self, input=None, timeout=None):
            seen.update(input=input, timeout=timeout)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-environment-only")
    monkeypatch.setenv("DATABASE_URL", "synthetic-private-db")
    monkeypatch.setattr(parser.subprocess, "Popen", Process)
    assert extract_document("synthetic.pdf", bytes_for("pdf")) == result
    assert seen["command"][1:3] == ["-I", "-B"]
    assert seen["command"][-1] == "pdf" and "shell" not in seen
    assert seen["env"] == {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC"}
    assert seen["close_fds"] and seen["start_new_session"] and seen["timeout"] == 15


def test_wall_timeout_kills_worker_group_and_returns_fixed_error(monkeypatch):
    killed = []

    class Process:
        pid = 1234567

        def __init__(self, *args, **kwargs):
            self.calls = 0

        def communicate(self, input=None, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("synthetic-worker", timeout)

    monkeypatch.setattr(parser.subprocess, "Popen", Process)
    monkeypatch.setattr(parser.os, "killpg", lambda pid, signal: killed.append((pid, signal)))
    rejected(bytes_for("pdf"), "pdf", "document_parse_timeout")
    assert killed and killed[0][0] == 1234567


def test_parent_rechecks_exact_offsets_instead_of_trusting_worker_json():
    result = extract_document("synthetic.pdf", bytes_for("pdf"))
    for field, value in (("start", 3), ("end", 9999999), ("text", "forged source"), ("number", 44)):
        bad = deepcopy(result)
        bad["segments"][0][field] = value
        with pytest.raises(DocumentError, match="^document_parse_failed$"):
            parser._checked_result(bad, "pdf")


@pytest.mark.parametrize("relationship", ["vbaProject", "oleObject", "package"])
def test_active_internal_relationship_cannot_hide_behind_an_image_filename(relationship):
    rel = f'<Relationships xmlns="{REL}"><Relationship Id="rIdS" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{relationship}" Target="media/innocent.png"/></Relationships>'.encode()
    rejected(
        changed_docx(additions={"word/_rels/synthetic.xml.rels": rel}),
        "docx",
        "document_active_content",
    )


def test_unused_header_or_note_parts_are_not_mistaken_for_visible_manuscript():
    parts = {
        "word/header-unused.xml": f'<w:hdr xmlns:w="{W}"><w:p><w:r><w:t>UNREFERENCED-SYNTHETIC-HIDDEN-TEXT</w:t></w:r></w:p></w:hdr>'.encode()
    }
    result = extract_document("synthetic.docx", changed_docx(additions=parts))
    assert "UNREFERENCED-SYNTHETIC-HIDDEN-TEXT" not in result["text"]


def test_mailto_hyperlink_only_extracts_visible_email_not_target_or_parameters():
    visible = "visible-author@synthetic.test"
    hidden = "hidden-recipient@synthetic.test"
    marker = "SYNTHETIC-IGNORED-MAIL-PARAMETERS"
    target = f"mailto:{hidden}?subject={marker}&amp;body=not-extracted"

    def document(data):
        node = f'<w:p><w:hyperlink r:id="rIdMailSynthetic"><w:r><w:t>{visible}</w:t></w:r></w:hyperlink></w:p>'
        return data.replace(b"</w:body>", node.encode() + b"</w:body>")

    def relationships(data):
        node = f'<Relationship Id="rIdMailSynthetic" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" TargetMode="External" Target="{target}"/>'
        return data.replace(b"</Relationships>", node.encode() + b"</Relationships>")

    result = extract_document(
        "synthetic.docx",
        changed_docx(
            changes={"word/document.xml": document, "word/_rels/document.xml.rels": relationships}
        ),
    )
    assert visible in result["text"]
    serialized = json.dumps(result)
    assert (
        hidden not in serialized and marker not in serialized and "not-extracted" not in serialized
    )
    assert "external_hyperlink_targets_ignored" in result["warnings"]


@pytest.mark.parametrize(
    "target",
    ["mailto://example.test/recipient", "mailto:", "mailto:recipient@synthetic.test&#10;injected"],
)
def test_mailto_does_not_allow_authority_empty_address_or_control_characters(target):
    rel = f'<Relationships xmlns="{REL}"><Relationship Id="rIdS" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" TargetMode="External" Target="{target}"/></Relationships>'.encode()
    rejected(
        changed_docx(additions={"word/_rels/synthetic.xml.rels": rel}),
        "docx",
        "document_unsafe_relationship",
    )


@pytest.mark.parametrize("target", ["../customXml/item1.xml", "/customXml/item1.xml"])
def test_ooxml_part_references_resolve_inside_archive_without_reading_external_paths(target):
    rel = f'<Relationships xmlns="{REL}"><Relationship Id="rInternal" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml" Target="{target}"/></Relationships>'.encode()
    result = extract_document(
        "synthetic.docx",
        changed_docx(
            additions={
                "word/_rels/synthetic.xml.rels": rel,
                "customXml/item1.xml": b"<metadata>UNINDEXED CUSTOM METADATA</metadata>",
            }
        ),
    )
    assert "Synthetic Author Alpha" in result["text"]
    assert "UNINDEXED CUSTOM METADATA" not in result["text"]


@pytest.mark.parametrize(
    "target",
    [
        "../../outside.xml",
        "../../../outside.xml",
        "file:///outside.xml",
        "//example.test/outside.xml",
        "%2e%2e/%2e%2e/outside.xml",
        "../%5coutside.xml",
    ],
)
def test_part_reference_normalization_does_not_escape_the_zip_namespace(target):
    rel = f'<Relationships xmlns="{REL}"><Relationship Id="rInternal" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml" Target="{target}"/></Relationships>'.encode()
    rejected(
        changed_docx(additions={"word/_rels/synthetic.xml.rels": rel}),
        "docx",
        "document_unsafe_relationship",
    )


def field_xml(code, result="[1]", *, close=True):
    from xml.sax.saxutils import escape

    return (
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        f"<w:r><w:instrText>{escape(code)}</w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        f"<w:r><w:t>{escape(result)}</w:t></w:r>"
        + ('<w:r><w:fldChar w:fldCharType="end"/></w:r>' if close else "")
        + "</w:p>"
    ).encode()


@pytest.mark.parametrize(
    "code",
    [
        "ADDIN EN.CITE <EndNote>PRIVATE FIELD DATA</EndNote>",
        "ADDIN EN.REFLIST",
        r"PAGE \* MERGEFORMAT",
        "NUMPAGES",
    ],
)
def test_only_saved_citation_and_pagination_text_is_extracted_never_field_instructions(code):
    result = extract_document(
        "synthetic.docx",
        changed_docx(
            changes={
                "word/document.xml": lambda raw: raw.replace(
                    b"</w:body>", field_xml(code) + b"</w:body>"
                )
            }
        ),
    )
    assert result["text"].endswith("[1]")
    assert code not in result["text"]
    assert "PRIVATE FIELD DATA" not in result["text"]
    assert "docx_cached_fields_not_updated" in result["warnings"]


@pytest.mark.parametrize(
    "code",
    [
        'INCLUDETEXT "file:///never-read"',
        "DDEAUTO cmd /c synthetic",
        'HYPERLINK "https://example.test"',
        "ADDIN unknown",
    ],
)
def test_fields_outside_saved_bibliography_and_pagination_allowlist_still_fail_closed(code):
    rejected(
        changed_docx(
            changes={
                "word/document.xml": lambda raw: raw.replace(
                    b"</w:body>", field_xml(code) + b"</w:body>"
                )
            }
        ),
        "docx",
        "document_active_content",
    )


@pytest.mark.parametrize("result,close", [("", True), ("[1]", False)])
def test_missing_cached_citation_or_unclosed_field_does_not_silently_lose_body_text(result, close):
    rejected(
        changed_docx(
            changes={
                "word/document.xml": lambda raw: raw.replace(
                    b"</w:body>", field_xml("ADDIN EN.CITE", result, close=close) + b"</w:body>"
                )
            }
        ),
        "docx",
        "document_text_incomplete",
    )


def test_endnote_nested_metadata_is_not_mistaken_for_missing_visible_citation():
    field = b'<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText>ADDIN EN.CITE</w:instrText></w:r><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText>ADDIN EN.CITE.DATA</w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>[27]</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    result = extract_document(
        "synthetic.docx",
        changed_docx(
            changes={
                "word/document.xml": lambda raw: raw.replace(b"</w:body>", field + b"</w:body>")
            }
        ),
    )
    assert result["text"].endswith("[27]")
    assert "EN.CITE" not in result["text"]


def test_simple_empty_pagination_reports_not_rendered_without_inventing_word_page_numbers():
    field = b'<w:p><w:fldSimple w:instr="PAGE"/></w:p>'
    result = extract_document(
        "synthetic.docx",
        changed_docx(
            changes={
                "word/document.xml": lambda raw: raw.replace(b"</w:body>", field + b"</w:body>")
            }
        ),
    )
    assert "docx_pagination_not_rendered" in result["warnings"]
    assert result["paragraph_count"] == 23


@pytest.mark.parametrize("mode", ["/Fit", "/XYZ"])
def test_local_pdf_initial_page_destination_is_ignored_without_running_actions(mode):
    from pypdf.generic import ArrayObject, NullObject, NumberObject

    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(bytes_for("pdf"))))
    destination = [writer.pages[0].indirect_reference, NameObject(mode)]
    if mode == "/XYZ":
        destination += [NullObject(), NullObject(), NumberObject(0)]
    writer._root_object[NameObject("/OpenAction")] = ArrayObject(destination)
    result = extract_document("synthetic.pdf", write_pdf(writer))
    assert result["page_count"] == 2
    assert "END-OF-SYNTHETIC-DOCUMENT-TRACE-2026" in result["text"]
    assert "pdf_initial_page_destination_ignored" in result["warnings"]


@pytest.mark.parametrize("code", [127, 129, 141, 143, 144, 157])
def test_pdf_winansi_unused_slots_are_bullets_not_dropped_text(code):
    from pypdf.generic import DecodedStreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(
        b"BT /F1 12 Tf 10 250 Td (" + bytes([code]) + b" Complete synthetic requirement) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    result = extract_document("winansi.pdf", write_pdf(writer))
    assert "\u2022 Complete synthetic requirement" in result["text"]
    assert result["parser"].endswith("-v3")


def test_unknown_control_character_in_non_winansi_font_is_still_rejected():
    from pypdf.generic import DecodedStreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/StandardEncoding"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 250 Td (Untrusted \x01 control) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    with pytest.raises(DocumentError, match="document_text_incomplete"):
        extract_document("not-winansi.pdf", write_pdf(writer))

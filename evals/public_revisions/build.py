"""Build offline CC BY article-only fixtures from previously downloaded publisher bytes.

Original full PDFs/XML stay in ignored research storage: they may contain appended
web comments whose separate reuse terms have not been established. Only licensed
article pages, article revision notes and explicitly CC BY reviewer paragraphs
are retained. Word fixtures are declared conversions, not publisher Word files.
"""

import argparse
import hashlib
import io
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from defusedxml import ElementTree as ET
from pypdf import PdfReader, PdfWriter

from packages.document_ingest import extract_document

CASES = {
    "oath": ("3-271", "10.12688/f1000research.5686"),
    "13-921": ("13-921", "10.12688/f1000research.154614"),
    "13-6": ("13-6", "10.12688/f1000research.143013"),
}
XL = "{http://www.w3.org/1999/xlink}"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"


def compact(value):
    return " ".join(value.split())


def paragraphs(node):
    if node.tag in {"title", "p", "td", "th", "preformat", "mixed-citation", "element-citation"}:
        value = compact("".join(node.itertext()))
        if value:
            yield value
        return
    for child in node:
        yield from paragraphs(child)


def docx(values):
    content = "".join(
        '<w:p><w:r><w:t xml:space="preserve">' + escape(v) + "</w:t></w:r></w:p>" for v in values
    )
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as z:

        def write(name, data):
            entry = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            z.writestr(entry, data)

        write(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        write(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        write(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            + content
            + "</w:body></w:document>",
        )
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research", type=Path, default=Path("artifacts/spec025/public-research"))
    parser.add_argument("--output", type=Path, default=Path("evals/public_revisions"))
    args = parser.parse_args()
    results = []
    for key, (article, doi) in CASES.items():
        folder = args.output / key
        folder.mkdir(parents=True, exist_ok=True)
        record = {
            "id": key,
            "article_url": f"https://f1000research.com/articles/{article}",
            "license_url": LICENSE,
            "versions": {},
            "review_requirements": [],
        }
        for version in [1, 2]:
            original = args.research / f"{key}-v{version}.pdf"
            xml = args.research / f"{key}-v{version}.xml"
            raw = original.read_bytes()
            source_xml = xml.read_bytes()
            root = ET.fromstring(source_xml)
            licenses = root.findall("./front/article-meta/permissions/license")
            assert any(item.get(XL + "href") == LICENSE for item in licenses)
            assert root.find("./front/article-meta/article-id").text == f"{doi}.{version}"
            meta = root.find("./front/article-meta")
            title = compact("".join(meta.find("title-group/article-title").itertext()))
            authors = [
                compact(" ".join(n.itertext()))
                for n in meta.findall("./contrib-group/contrib/name")
            ]
            e = extract_document(original.name, raw)
            appendix = next(
                s["number"]
                for s in e["segments"]
                if re.match(r"^Open Peer Review\s+Current Peer Review Status", s["text"])
            )
            writer = PdfWriter()
            reader = PdfReader(io.BytesIO(raw))
            for page in reader.pages[: appendix - 1]:
                writer.add_page(page, excluded_keys=["/Annots"])
            output = io.BytesIO()
            writer.write(output)
            excerpt = output.getvalue()
            pdf_path = folder / f"v{version}.pdf"
            pdf_path.write_bytes(excerpt)
            parsed = extract_document(pdf_path.name, excerpt)
            assert [s["text"] for s in parsed["segments"]] == [
                s["text"] for s in e["segments"][: appendix - 1]
            ]
            # Remove this section structurally even if a publisher places it inside
            # body: author claims are never manuscript modification evidence.
            parents = {c: p for p in root.iter() for c in p}
            revision = next(
                (s for s in root.findall(".//sec") if s.get("sec-type") == "version-changes"), None
            )
            response = list(paragraphs(revision)) if revision is not None else []
            if revision is not None:
                parents[revision].remove(revision)
            body = [title, "; ".join(authors)]
            for section in [*meta.findall("abstract"), root.find("body"), root.find("back")]:
                if section is not None:
                    body.extend(paragraphs(section))
            word_path = folder / f"v{version}.docx"
            word_path.write_bytes(docx(body))
            word = extract_document(word_path.name, word_path.read_bytes())
            assert word["text"] == "\n\n".join(body)
            guard_indices = sorted({0, len(body) // 2, len(body) - 1})
            record["versions"][str(version)] = {
                "doi": f"{doi}.{version}",
                "title": title,
                "authors": authors,
                "publisher_pdf_url": f"https://f1000research.com/articles/{article}/v{version}/pdf",
                "publisher_xml_url": f"https://f1000research.com/articles/{article}/v{version}/xml",
                "publisher_pdf_sha256": hashlib.sha256(raw).hexdigest(),
                "publisher_xml_sha256": hashlib.sha256(source_xml).hexdigest(),
                "original_page_count": len(e["segments"]),
                "article_page_count": appendix - 1,
                "body_first_page": 3,
                "pdf": {
                    "path": str(pdf_path),
                    "sha256": hashlib.sha256(excerpt).hexdigest(),
                    "transformation": "article-page excerpt without retypesetting; interactive annotations removed; appended reports/comments excluded",
                },
                "docx": {
                    "path": str(word_path),
                    "sha256": hashlib.sha256(word_path.read_bytes()).hexdigest(),
                    "transformation": "derived OOXML from licensed publisher XML body; no publisher-native Word claim",
                    "paragraph_count": len(body),
                },
                "xml_body_guards": [body[i][: min(75, len(body[i]))] for i in guard_indices],
            }
            if version == 2:
                response = [
                    p for p in response if p not in {"Revised", "Amendments from Version 1"}
                ]
                assert response and sum(map(len, response)) > 50
                response_path = folder / "author-revision-note.docx"
                response_path.write_bytes(docx(response))
                record["response"] = {
                    "path": str(response_path),
                    "sha256": hashlib.sha256(response_path.read_bytes()).hexdigest(),
                    "source_url": record["versions"]["2"]["publisher_xml_url"],
                    "source_element": "article sec[sec-type=version-changes]",
                    "license_url": LICENSE,
                    "scope": "published_author_revision_note_excerpt",
                    "transformation": "licensed article revision note converted to DOCX; not a complete rebuttal letter",
                    "text": "\n\n".join(response),
                }
                candidates = []
                for report in root.findall("./sub-article"):
                    t = report.find("./front-stub/title-group/article-title")
                    if t is None or "version 1" not in compact("".join(t.itertext())).lower():
                        continue
                    permission = report.find("./front-stub/permissions/license")
                    assert (
                        permission is not None
                        and "creativecommons.org/licenses/by/" in permission.get(XL + "href", "")
                    )
                    report_doi = report.find("./front-stub/article-id").text
                    author = report.find("./front-stub/contrib-group/contrib/name")
                    for index, p in enumerate(paragraphs(report.find("body"))):
                        score = sum(
                            token in p.lower()
                            for token in [
                                "should",
                                "could",
                                "clarif",
                                "suggest",
                                "consider",
                                "however",
                                "recommend",
                            ]
                        )
                        if score and len(p) >= 80:
                            candidates.append(
                                {
                                    "text": p,
                                    "doi": report_doi,
                                    "source_url": "https://doi.org/" + report_doi,
                                    "license_url": permission.get(XL + "href"),
                                    "credit": compact(" ".join(author.itertext()))
                                    if author is not None
                                    else "Reviewer credited in original report",
                                    "paragraph_index": index,
                                    "score": score,
                                }
                            )
                assert candidates, "No licensed review requirements"
                candidates.sort(key=lambda p: (-p["score"], p["doi"], p["paragraph_index"]))
                record["review_requirements"] = [
                    {k: v for k, v in p.items() if k != "score"} for p in candidates[:3]
                ]
        results.append(record)
    (args.output / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "public-revision-corpus.v1",
                "scope": "licensed real article version pairs with published revision-note excerpts; sandbox workflow only",
                "cases": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "cases": len(results),
                "pdf_files": 6,
                "converted_word_files": 9,
                "full_rebuttal_letters": 0,
                "license": LICENSE,
            }
        )
    )


if __name__ == "__main__":
    main()

"""Regenerate public, synthetic parser fixtures; never use confidential manuscripts."""

from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

ROOT = Path(__file__).resolve().parent
META = [
    "Title: Synthetic Editorial Review Manuscript",
    "Authors: Synthetic Author Alpha; Synthetic Author Beta",
    "Author 1: Synthetic Author Alpha",
    "Email 1: alpha@synthetic.test",
    "ORCID 1: 0000-0002-1825-0097",
    "Affiliation 1: Synthetic Research Institute",
    "Corresponding author: Synthetic Author Alpha",
    "Author 2: Synthetic Author Beta",
    "Email 2: beta@synthetic.test",
    "ORCID 2: 0000-0001-5109-3700",
    "Affiliation 2: Synthetic Publishing Laboratory",
    "Abstract: This entirely synthetic manuscript validates full text extraction,",
    "author metadata candidates, review gates and immutable source locations.",
    "Keywords: synthetic; metadata; version evidence",
]
BODY = [
    "Methods",
    "The sample contains 24 synthetic records. This is a single-arm observation.",
    "No control group is included. No real participants or confidential data exist.",
    "Results",
    "The extraction test must preserve this complete second-page content.",
    "Reference DOI: 10.1371/journal.pmed.0020124",
    "END-OF-SYNTHETIC-DOCUMENT-TRACE-2026",
]


def make_pdf():
    writer = PdfWriter()
    for lines in (META, BODY):
        page = writer.add_blank_page(width=595, height=842)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        commands = ["BT /F1 11 Tf 45 790 Td 17 TL"]
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.extend([f"({escaped}) Tj", "T*"])
        commands.append("ET")
        stream = DecodedStreamObject()
        stream.set_data("\n".join(commands).encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.add_metadata(
        {"/Title": "Entirely synthetic parser acceptance", "/Author": "Pivot test fixtures"}
    )
    writer.write(ROOT / "synthetic-manuscript.pdf")


if __name__ == "__main__":
    make_pdf()

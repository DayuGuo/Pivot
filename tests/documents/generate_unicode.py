"""Deterministic synthetic non-BMP DOCX for code-point/UTF-16 scope regressions.

Run from repository root: PYTHONPATH=. .venv/bin/python tests/documents/generate_unicode.py
"""

from pathlib import Path

from evals.public_revisions.build import docx

Path(__file__).with_name("synthetic-unicode.docx").write_bytes(
    docx(
        [
            "Title: Synthetic Unicode 😀",
            "第二段：𝛽 和 😀 均须完整保留。",
            "第三段：结束，不应混入第二段。",
        ]
    )
)

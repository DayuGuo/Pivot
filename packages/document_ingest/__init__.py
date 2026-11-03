"""Bounded local extraction of text-layer PDF and non-active DOCX manuscripts."""

from .parser import DocumentError, extract_document

__all__ = ["DocumentError", "extract_document"]

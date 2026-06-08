"""Compatibility shim: import PyMuPDF as `fitz` regardless of installed version."""
try:
    import fitz  # PyMuPDF < 1.24
except ImportError:
    import pymupdf as fitz  # type: ignore[no-redef]  # PyMuPDF >= 1.24

__all__ = ["fitz"]

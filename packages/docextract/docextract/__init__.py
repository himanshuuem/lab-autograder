"""Extract student programs from submitted PDFs and detect code similarity.

Public API:
    extract_submission(pdf_path) -> ExtractionResult
    compare_submissions(docs)    -> list[PairResult]
"""
from .convert import Bundle, ConversionError, bundle, sniff, to_pdf
from .pipeline import ExtractedProgram, ExtractionResult, extract_submission
from .similarity import Doc, PairResult, compare_submissions

__all__ = [
    "extract_submission", "ExtractionResult", "ExtractedProgram",
    "compare_submissions", "Doc", "PairResult",
    "bundle", "Bundle", "ConversionError", "sniff", "to_pdf",
]
__version__ = "1.0.0"

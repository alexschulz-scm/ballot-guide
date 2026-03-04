"""
PDF text extractor for ballot measure legal text.

Attempts to use pdfplumber if installed. Gracefully handles ImportError
(library not installed) and any parse errors from corrupt PDF data —
in both cases returns an empty string rather than raising.
"""

import io


def extract_text_from_pdf(data: bytes) -> str:
    """
    Extract plain text from PDF bytes.

    Returns an empty string if pdfplumber is not installed, if the data
    is not a valid PDF, or if any other error occurs during parsing.
    Never raises an exception.
    """
    try:
        import pdfplumber  # type: ignore[import]
    except ImportError:
        return ""

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages).strip()
    except Exception:
        return ""

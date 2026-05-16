"""Document text extraction for PDF / DOCX / TXT uploads."""

import io
import logging
from typing import Optional

import docx
import pypdf

logger = logging.getLogger(__name__)

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TXT_MIME = "text/plain"
SUPPORTED_MIMES = {PDF_MIME, DOCX_MIME, TXT_MIME}


class DocumentProcessor:
    """Extract plain text from an uploaded document."""

    @staticmethod
    def supports(mime_type: str) -> bool:
        return mime_type in SUPPORTED_MIMES

    @staticmethod
    def extract(data: bytes, mime_type: str) -> Optional[str]:
        """Return the document's text, or None if extraction failed."""
        try:
            if mime_type == PDF_MIME:
                reader = pypdf.PdfReader(io.BytesIO(data))
                return "\n".join(page.extract_text() or "" for page in reader.pages)
            if mime_type == DOCX_MIME:
                doc = docx.Document(io.BytesIO(data))
                return "\n".join(p.text for p in doc.paragraphs)
            if mime_type == TXT_MIME:
                return data.decode("utf-8", errors="replace")
        except Exception:
            logger.exception("Failed to extract %s", mime_type)
            return None
        return None

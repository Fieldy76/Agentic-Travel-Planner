import io

import docx
import pypdf

from travel_agent.agent.documents import DOCX_MIME, PDF_MIME, TXT_MIME, DocumentProcessor


def _make_pdf(text: str) -> bytes:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_docx(text: str) -> bytes:
    doc = docx.Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_supports_known_mimes():
    assert DocumentProcessor.supports(PDF_MIME)
    assert DocumentProcessor.supports(DOCX_MIME)
    assert DocumentProcessor.supports(TXT_MIME)
    assert not DocumentProcessor.supports("image/png")
    assert not DocumentProcessor.supports("application/x-msdownload")


def test_extract_txt_round_trip():
    extracted = DocumentProcessor.extract(b"hello\nworld", TXT_MIME)
    assert extracted == "hello\nworld"


def test_extract_docx_round_trip():
    data = _make_docx("Trip itinerary: Paris -> Rome")
    extracted = DocumentProcessor.extract(data, DOCX_MIME)
    assert "Trip itinerary: Paris -> Rome" in extracted


def test_extract_pdf_returns_string():
    data = _make_pdf("(unused)")
    extracted = DocumentProcessor.extract(data, PDF_MIME)
    assert isinstance(extracted, str)


def test_extract_returns_none_for_unsupported():
    assert DocumentProcessor.extract(b"x", "image/png") is None


def test_extract_returns_none_on_corrupt_pdf():
    assert DocumentProcessor.extract(b"not a real pdf", PDF_MIME) is None

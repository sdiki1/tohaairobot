from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".docx", ".txt", ".md", ".pdf"}


def list_supported_files(attach_dir: Path) -> list[Path]:
    if not attach_dir.exists():
        return []
    files = [p for p in attach_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]
    return sorted(files, key=lambda x: x.name.lower())


def read_file_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _read_docx(path)
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix in {".txt", ".md"}:
        return _read_text(path)
    return ""


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    normalized = _normalize_whitespace(text)
    if not normalized:
        return []
    if chunk_size <= 0:
        return [normalized]

    step = max(1, chunk_size - max(0, overlap))
    chunks: list[str] = []
    for start in range(0, len(normalized), step):
        chunk = normalized[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(normalized):
            break
    return chunks


def sanitize_filename(name: str) -> str:
    clean = Path(name).name.strip()
    return clean


def _read_docx(path: Path) -> str:
    document = Document(path)
    lines = [p.text.strip() for p in document.paragraphs if p.text and p.text.strip()]
    return "\n".join(lines)


def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _read_text(path: Path) -> str:
    for encoding in ("utf-8", "cp1251", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


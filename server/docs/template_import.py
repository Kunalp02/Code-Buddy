"""Import documentation templates from TXT, DOCX, or PDF into canonical Markdown."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

SUPPORTED_IMPORT_EXTENSIONS = {".md", ".txt", ".docx", ".pdf"}


def detect_format(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_IMPORT_EXTENSIONS:
        raise ValueError(f"Unsupported template format: {ext or 'unknown'}. Use .md, .txt, .docx, or .pdf")
    return ext.lstrip(".")


def import_template_bytes(filename: str, data: bytes) -> str:
    fmt = detect_format(filename)
    if fmt == "md":
        return data.decode("utf-8")
    if fmt == "txt":
        return _txt_to_markdown(data.decode("utf-8"))
    if fmt == "docx":
        return _docx_to_markdown(data)
    if fmt == "pdf":
        return _pdf_to_markdown(data)
    raise ValueError(f"Unsupported format: {fmt}")


def _txt_to_markdown(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append("")
            continue
        if stripped.isupper() and len(stripped) < 60 and " " in stripped:
            out.append(f"## {stripped.title()}")
        elif stripped.endswith(":") and len(stripped) < 60:
            out.append(f"### {stripped[:-1]}")
        elif stripped.startswith("#"):
            out.append(stripped)
        else:
            out.append(stripped)
    return "\n".join(out).strip() + "\n"


def _docx_to_markdown(data: bytes) -> str:
    from docx import Document

    doc = Document(BytesIO(data))
    out: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            out.append("")
            continue
        style = (para.style.name if para.style else "").lower()
        if "heading 1" in style:
            out.append(f"# {text}")
        elif "heading 2" in style:
            out.append(f"## {text}")
        elif "heading 3" in style:
            out.append(f"### {text}")
        elif "heading" in style:
            level = 2
            match = re.search(r"heading\s+(\d+)", style)
            if match:
                level = min(int(match.group(1)), 6)
            out.append("#" * level + f" {text}")
        elif text.startswith("#"):
            out.append(text)
        else:
            out.append(text)
    return "\n".join(out).strip() + "\n"


def _pdf_to_markdown(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    chunks: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            chunks.append(text.strip())
    if not chunks:
        raise ValueError("PDF contains no extractable text")

    merged = "\n\n".join(chunks)
    lines = merged.splitlines()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append("")
            continue
        if len(stripped) < 60 and stripped.isupper():
            out.append(f"## {stripped.title()}")
        else:
            out.append(stripped)
    return "\n".join(out).strip() + "\n"

"""Export Markdown documentation and templates to TXT, DOCX, or PDF."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

SUPPORTED_EXPORT_FORMATS = {"md", "txt", "docx", "pdf"}


def export_content(markdown: str, fmt: str, *, title: str = "Documentation", assets: dict[str, Path] | None = None) -> tuple[bytes, str]:
    fmt = fmt.lower().lstrip(".")
    if fmt not in SUPPORTED_EXPORT_FORMATS:
        raise ValueError(f"Unsupported export format: {fmt}")

    if fmt == "md":
        return markdown.encode("utf-8"), "text/markdown"
    if fmt == "txt":
        return markdown_to_txt(markdown).encode("utf-8"), "text/plain"
    if fmt == "docx":
        return markdown_to_docx(markdown, title=title, assets=assets or {}), (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    if fmt == "pdf":
        return markdown_to_pdf(markdown, title=title, assets=assets or {}), "application/pdf"
    raise ValueError(f"Unsupported export format: {fmt}")


def default_filename(base: str, fmt: str) -> str:
    stem = Path(base).stem
    return f"{stem}.{fmt.lower().lstrip('.')}"


def markdown_to_txt(markdown: str) -> str:
    text = markdown
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"[Image: \1]", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"```[\s\S]*?```", lambda m: re.sub(r"^", "  ", m.group(0).strip("`")), text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def _svg_to_png(svg_path: Path) -> Path | None:
    png_path = svg_path.with_suffix(".png")
    try:
        import cairosvg

        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path))
        return png_path if png_path.exists() else None
    except Exception:
        return None


def _resolve_image(path_ref: str, assets: dict[str, Path]) -> Path | None:
    name = Path(path_ref).name
    if name in assets:
        return assets[name]
    if path_ref in assets:
        return assets[path_ref]
    return None


def markdown_to_docx(markdown: str, *, title: str = "Documentation", assets: dict[str, Path] | None = None) -> bytes:
    from docx import Document
    from docx.shared import Inches, Pt

    assets = assets or {}
    doc = Document()
    doc.add_heading(title, 0)

    image_re = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    code_block_re = re.compile(r"```(\w+)?\n([\s\S]*?)```", re.MULTILINE)

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue

        img_match = image_re.match(line)
        if img_match:
            _, path_ref = img_match.groups()
            img_path = _resolve_image(path_ref, assets)
            if img_path and img_path.exists() and img_path.suffix.lower() != ".svg":
                doc.add_picture(str(img_path), width=Inches(6.0))
            elif img_path and img_path.exists() and img_path.suffix.lower() == ".svg":
                png_path = _svg_to_png(img_path)
                if png_path:
                    doc.add_picture(str(png_path), width=Inches(6.0))
                else:
                    doc.add_paragraph("[System Architecture diagram — see SVG export]")
            else:
                doc.add_paragraph(f"[Image: {path_ref}]")
            continue

        if line.startswith("# "):
            doc.add_heading(line[2:].strip(), level=1)
        elif line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=2)
        elif line.startswith("### "):
            doc.add_heading(line[4:].strip(), level=3)
        elif line.startswith("#### "):
            doc.add_heading(line[5:].strip(), level=4)
        elif line.startswith("```"):
            continue
        elif line.startswith("|"):
            p = doc.add_paragraph(line)
            p.style = "Intense Quote"
        elif line.startswith("- ") or line.startswith("* "):
            doc.add_paragraph(line[2:].strip(), style="List Bullet")
        else:
            doc.add_paragraph(line)

    # Append fenced code blocks inline after scan
    for match in code_block_re.finditer(markdown):
        lang, code = match.groups()
        heading = f"Code ({lang})" if lang else "Code"
        doc.add_heading(heading, level=4)
        p = doc.add_paragraph(code.strip())
        p.style = "Intense Quote"

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def markdown_to_pdf(markdown: str, *, title: str = "Documentation", assets: dict[str, Path] | None = None) -> bytes:
    from fpdf import FPDF

    assets = assets or {}
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 10, title)
    pdf.ln(4)

    image_re = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            pdf.ln(3)
            continue

        img_match = image_re.match(line)
        if img_match:
            alt, path_ref = img_match.groups()
            img_path = _resolve_image(path_ref, assets)
            if img_path and img_path.exists() and img_path.suffix.lower() == ".svg":
                png_path = _svg_to_png(img_path)
                if png_path and png_path.exists():
                    try:
                        pdf.image(str(png_path), w=180)
                        pdf.ln(4)
                        continue
                    except Exception:
                        pass
                pdf.set_font("Helvetica", "I", 10)
                pdf.multi_cell(0, 6, f"[Architecture diagram: {alt or 'System Architecture'} — see SVG export]")
            elif img_path and img_path.exists():
                try:
                    pdf.image(str(img_path), w=180)
                    pdf.ln(4)
                except Exception:
                    pdf.set_font("Helvetica", "I", 10)
                    pdf.multi_cell(0, 6, f"[Image: {alt or path_ref}]")
            else:
                pdf.set_font("Helvetica", "I", 10)
                pdf.multi_cell(0, 6, f"[Image: {alt or path_ref}]")
            continue

        if line.startswith("# "):
            pdf.set_font("Helvetica", "B", 14)
            pdf.multi_cell(0, 8, line[2:].strip())
        elif line.startswith("## "):
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(0, 7, line[3:].strip())
        elif line.startswith("### "):
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 6, line[4:].strip())
        elif line.startswith("```"):
            continue
        else:
            pdf.set_font("Helvetica", size=10)
            safe = line.encode("latin-1", errors="replace").decode("latin-1")
            pdf.multi_cell(0, 5, safe)

    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return str(out).encode("latin-1")

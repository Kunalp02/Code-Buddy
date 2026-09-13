"""Render system architecture diagram as SVG and inject into documentation."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from server.config import settings
from server.diagram.system_flow import build_system_flow_diagram

ARCHITECTURE_ASSET = "architecture-diagram.svg"
ARCHITECTURE_HEADING_RE = re.compile(r"(^##\s+Architecture\s*$)", re.IGNORECASE | re.MULTILINE)
PLACEHOLDER_RE = re.compile(r"\{\{ARCHITECTURE_DIAGRAM\}\}", re.IGNORECASE)

NODE_W = 200
NODE_H = 92


def architecture_asset_path(project_id: str) -> Path:
    return settings.data_dir / project_id / ARCHITECTURE_ASSET


def architecture_api_url(project_id: str) -> str:
    return f"/api/projects/{project_id}/documentation/assets/{ARCHITECTURE_ASSET}"


def architecture_export_ref(export_dir: str = "docs/assets") -> str:
    return f"./{export_dir.rstrip('/')}/{ARCHITECTURE_ASSET}"


def _abs_positions(diagram: dict[str, Any]) -> dict[str, dict[str, float]]:
    nodes = diagram.get("nodes", [])
    by_id = {n["id"]: n for n in nodes}
    positions: dict[str, dict[str, float]] = {}

    for node in nodes:
        pos = node.get("position", {"x": 0, "y": 0})
        x, y = float(pos.get("x", 0)), float(pos.get("y", 0))
        parent_id = node.get("parentId")
        if parent_id and parent_id in by_id:
            parent = by_id[parent_id]
            px = float(parent.get("position", {}).get("x", 0))
            py = float(parent.get("position", {}).get("y", 0))
            x += px
            y += py
        positions[node["id"]] = {"x": x, "y": y, "w": NODE_W, "h": NODE_H}
    return positions


def _diagram_to_svg(diagram: dict[str, Any]) -> str:
    nodes = [n for n in diagram.get("nodes", []) if n.get("type") != "zone"]
    zones = [n for n in diagram.get("nodes", []) if n.get("type") == "zone"]
    edges = diagram.get("edges", [])
    positions = _abs_positions(diagram)

    if not positions:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="120"><text x="20" y="60">No architecture detected</text></svg>'

    max_x = max(pos["x"] + pos["w"] for pos in positions.values())
    max_y = max(pos["y"] + pos["h"] for pos in positions.values())
    for zone in zones:
        pos = zone.get("position", {"x": 0, "y": 0})
        max_x = max(max_x, float(pos.get("x", 0)) + float(zone.get("width", 240)))
        max_y = max(max_y, float(pos.get("y", 0)) + float(zone.get("height", 200)))

    pad = 40
    width = int(max_x + pad * 2)
    height = int(max_y + pad * 2)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
        '<polygon points="0 0, 8 4, 0 8" fill="#2563eb"/></marker></defs>',
        f'<rect width="{width}" height="{height}" fill="#f8fafc"/>',
    ]

    for zone in zones:
        pos = zone.get("position", {"x": 0, "y": 0})
        x = float(pos.get("x", 0)) + pad
        y = float(pos.get("y", 0)) + pad
        zw = float(zone.get("width", 240))
        zh = float(zone.get("height", 200))
        color = zone.get("color", "#6366f1")
        label = html.escape(zone.get("label", "ZONE"))
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{zw:.1f}" height="{zh:.1f}" rx="10" '
            f'fill="{color}14" stroke="{color}55" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{x + 14:.1f}" y="{y + 22:.1f}" font-family="Inter,Arial,sans-serif" '
            f'font-size="11" font-weight="700" fill="{color}">{label}</text>'
        )

    for node in nodes:
        if node.get("type") == "zone":
            continue
        pos = positions.get(node["id"])
        if not pos:
            continue
        x = pos["x"] + pad
        y = pos["y"] + pad
        w, h = pos["w"], pos["h"]
        color = node.get("color", "#6366f1")
        label = html.escape(node.get("label", node["id"]))
        layer = html.escape((node.get("layer") or node.get("type") or "").upper())
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8" '
            f'fill="#ffffff" stroke="{color}" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{x + 12:.1f}" y="{y + 20:.1f}" font-family="Inter,Arial,sans-serif" '
            f'font-size="9" font-weight="700" fill="#64748b">{layer}</text>'
        )
        parts.append(
            f'<text x="{x + 12:.1f}" y="{y + 42:.1f}" font-family="Inter,Arial,sans-serif" '
            f'font-size="13" font-weight="700" fill="#0f172a">{label}</text>'
        )

    for edge in edges:
        src = positions.get(edge.get("source", ""))
        tgt = positions.get(edge.get("target", ""))
        if not src or not tgt:
            continue
        x1 = src["x"] + src["w"] + pad
        y1 = src["y"] + src["h"] / 2 + pad
        x2 = tgt["x"] + pad
        y2 = tgt["y"] + tgt["h"] / 2 + pad
        mid_x = (x1 + x2) / 2
        parts.append(
            f'<path d="M{x1:.1f},{y1:.1f} C{mid_x:.1f},{y1:.1f} {mid_x:.1f},{y2:.1f} {x2:.1f},{y2:.1f}" '
            f'fill="none" stroke="#2563eb" stroke-width="2" marker-end="url(#arrow)"/>'
        )
        label = html.escape(edge.get("label") or "")
        if label:
            parts.append(
                f'<text x="{mid_x:.1f}" y="{(y1 + y2) / 2 - 6:.1f}" text-anchor="middle" '
                f'font-family="Inter,Arial,sans-serif" font-size="10" font-weight="600" fill="#475569">{label}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


def render_architecture_diagram(project_id: str) -> Path:
    diagram = build_system_flow_diagram(project_id)
    svg = _diagram_to_svg(diagram)
    path = architecture_asset_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    return path


def architecture_markdown_block(project_id: str, *, for_export: bool = False, export_dir: str = "docs/assets") -> str:
    render_architecture_diagram(project_id)
    ref = architecture_export_ref(export_dir) if for_export else architecture_api_url(project_id)
    return f"![System Architecture]({ref})"


def inject_architecture_diagram(
    content: str,
    project_id: str,
    *,
    for_export: bool = False,
    export_dir: str = "docs/assets",
) -> str:
    try:
        block = architecture_markdown_block(project_id, for_export=for_export, export_dir=export_dir)
    except Exception:
        return content

    image_section = f"\n\n{block}\n\n"

    if PLACEHOLDER_RE.search(content):
        return PLACEHOLDER_RE.sub(block, content)

    match = ARCHITECTURE_HEADING_RE.search(content)
    if match:
        insert_at = match.end()
        return content[:insert_at] + image_section + content[insert_at:]

    return content + "\n\n## Architecture\n" + image_section


def copy_architecture_asset_for_export(project_id: str, project_root: Path, export_relative_path: str) -> Path | None:
    src = architecture_asset_path(project_id)
    if not src.exists():
        return None

    export_path = Path(export_relative_path)
    if export_path.parent.name == "docs":
        assets_dir = export_path.parent / "assets"
    else:
        assets_dir = export_path.parent / "docs" / "assets"
    assets_dir = (project_root / assets_dir).resolve()
    if not str(assets_dir).startswith(str(project_root.resolve())):
        raise ValueError("Invalid export asset path")
    assets_dir.mkdir(parents=True, exist_ok=True)
    dest = assets_dir / ARCHITECTURE_ASSET
    dest.write_bytes(src.read_bytes())
    return dest

"""Reference-style system architecture diagram: zones + left-to-right request flow."""

from __future__ import annotations

from typing import Any

from server.diagram.generator import LAYER_COLORS, SYSTEM_LAYER_LABELS
from server.graph.queries import get_component_connections, get_components, get_modules, get_project, get_routes

NODE_W = 200
NODE_H = 92
ZONE_PAD = 28
ZONE_HEADER = 36
ROW_GAP = 28
ZONE_GAP = 56
CLIENT_GAP = 80

ZONE_META = {
    "frontend": {"id": "zone-frontend", "label": "FRONTEND", "color": "#8b5cf6"},
    "backend": {"id": "zone-backend", "label": "BACKEND", "color": "#10b981"},
    "data": {"id": "zone-data", "label": "DATA & SERVICES", "color": "#6366f1"},
}

BACKEND_ORDER = ("proxy", "container", "api", "auth", "orm", "service", "core")
DATA_ORDER = ("database", "cache", "queue", "storage", "search", "external")

FLOW_LABELS = {
    "http": "HTTPS",
    "https": "HTTPS",
    "api": "API request",
    "route": "route",
    "auth": "authenticate",
    "orm": "data access",
    "sql": "query",
    "database": "query",
    "cache": "cache data",
    "async": "publish events",
    "queue": "publish events",
    "storage": "store / retrieve",
    "search": "search / index",
    "external": "fetch data",
    "grpc": "gRPC",
    "presentation": "API request",
    "proxy": "route",
    "container": "deploy",
}


def _zone_for_type(component_type: str) -> str | None:
    if component_type in BACKEND_ORDER:
        return "backend"
    if component_type in DATA_ORDER:
        return "data"
    return None


def _has_frontend(meta: dict, modules: list[dict]) -> bool:
    framework = (meta.get("framework") or "").lower()
    if framework in {"react", "nextjs", "vue", "angular", "svelte"}:
        return True
    for mod in modules:
        path = mod.get("path", "").lower()
        if any(token in path for token in ("web/", "frontend/", "client/", "ui/", "pages/")):
            return True
    return False


def _frontend_label(meta: dict) -> str:
    framework = (meta.get("framework") or "").lower()
    labels = {
        "react": "React Web App",
        "nextjs": "Next.js App",
        "vue": "Vue Web App",
        "angular": "Angular App",
        "svelte": "Svelte App",
    }
    return labels.get(framework, "Web Browser")


def _node(
    comp_id: str,
    label: str,
    component_type: str,
    *,
    technology: str = "",
    description: str = "",
    file_path: str = "",
    line: int | None = None,
    zone: str | None = None,
) -> dict[str, Any]:
    return {
        "id": comp_id,
        "type": component_type,
        "label": label,
        "layer": component_type,
        "technology": technology,
        "file_path": file_path,
        "line": line,
        "description": description or f"{label} ({component_type})",
        "color": LAYER_COLORS.get(component_type, LAYER_COLORS["module"]),
        "parentId": ZONE_META[zone]["id"] if zone else None,
        "flow_handles": "lr",
        "position": {"x": 0, "y": 0},
    }


def _edge(edge_id: str, source: str, target: str, label: str, edge_type: str = "flow") -> dict[str, Any]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "label": label,
        "weight": 3 if edge_type == "flow" else 2,
        "edge_type": edge_type,
    }


def _layout_zone_children(children: list[dict[str, Any]], vertical: bool = True) -> tuple[int, int]:
    if not children:
        return NODE_W + ZONE_PAD * 2, ZONE_HEADER + ZONE_PAD * 2

    if vertical:
        width = NODE_W + ZONE_PAD * 2
        height = ZONE_HEADER + ZONE_PAD * 2 + len(children) * NODE_H + (len(children) - 1) * ROW_GAP
        for idx, child in enumerate(children):
            child["position"] = {"x": ZONE_PAD, "y": ZONE_HEADER + ZONE_PAD + idx * (NODE_H + ROW_GAP)}
    else:
        height = ZONE_HEADER + ZONE_PAD * 2 + NODE_H
        width = ZONE_PAD * 2 + len(children) * NODE_W + (len(children) - 1) * ROW_GAP
        for idx, child in enumerate(children):
            child["position"] = {"x": ZONE_PAD + idx * (NODE_W + ROW_GAP), "y": ZONE_HEADER + ZONE_PAD}

    return width, height


def build_system_flow_diagram(project_id: str) -> dict[str, Any]:
    components = get_components(project_id)
    connections = get_component_connections(project_id)
    meta = get_project(project_id) or {}
    routes = get_routes(project_id)
    modules = get_modules(project_id)

    if not components:
        return {
            "level": "SYSTEM",
            "layout": "system-flow",
            "nodes": [],
            "edges": [],
            "clusters": [],
            "summary": "Re-index the project to detect system components (database, cache, auth).",
            "legend": [],
        }

    by_id = {c["id"]: c for c in components}
    used_ids: set[str] = set()

    client = by_id.get("client")
    client_node = _node(
        "client",
        client["name"] if client else "Client / User",
        "external",
        technology=client.get("technology", "HTTP Client") if client else "HTTP Client",
        description=client.get("detail", "External users or API consumers") if client else "External users or API consumers",
    )
    used_ids.add("client")

    frontend_children: list[dict[str, Any]] = []
    if _has_frontend(meta, modules):
        frontend_children.append(
            _node(
                "frontend_app",
                _frontend_label(meta),
                "presentation",
                technology=meta.get("framework") or "Web UI",
                description="User-facing web interface",
                zone="frontend",
            )
        )
        used_ids.add("frontend_app")

    backend_children: list[dict[str, Any]] = []
    data_children: list[dict[str, Any]] = []

    for comp in components:
        comp_id = comp["id"]
        if comp_id in used_ids or comp_id == "client":
            continue

        ctype = comp["component_type"]
        zone = _zone_for_type(ctype)
        if zone == "backend":
            backend_children.append(
                _node(
                    comp_id,
                    comp["name"],
                    ctype,
                    technology=comp.get("technology", ""),
                    description=comp.get("detail") or "",
                    file_path=comp.get("evidence_file") or "",
                    line=comp.get("evidence_line"),
                    zone="backend",
                )
            )
            used_ids.add(comp_id)
        elif zone == "data" and comp_id != "client":
            data_children.append(
                _node(
                    comp_id,
                    comp["name"],
                    ctype,
                    technology=comp.get("technology", ""),
                    description=comp.get("detail") or "",
                    file_path=comp.get("evidence_file") or "",
                    line=comp.get("evidence_line"),
                    zone="data",
                )
            )
            used_ids.add(comp_id)

    if not backend_children:
        backend_children.append(
            _node(
                "app_server",
                "Application Server",
                "api",
                technology=meta.get("framework") or "Application",
                description="Main application runtime",
                zone="backend",
            )
        )

    backend_children.sort(
        key=lambda n: (
            BACKEND_ORDER.index(n["type"]) if n["type"] in BACKEND_ORDER else 99,
            n["label"],
        )
    )
    data_children.sort(
        key=lambda n: (
            DATA_ORDER.index(n["type"]) if n["type"] in DATA_ORDER else 99,
            n["label"],
        )
    )

    zones: list[dict[str, Any]] = []
    zone_nodes: list[dict[str, Any]] = []
    child_nodes: list[dict[str, Any]] = []

    x_cursor = 0
    if frontend_children:
        fw, fh = _layout_zone_children(frontend_children, vertical=True)
        zone_nodes.append(
            {
                "id": ZONE_META["frontend"]["id"],
                "type": "zone",
                "label": ZONE_META["frontend"]["label"],
                "layer": "zone",
                "color": ZONE_META["frontend"]["color"],
                "width": fw,
                "height": fh,
                "description": "Presentation layer",
                "position": {"x": x_cursor, "y": 0},
            }
        )
        zones.append({"id": "frontend", "label": ZONE_META["frontend"]["label"], "width": fw, "height": fh})
        child_nodes.extend(frontend_children)
        x_cursor += fw + ZONE_GAP

    bw, bh = _layout_zone_children(backend_children, vertical=True)
    zone_nodes.append(
        {
            "id": ZONE_META["backend"]["id"],
            "type": "zone",
            "label": ZONE_META["backend"]["label"],
            "layer": "zone",
            "color": ZONE_META["backend"]["color"],
            "width": bw,
            "height": bh,
            "description": "Application and middleware services",
            "position": {"x": x_cursor, "y": 0},
        }
    )
    zones.append({"id": "backend", "label": ZONE_META["backend"]["label"], "width": bw, "height": bh})
    child_nodes.extend(backend_children)
    x_cursor += bw + ZONE_GAP

    if data_children:
        dw, dh = _layout_zone_children(data_children, vertical=True)
        zone_nodes.append(
            {
                "id": ZONE_META["data"]["id"],
                "type": "zone",
                "label": ZONE_META["data"]["label"],
                "layer": "zone",
                "color": ZONE_META["data"]["color"],
                "width": dw,
                "height": dh,
                "description": "Persistence, cache, and external integrations",
                "position": {"x": x_cursor, "y": 0},
            }
        )
        zones.append({"id": "data", "label": ZONE_META["data"]["label"], "width": dw, "height": dh})
        child_nodes.extend(data_children)

    max_zone_height = max((z["height"] for z in zones), default=NODE_H)
    client_node["position"] = {
        "x": -(NODE_W + CLIENT_GAP),
        "y": max_zone_height / 2 - NODE_H / 2,
    }

    flow_edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str]] = set()

    def add_flow(source: str, target: str, label: str) -> None:
        key = (source, target)
        if key in seen_edges:
            return
        seen_edges.add(key)
        flow_edges.append(_edge(f"flow-{source}->{target}", source, target, label))

    entry_backend = backend_children[0]["id"]
    exit_backend = backend_children[-1]["id"]

    if frontend_children:
        add_flow("client", "frontend_app", "HTTPS")
        add_flow("frontend_app", entry_backend, "API request")
    else:
        add_flow("client", entry_backend, "HTTPS")

    spine = [n["id"] for n in backend_children]
    for left, right in zip(spine, spine[1:]):
        left_type = next(n["type"] for n in backend_children if n["id"] == left)
        label = FLOW_LABELS.get(left_type, "forwards to")
        add_flow(left, right, label)

    api_node = next((n["id"] for n in backend_children if n["type"] == "api"), exit_backend)
    auth_node = next((n["id"] for n in backend_children if n["type"] == "auth"), None)
    orm_nodes = [n["id"] for n in backend_children if n["type"] == "orm"]

    if auth_node and auth_node != api_node:
        add_flow(api_node, auth_node, "authenticate")

    for orm_id in orm_nodes:
        add_flow(api_node, orm_id, "data access")

    for data_node in data_children:
        dtype = data_node["type"]
        label = FLOW_LABELS.get(dtype, "connects to")
        if dtype == "database" and orm_nodes:
            add_flow(orm_nodes[0], data_node["id"], label)
        else:
            add_flow(api_node, data_node["id"], label)

    for conn in connections:
        src, tgt = conn["source_id"], conn["target_id"]
        if src == "client" or tgt == "client":
            continue
        if (src, tgt) in seen_edges:
            continue
        ctype = conn.get("connection_type", "")
        label = conn.get("label") or FLOW_LABELS.get(ctype, ctype)
        flow_edges.append(_edge(f"evidence-{src}->{tgt}", src, tgt, label, edge_type="system"))

    db_list = [c["name"] for c in components if c["component_type"] == "database"]
    cache_list = [c["name"] for c in components if c["component_type"] == "cache"]
    auth_list = [c["name"] for c in components if c["component_type"] == "auth"]

    parts = []
    if frontend_children:
        parts.append("Frontend detected")
    if db_list:
        parts.append(f"Databases: {', '.join(db_list)}")
    if cache_list:
        parts.append(f"Cache: {', '.join(cache_list)}")
    if auth_list:
        parts.append(f"Auth: {', '.join(auth_list)}")
    if routes:
        parts.append(f"{len(routes)} API routes")

    summary = "Request flow architecture — " + (
        " · ".join(parts) if parts else "components mapped from code evidence"
    )

    present_layers = {c["component_type"] for c in components}
    if frontend_children:
        present_layers.add("presentation")
    legend = [
        {
            "layer": layer,
            "label": SYSTEM_LAYER_LABELS.get(layer, layer.replace("_", " ").title()),
            "color": LAYER_COLORS.get(layer, "#818cf8"),
        }
        for layer in sorted(
            present_layers,
            key=lambda x: (BACKEND_ORDER + DATA_ORDER).index(x) if x in BACKEND_ORDER + DATA_ORDER else 50,
        )
        if layer in SYSTEM_LAYER_LABELS or layer == "presentation"
    ]

    return {
        "level": "SYSTEM",
        "layout": "system-flow",
        "nodes": [client_node, *zone_nodes, *child_nodes],
        "edges": flow_edges,
        "clusters": [
            {
                "id": z["id"],
                "label": z["label"],
                "layer": "zone",
                "color": ZONE_META[z["id"].replace("zone-", "")]["color"],
                "modules": [],
            }
            for z in zones
        ],
        "summary": summary,
        "legend": legend,
        "meta": {
            "framework": meta.get("framework"),
            "databases": db_list,
            "caches": cache_list,
            "auth": auth_list,
            "zones": [z["label"] for z in zones],
        },
    }

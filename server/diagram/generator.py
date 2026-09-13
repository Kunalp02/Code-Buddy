from typing import Any

from server.graph.queries import (
    get_component_connections,
    get_components,
    get_file_symbols,
    get_module_deps,
    get_module_enrichment,
    get_modules,
    get_project,
    get_routes,
)

LAYER_ORDER = {
    "presentation": 0,
    "api": 1,
    "security": 2,
    "core": 3,
    "domain": 3,
    "shared": 4,
    "data": 5,
    "config": 6,
    "test": 7,
    "module": 4,
    "entry": 1,
}

LAYER_LABELS = {
    "presentation": "Presentation",
    "api": "API Layer",
    "security": "Security",
    "core": "Core / Domain",
    "domain": "Core / Domain",
    "shared": "Shared Utils",
    "data": "Data Layer",
    "config": "Configuration",
    "test": "Tests",
    "module": "Modules",
    "entry": "Entry Points",
}

LAYER_COLORS = {
    "presentation": "#8b5cf6",
    "api": "#06b6d4",
    "security": "#f59e0b",
    "core": "#6366f1",
    "domain": "#6366f1",
    "shared": "#64748b",
    "data": "#10b981",
    "config": "#94a3b8",
    "test": "#475569",
    "module": "#818cf8",
    "entry": "#22d3ee",
    "system": "#e2e8f0",
    "external": "#334155",
    "route": "#06b6d4",
    "function": "#a78bfa",
    "database": "#10b981",
    "cache": "#f43f5e",
    "queue": "#f97316",
    "storage": "#eab308",
    "search": "#14b8a6",
    "orm": "#6366f1",
    "auth": "#f59e0b",
    "container": "#4f46e5",
    "proxy": "#64748b",
}

SYSTEM_LAYER_ORDER = {
    "external": 0,
    "api": 1,
    "auth": 2,
    "orm": 3,
    "service": 3,
    "core": 3,
    "database": 4,
    "cache": 4,
    "queue": 4,
    "storage": 4,
    "search": 4,
    "container": 2,
    "proxy": 1,
}

SYSTEM_LAYER_LABELS = {
    "external": "External",
    "api": "Application",
    "auth": "Authentication",
    "orm": "Data Access",
    "service": "Services",
    "database": "Databases",
    "cache": "Cache / Sessions",
    "queue": "Message Queues",
    "storage": "Object Storage",
    "search": "Search / Analytics",
    "container": "Containers",
    "proxy": "Reverse Proxy",
}


def _classify_layer(path: str, name: str, route_count: int, symbol_count: int) -> str:
    p = path.lower()
    n = name.lower()

    if route_count > 0:
        return "api"
    if any(x in p for x in ("auth", "security", "middleware", "oauth", "jwt")):
        return "security"
    if any(x in p for x in ("api", "routes", "controllers", "handlers", "views", "endpoints", "router")):
        return "api"
    if any(x in p for x in ("db", "database", "repository", "repositories", "models", "storage", "migration")):
        return "data"
    if any(x in p for x in ("config", "settings", "constants", "env")):
        return "config"
    if any(x in p for x in ("test", "tests", "spec", "__tests__", "fixtures")):
        return "test"
    if any(x in p for x in ("web", "ui", "frontend", "components", "pages", "src")):
        return "presentation"
    if any(x in p for x in ("utils", "helpers", "common", "shared", "lib")):
        return "shared"
    if any(x in p for x in ("agent", "service", "core", "domain", "indexer", "graph", "diagram", "server")):
        return "core"
    if symbol_count >= 15:
        return "core"
    return "module"


def _layer_rank(layer: str) -> int:
    return LAYER_ORDER.get(layer, 4)


def _describe_module(path: str, layer: str, file_count: int, symbol_count: int, route_count: int) -> str:
    parts = [f"{file_count} files", f"{symbol_count} symbols"]
    if route_count:
        parts.append(f"{route_count} routes")
    layer_name = LAYER_LABELS.get(layer, layer.title())
    return f"{layer_name} · " + " · ".join(parts)


def generate_l1_diagram(project_id: str) -> dict[str, Any]:
    return generate_architecture_diagram(project_id)


def generate_architecture_diagram(project_id: str) -> dict[str, Any]:
    modules = get_modules(project_id)
    deps = get_module_deps(project_id)
    enrichment = get_module_enrichment(project_id)
    meta = get_project(project_id) or {}

    if not modules:
        return {"level": "L1", "nodes": [], "edges": [], "clusters": [], "summary": "No modules detected."}

    node_map = {m["path"]: m for m in modules}
    nodes: list[dict[str, Any]] = []
    clusters: dict[str, list[str]] = {}

    # System context node
    project_name = meta.get("name", "Application")
    nodes.append(
        {
            "id": "__system__",
            "type": "system",
            "label": project_name,
            "path": "",
            "layer": "system",
            "file_count": meta.get("stats", {}).get("files_parsed", 0),
            "symbol_count": meta.get("stats", {}).get("symbols", 0),
            "route_count": meta.get("stats", {}).get("routes", 0),
            "fan_in": 0,
            "fan_out": len(modules),
            "hub_score": len(modules),
            "description": f"{meta.get('framework', 'app')} codebase",
            "color": LAYER_COLORS["system"],
            "position": {"x": 0, "y": 0},
        }
    )

    top_modules = sorted(modules, key=lambda m: m["file_count"], reverse=True)[:6]

    for mod in modules:
        extra = enrichment.get(mod["path"], {})
        symbol_count = extra.get("symbol_count", 0)
        route_count = extra.get("route_count", 0)
        fan_in = extra.get("fan_in", 0)
        fan_out = extra.get("fan_out", 0)
        layer = _classify_layer(mod["path"], mod["name"], route_count, symbol_count)
        hub_score = fan_in + fan_out

        clusters.setdefault(layer, []).append(mod["path"])

        nodes.append(
            {
                "id": mod["path"],
                "type": "module",
                "label": mod["name"],
                "path": mod["path"],
                "layer": layer,
                "file_count": mod["file_count"],
                "symbol_count": symbol_count,
                "route_count": route_count,
                "fan_in": fan_in,
                "fan_out": fan_out,
                "hub_score": hub_score,
                "is_hub": hub_score >= 3,
                "description": _describe_module(mod["path"], layer, mod["file_count"], symbol_count, route_count),
                "color": LAYER_COLORS.get(layer, LAYER_COLORS["module"]),
                "position": {"x": 0, "y": 0},
            }
        )

    edges: list[dict[str, Any]] = []

    # Connect system to top-level entry modules
    for mod in top_modules:
        edges.append(
            {
                "id": f"__system__->{mod['path']}",
                "source": "__system__",
                "target": mod["path"],
                "weight": 1,
                "label": "contains",
                "edge_type": "system",
            }
        )

    for dep in deps:
        if dep["from_module"] in node_map and dep["to_module"] in node_map:
            weight = dep["weight"]
            edges.append(
                {
                    "id": f"{dep['from_module']}->{dep['to_module']}",
                    "source": dep["from_module"],
                    "target": dep["to_module"],
                    "weight": weight,
                    "label": str(weight) if weight > 1 else "",
                    "edge_type": "dependency",
                }
            )

    cluster_list = [
        {
            "id": layer,
            "label": LAYER_LABELS.get(layer, layer.title()),
            "layer": layer,
            "color": LAYER_COLORS.get(layer, LAYER_COLORS["module"]),
            "modules": paths,
        }
        for layer, paths in sorted(clusters.items(), key=lambda x: _layer_rank(x[0]))
    ]

    hub = max(nodes[1:], key=lambda n: n.get("hub_score", 0), default=None) if len(nodes) > 1 else None
    summary = (
        f"Auto-generated architecture: {len(modules)} modules, {len(edges)} connections across "
        f"{len(cluster_list)} layers."
    )
    if hub:
        summary += f" Central hub: {hub['label']} ({hub['path']})."

    return {
        "level": "L1",
        "layout": "layered",
        "nodes": nodes,
        "edges": edges,
        "clusters": cluster_list,
        "summary": summary,
        "legend": [
            {"layer": k, "label": v, "color": LAYER_COLORS.get(k, "#818cf8")}
            for k, v in LAYER_LABELS.items()
            if k in {c["layer"] for c in cluster_list}
        ],
    }


def generate_l3_flow(project_id: str, route_path: str | None = None) -> dict[str, Any]:
    routes = get_routes(project_id)
    if not routes:
        return {"level": "L3", "nodes": [], "edges": [], "clusters": [], "summary": "No routes detected."}

    selected = None
    if route_path:
        for r in routes:
            if r["path"] == route_path:
                selected = r
                break
    if not selected:
        selected = routes[0]

    file_path = selected.get("file_path")
    symbols = get_file_symbols(project_id, file_path) if file_path else []

    nodes = [
        {
            "id": "client",
            "type": "external",
            "label": "Client",
            "layer": "external",
            "color": LAYER_COLORS["external"],
            "description": "External caller",
            "position": {"x": 0, "y": 0},
        },
        {
            "id": "route",
            "type": "route",
            "label": f"{selected.get('method', 'GET')} {selected['path']}",
            "layer": "api",
            "color": LAYER_COLORS["route"],
            "file_path": file_path,
            "line": selected.get("line"),
            "description": "HTTP endpoint",
            "position": {"x": 0, "y": 0},
        },
    ]
    edges = [
        {
            "id": "e-client-route",
            "source": "client",
            "target": "route",
            "label": "HTTP",
            "weight": 1,
            "edge_type": "flow",
        }
    ]

    prev = "route"
    for i, sym in enumerate(symbols[:5]):
        node_id = f"sym-{sym['id']}"
        kind = sym.get("kind", "function")
        nodes.append(
            {
                "id": node_id,
                "type": kind,
                "label": sym["name"],
                "layer": "core",
                "color": LAYER_COLORS.get("function", "#a78bfa"),
                "file_path": file_path,
                "start_line": sym["start_line"],
                "description": f"{kind} in {file_path}",
                "position": {"x": 0, "y": 0},
            }
        )
        edges.append(
            {
                "id": f"e-flow-{i}",
                "source": prev,
                "target": node_id,
                "label": "calls",
                "weight": 1,
                "edge_type": "flow",
            }
        )
        prev = node_id

    return {
        "level": "L3",
        "layout": "flow",
        "nodes": nodes,
        "edges": edges,
        "clusters": [],
        "summary": f"Request flow: {selected.get('method', 'GET')} {selected['path']}",
        "route": selected,
        "legend": [],
    }


def generate_system_diagram(project_id: str) -> dict[str, Any]:
    """System architecture diagram: databases, caches, auth, connections — not folder structure."""
    components = get_components(project_id)
    connections = get_component_connections(project_id)
    meta = get_project(project_id) or {}
    routes = get_routes(project_id)

    if not components:
        return {
            "level": "SYSTEM",
            "layout": "system",
            "nodes": [],
            "edges": [],
            "clusters": [],
            "summary": "Re-index the project to detect system components (database, cache, auth).",
            "legend": [],
        }

    nodes: list[dict[str, Any]] = []
    for comp in components:
        ctype = comp["component_type"]
        nodes.append(
            {
                "id": comp["id"],
                "type": ctype,
                "label": comp["name"],
                "layer": ctype,
                "technology": comp.get("technology", ""),
                "file_path": comp.get("evidence_file") or "",
                "line": comp.get("evidence_line"),
                "description": comp.get("detail") or f"{comp['name']} ({ctype})",
                "color": LAYER_COLORS.get(ctype, LAYER_COLORS["module"]),
                "position": {"x": 0, "y": 0},
            }
        )

    edges: list[dict[str, Any]] = []
    for i, conn in enumerate(connections):
        edges.append(
            {
                "id": f"sys-{i}-{conn['source_id']}->{conn['target_id']}",
                "source": conn["source_id"],
                "target": conn["target_id"],
                "label": conn.get("label") or conn.get("connection_type", ""),
                "weight": 2,
                "edge_type": "system",
            }
        )

    db_list = [c["name"] for c in components if c["component_type"] == "database"]
    cache_list = [c["name"] for c in components if c["component_type"] == "cache"]
    auth_list = [c["name"] for c in components if c["component_type"] == "auth"]

    parts = []
    if db_list:
        parts.append(f"Databases: {', '.join(db_list)}")
    if cache_list:
        parts.append(f"Cache: {', '.join(cache_list)}")
    if auth_list:
        parts.append(f"Auth: {', '.join(auth_list)}")
    if routes:
        parts.append(f"{len(routes)} API routes")

    summary = "System architecture — " + (" · ".join(parts) if parts else "application components detected")
    summary += f" · {len(connections)} connections mapped from code evidence."

    present_layers = {c["component_type"] for c in components}
    legend = [
        {"layer": layer, "label": SYSTEM_LAYER_LABELS.get(layer, layer.title()), "color": LAYER_COLORS.get(layer, "#818cf8")}
        for layer in sorted(present_layers, key=lambda x: SYSTEM_LAYER_ORDER.get(x, 5))
        if layer in SYSTEM_LAYER_LABELS
    ]

    return {
        "level": "SYSTEM",
        "layout": "system",
        "nodes": nodes,
        "edges": edges,
        "clusters": [],
        "summary": summary,
        "legend": legend,
        "meta": {
            "framework": meta.get("framework"),
            "databases": db_list,
            "caches": cache_list,
            "auth": auth_list,
        },
    }

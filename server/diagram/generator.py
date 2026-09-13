import math
from typing import Any

from server.graph.queries import get_file_symbols, get_module_deps, get_modules, get_routes


def generate_l1_diagram(project_id: str) -> dict[str, Any]:
    modules = get_modules(project_id)
    deps = get_module_deps(project_id)

    if not modules:
        return {"nodes": [], "edges": [], "summary": "No modules detected."}

    node_map = {m["path"]: m for m in modules}
    nodes = []
    count = len(modules)
    radius = max(220, count * 28)

    for i, mod in enumerate(modules):
        angle = (2 * math.pi * i) / max(count, 1)
        x = 400 + radius * math.cos(angle)
        y = 300 + radius * math.sin(angle)
        nodes.append(
            {
                "id": mod["path"],
                "type": "module",
                "label": mod["name"],
                "path": mod["path"],
                "file_count": mod["file_count"],
                "position": {"x": x, "y": y},
            }
        )

    edges = []
    for dep in deps:
        if dep["from_module"] in node_map and dep["to_module"] in node_map:
            edges.append(
                {
                    "id": f"{dep['from_module']}->{dep['to_module']}",
                    "source": dep["from_module"],
                    "target": dep["to_module"],
                    "weight": dep["weight"],
                    "label": str(dep["weight"]),
                }
            )

    summary = (
        f"Architecture map with {len(nodes)} modules and {len(edges)} dependencies. "
        f"Largest module: {modules[0]['path']} ({modules[0]['file_count']} files)."
    )
    return {"level": "L1", "nodes": nodes, "edges": edges, "summary": summary}


def generate_l3_flow(project_id: str, route_path: str | None = None) -> dict[str, Any]:
    routes = get_routes(project_id)
    if not routes:
        return {"nodes": [], "edges": [], "summary": "No routes detected in this project."}

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
            "position": {"x": 80, "y": 200},
        },
        {
            "id": "route",
            "type": "route",
            "label": f"{selected.get('method', 'GET')} {selected['path']}",
            "file_path": file_path,
            "line": selected.get("line"),
            "position": {"x": 280, "y": 200},
        },
    ]
    edges = [{"id": "e1", "source": "client", "target": "route", "label": "request"}]

    x = 480
    prev = "route"
    for i, sym in enumerate(symbols[:4]):
        node_id = f"sym-{sym['id']}"
        nodes.append(
            {
                "id": node_id,
                "type": sym["kind"],
                "label": sym["name"],
                "file_path": file_path,
                "start_line": sym["start_line"],
                "position": {"x": x, "y": 120 + i * 80},
            }
        )
        edges.append({"id": f"e-{i+2}", "source": prev, "target": node_id, "label": "calls"})
        prev = node_id
        x += 180

    summary = f"Flow for {selected.get('method', 'GET')} {selected['path']}"
    return {
        "level": "L3",
        "nodes": nodes,
        "edges": edges,
        "summary": summary,
        "route": selected,
    }

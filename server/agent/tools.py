import json
from typing import Any

from server.diagram.generator import generate_l1_diagram, generate_l3_flow, generate_system_diagram
from server.graph.queries import (
    get_file_symbols,
    get_module_deps,
    get_modules,
    get_routes,
    get_system_architecture,
    read_snippet,
    search_symbols,
)


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_system_architecture",
            "description": (
                "Get full system architecture in ONE call: databases (type & evidence), caches, "
                "queues, auth, ORM, API routes, and how components connect. "
                "Use this FIRST for architecture, database, infrastructure, or 'how does it work' questions."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_symbol",
            "description": "Search for classes, functions, and methods by name or file path fragment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Symbol or path to search for"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_routes",
            "description": "List HTTP/API routes discovered in the project.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_module_deps",
            "description": "Get module-level dependency graph between folders/packages.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_modules",
            "description": "List top-level modules/folders and their file counts.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_snippet",
            "description": "Read a bounded code snippet from a file. Max 120 lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "start_line": {"type": "integer", "default": 1},
                    "end_line": {"type": "integer"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_symbols",
            "description": "List all symbols defined in a specific file.",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_diagram",
            "description": "Generate architecture diagram data (L1 module map or L3 route flow).",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["L1", "L3"]},
                    "route_path": {"type": "string", "description": "For L3, optional route path"},
                },
                "required": ["level"],
            },
        },
    },
]


def execute_tool(project_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        if name == "get_system_architecture":
            return get_system_architecture(project_id)
        if name == "search_symbol":
            return {
                "results": search_symbols(
                    project_id, arguments.get("query", ""), arguments.get("limit", 10)
                )
            }
        if name == "get_routes":
            return {"routes": get_routes(project_id)}
        if name == "get_module_deps":
            return {"dependencies": get_module_deps(project_id)}
        if name == "get_modules":
            return {"modules": get_modules(project_id)}
        if name == "read_snippet":
            return read_snippet(
                project_id,
                arguments["file_path"],
                arguments.get("start_line", 1),
                arguments.get("end_line"),
            )
        if name == "get_file_symbols":
            return {"symbols": get_file_symbols(project_id, arguments["file_path"])}
        if name == "generate_diagram":
            level = arguments.get("level", "L1")
            if level == "L3":
                return generate_l3_flow(project_id, arguments.get("route_path"))
            return generate_l1_diagram(project_id)
        if name == "generate_diagram" and arguments.get("level") == "SYSTEM":
            return generate_system_diagram(project_id)
        return {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        return {"error": str(exc)}


def compact_tool_result(result: dict[str, Any]) -> str:
    text = json.dumps(result, default=str)
    if len(text) > 8000:
        return text[:8000] + "...(truncated)"
    return text

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from ollama import Client

from server.agent.tools import TOOL_DEFINITIONS, compact_tool_result, execute_tool
from server.config import settings
from server.db import get_db, init_schema, load_meta
from server.graph.queries import get_project, get_stats


SYSTEM_PROMPT = """You are Arcfold, an expert codebase analyst with access to an indexed code graph.

Tool routing (follow strictly):
- Broad project questions → get_codebase_summary first
- Architecture / database / infra → get_system_architecture
- "Where is X" / "find X" → search_symbol
- "Who calls X" / "where is X used" / references → find_references or get_callers
- API endpoints → get_routes
- Module structure → get_modules + get_module_deps
- Code details → read_snippet (max 120 lines, 1-2 calls max)

Rules:
1. NEVER guess paths, symbols, or behavior — verify with tools first.
2. Cite every claim as `path:line` from tool results.
3. If tools return empty, say "Not found in index" — do not invent answers.
4. Prefer symbol references and routes over folder names.
5. For C# projects, Roslyn-backed references are available when indexed.

Format ALL responses in Markdown:
- Use ## headings for sections
- Use bullet lists and tables for routes, modules, symbols
- Use `inline code` for symbol names
- Use fenced code blocks for short snippets
- Use **bold** for key findings
"""


def _client() -> Client:
    headers = {}
    api_key = settings.ollama_api_key or os.environ.get("OLLAMA_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return Client(host=settings.ollama_host, headers=headers)


def _project_context(project_id: str) -> str:
    meta = get_project(project_id) or {}
    stats = get_stats(project_id)
    return (
        f"Project: {meta.get('name', project_id)}\n"
        f"Path: {meta.get('path', '')}\n"
        f"Framework: {meta.get('framework', 'unknown')}\n"
        f"Stats: {json.dumps(stats)}\n"
        f"Entry points: {', '.join(meta.get('entry_points', []))}"
    )


def _ensure_session(project_id: str, session_id: str | None) -> str:
    sid = session_id or str(uuid.uuid4())
    with get_db(project_id) as conn:
        init_schema(conn)
        row = conn.execute("SELECT id FROM chat_sessions WHERE id = ?", (sid,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO chat_sessions (id, created_at, title) VALUES (?, ?, ?)",
                (sid, datetime.now(timezone.utc).isoformat(), "New chat"),
            )
    return sid


def _save_message(project_id: str, session_id: str, role: str, content: str, metadata: dict | None = None):
    with get_db(project_id) as conn:
        conn.execute(
            """
            INSERT INTO chat_messages (session_id, role, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                role,
                content,
                json.dumps(metadata or {}),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def _load_history(project_id: str, session_id: str, limit: int = 20) -> list[dict[str, str]]:
    with get_db(project_id) as conn:
        rows = conn.execute(
            """
            SELECT role, content FROM chat_messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def chat_stream(
    project_id: str,
    message: str,
    session_id: str | None = None,
    model: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    if not get_project(project_id):
        yield {"type": "error", "content": "Project not found"}
        return

    sid = _ensure_session(project_id, session_id)
    model_name = model or settings.ollama_model
    tool_calls_made = 0
    evidence: list[dict[str, Any]] = []

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + _project_context(project_id)},
        *_load_history(project_id, sid),
        {"role": "user", "content": message},
    ]
    _save_message(project_id, sid, "user", message)

    client = _client()

    try:
        while tool_calls_made < settings.max_agent_tool_calls:
            response = client.chat(
                model=model_name,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                stream=False,
            )
            msg = response.message
            tool_calls = getattr(msg, "tool_calls", None) or []

            if not tool_calls:
                content = msg.content or ""
                _save_message(project_id, sid, "assistant", content, {"tool_calls": tool_calls_made, "evidence": evidence})
                yield {"type": "session", "session_id": sid}
                yield {"type": "evidence", "items": evidence}
                yield {"type": "meta", "tool_calls": tool_calls_made, "model": model_name}
                for chunk in _chunk_text(content):
                    yield {"type": "token", "content": chunk}
                yield {"type": "done"}
                return

            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": tc.function.name,
                                "arguments": _tool_arguments_for_message(tc.function.arguments),
                            }
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                tool_calls_made += 1
                name = tc.function.name
                args = _parse_tool_arguments(tc.function.arguments)

                yield {"type": "tool_start", "name": name, "arguments": args}
                result = execute_tool(project_id, name, args)
                if name == "search_symbol" and "results" in result:
                    for item in result["results"][:5]:
                        evidence.append(
                            {
                                "type": "symbol",
                                "label": f"{item['name']} ({item['kind']})",
                                "path": item["file_path"],
                                "line": item["start_line"],
                            }
                        )
                if name == "get_routes" and "routes" in result:
                    for item in result["routes"][:8]:
                        evidence.append(
                            {
                                "type": "route",
                                "label": f"{item.get('method', 'GET')} {item['path']}",
                                "path": item.get("file_path") or "",
                                "line": item.get("line"),
                            }
                        )
                if name == "get_system_architecture":
                    for comp in result.get("components", [])[:10]:
                        if comp.get("evidence_file"):
                            evidence.append(
                                {
                                    "type": comp.get("component_type", "component"),
                                    "label": f"{comp['name']} ({comp.get('technology', '')})",
                                    "path": comp["evidence_file"],
                                    "line": comp.get("evidence_line"),
                                }
                            )
                if name == "find_references":
                    for item in result.get("references", [])[:8]:
                        path = item.get("file_path") or ""
                        if path:
                            target = item.get("target", {})
                            tname = target.get("name", "") if isinstance(target, dict) else ""
                            evidence.append(
                                {
                                    "type": "reference",
                                    "label": f"{item.get('from_symbol') or 'usage'} → {tname}",
                                    "path": path,
                                    "line": item.get("line"),
                                }
                            )
                if name == "get_callers":
                    for item in result.get("callers", [])[:8]:
                        path = item.get("file_path") or ""
                        if path:
                            evidence.append(
                                {
                                    "type": "reference",
                                    "label": f"calls {item.get('target', '')}",
                                    "path": path,
                                    "line": item.get("line"),
                                }
                            )
                if name == "read_snippet" and "path" in result:
                    evidence.append(
                        {
                            "type": "snippet",
                            "label": result["path"],
                            "path": result["path"],
                            "line": result["start_line"],
                        }
                    )

                compact = compact_tool_result(result)
                yield {"type": "tool_end", "name": name, "result_preview": compact[:500]}
                messages.append({"role": "tool", "content": compact, "tool_name": name})

        messages.append(
            {
                "role": "user",
                "content": (
                    "Tool budget reached. Summarize ALL findings gathered so far in markdown. "
                    "Include databases, connections, routes, and components. Do not request more tools."
                ),
            }
        )
        try:
            summary_resp = client.chat(model=model_name, messages=messages, stream=False)
            final = summary_resp.message.content or "Partial answer only — try a more focused question."
        except Exception:
            final = (
                "I used many tool calls but could not finish synthesizing. "
                "Try asking one specific question, e.g. 'What database is used?' or 'List API routes'."
            )
        _save_message(project_id, sid, "assistant", final, {"tool_calls": tool_calls_made, "evidence": evidence})
        yield {"type": "session", "session_id": sid}
        yield {"type": "evidence", "items": evidence}
        yield {"type": "meta", "tool_calls": tool_calls_made, "model": model_name, "partial": True}
        for chunk in _chunk_text(final):
            yield {"type": "token", "content": chunk}
        yield {"type": "done"}
    except Exception as exc:
        hint = ""
        if "401" in str(exc).lower() or "unauthorized" in str(exc).lower():
            hint = " Check OLLAMA_API_KEY."
        elif "model" in str(exc).lower():
            hint = " Try a different model in settings."
        err = f"Agent error: {exc}.{hint}"
        yield {"type": "error", "content": err}


def _parse_tool_arguments(arguments: Any) -> dict[str, Any]:
    if not arguments:
        return {}
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _tool_arguments_for_message(arguments: Any) -> dict[str, Any]:
    return _parse_tool_arguments(arguments)


def _chunk_text(text: str, size: int = 40):
    for i in range(0, len(text), size):
        yield text[i : i + size]

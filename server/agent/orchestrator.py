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


SYSTEM_PROMPT = """You are Code-Buddy, an expert codebase analyst.

Rules:
1. ALWAYS use graph tools first before reading file snippets.
2. NEVER guess file paths or symbols — verify with tools.
3. Keep read_snippet calls small (max 120 lines).
4. Cite evidence as `path:line` for every factual claim.
5. If evidence is insufficient, say so clearly.
6. Prefer structural answers: modules, routes, symbols, dependencies.
7. When explaining flows, mention the route and handler files.
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
        while tool_calls_made <= settings.max_agent_tool_calls:
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

        final = "I reached the tool call limit. Please ask a more specific follow-up question."
        _save_message(project_id, sid, "assistant", final)
        yield {"type": "session", "session_id": sid}
        yield {"type": "token", "content": final}
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

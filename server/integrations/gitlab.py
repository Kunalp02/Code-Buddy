import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

DEFAULT_GITLAB = "https://gitlab.com"
MAX_FILE_BYTES = 1_000_000


def parse_project_ref(url_or_path: str) -> str:
    text = url_or_path.strip().rstrip("/")
    if "gitlab" in text and text.startswith("http"):
        m = re.search(r"gitlab[^/]*/(.+?)(?:\.git)?/?$", text, re.I)
        if m:
            return urllib.parse.quote(m.group(1), safe="")
    return urllib.parse.quote(text.strip("/"), safe="")


def _request(token: str, path: str, host: str = DEFAULT_GITLAB) -> Any:
    url = f"{host.rstrip('/')}/api/v4{path}"
    req = urllib.request.Request(
        url,
        headers={"PRIVATE-TOKEN": token, "User-Agent": "Code-Buddy"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"GitLab API error ({exc.code}): {body[:300]}") from exc


def list_projects(token: str, host: str = DEFAULT_GITLAB, per_page: int = 100) -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    for page in range(1, 6):
        data = _request(
            token,
            f"/projects?membership=true&simple=true&per_page={per_page}&page={page}&order_by=updated_at",
            host,
        )
        if not data:
            break
        for p in data:
            projects.append(
                {
                    "id": p["id"],
                    "name": p["name"],
                    "path_with_namespace": p["path_with_namespace"],
                    "default_branch": p.get("default_branch", "main"),
                    "web_url": p.get("web_url", ""),
                }
            )
        if len(data) < per_page:
            break
    return projects


def list_branches(token: str, project_id: int | str, host: str = DEFAULT_GITLAB) -> list[dict[str, str]]:
    data = _request(token, f"/projects/{project_id}/repository/branches?per_page=100", host)
    return [{"name": b["name"], "sha": b["commit"]["id"]} for b in data]


def _tree_paths(token: str, project_id: int | str, branch: str, host: str) -> list[str]:
    paths: list[str] = []
    page = 1
    while page <= 20:
        data = _request(
            token,
            f"/projects/{project_id}/repository/tree?recursive=true&per_page=100&page={page}&ref={urllib.parse.quote(branch, safe='')}",
            host,
        )
        if not data:
            break
        for item in data:
            if item.get("type") == "blob":
                paths.append(item["path"])
        if len(data) < 100:
            break
        page += 1
    return paths


def fetch_file_content(
    token: str, project_id: int | str, path: str, branch: str, host: str = DEFAULT_GITLAB
) -> bytes | None:
    encoded = urllib.parse.quote(path, safe="")
    ref = urllib.parse.quote(branch, safe="")
    url = f"{host.rstrip('/')}/api/v4/projects/{project_id}/repository/files/{encoded}/raw?ref={ref}"
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token, "User-Agent": "Code-Buddy"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            if len(data) > MAX_FILE_BYTES:
                return None
            return data
    except urllib.error.HTTPError:
        return None


def fetch_repository_files(
    token: str,
    project_id: int | str,
    branch: str,
    host: str = DEFAULT_GITLAB,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, bytes]:
    from pathlib import Path

    from server.indexer.walker import detect_language, should_skip_file

    all_paths = _tree_paths(token, project_id, branch, host)
    files: dict[str, bytes] = {}
    candidates = []
    for rel in all_paths:
        p = Path(rel)
        if should_skip_file(p):
            continue
        if detect_language(p) is None:
            continue
        candidates.append(rel)

    total = len(candidates)
    for i, rel in enumerate(candidates):
        if on_progress:
            on_progress(i + 1, total, rel)
        content = fetch_file_content(token, project_id, rel, branch, host)
        if content:
            files[rel] = content
        if i % 20 == 0:
            time.sleep(0.05)
    return files

import base64
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

GITHUB_API = "https://api.github.com"
MAX_FILE_BYTES = 1_000_000


def parse_repo_ref(url_or_path: str) -> tuple[str, str]:
    text = url_or_path.strip().rstrip("/")
    if text.startswith("http"):
        m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", text, re.I)
        if m:
            return m.group(1), m.group(2)
    parts = text.replace(".git", "").split("/")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    raise ValueError(f"Cannot parse GitHub repository: {url_or_path}")


def _request(token: str, path: str, host: str = GITHUB_API) -> Any:
    url = f"{host}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "Code-Buddy",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"GitHub API error ({exc.code}): {body[:300]}") from exc


def list_repositories(token: str, per_page: int = 100) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    for page in range(1, 6):
        data = _request(
            token,
            f"/user/repos?per_page={per_page}&page={page}&sort=updated&affiliation=owner,organization_member",
        )
        if not data:
            break
        for r in data:
            repos.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "full_name": r["full_name"],
                    "owner": r["owner"]["login"],
                    "default_branch": r.get("default_branch", "main"),
                    "private": r.get("private", False),
                    "html_url": r.get("html_url", ""),
                }
            )
        if len(data) < per_page:
            break
    return repos


def list_branches(token: str, owner: str, repo: str) -> list[dict[str, str]]:
    data = _request(token, f"/repos/{owner}/{repo}/branches?per_page=100")
    return [{"name": b["name"], "sha": b["commit"]["sha"]} for b in data]


def _tree_paths(token: str, owner: str, repo: str, branch: str) -> list[str]:
    branch_data = _request(token, f"/repos/{owner}/{repo}/branches/{urllib.parse.quote(branch, safe='')}")
    tree_sha = branch_data["commit"]["commit"]["tree"]["sha"]
    tree = _request(
        token,
        f"/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1",
    )
    if tree.get("truncated"):
        pass  # large repos — still use partial tree
    paths = []
    for item in tree.get("tree", []):
        if item.get("type") == "blob":
            paths.append(item["path"])
    return paths


def fetch_file_content(token: str, owner: str, repo: str, path: str, branch: str) -> bytes | None:
    encoded = urllib.parse.quote(path, safe="")
    ref = urllib.parse.quote(branch, safe="")
    try:
        data = _request(token, f"/repos/{owner}/{repo}/contents/{encoded}?ref={ref}")
    except RuntimeError:
        return None
    if isinstance(data, list):
        return None
    if data.get("size", 0) > MAX_FILE_BYTES:
        return None
    content = data.get("content", "")
    if data.get("encoding") == "base64":
        return base64.b64decode(content)
    return content.encode() if isinstance(content, str) else None


def fetch_repository_files(
    token: str,
    owner: str,
    repo: str,
    branch: str,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, bytes]:
    from pathlib import Path

    from server.indexer.walker import detect_language, should_skip_file

    all_paths = _tree_paths(token, owner, repo, branch)
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
        content = fetch_file_content(token, owner, repo, rel, branch)
        if content:
            files[rel] = content
        if i % 20 == 0:
            time.sleep(0.05)
    return files

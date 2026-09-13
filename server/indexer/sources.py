"""Resolve project roots: local path or remote API read (no git clone)."""

from pathlib import Path

from server.config import settings
from server.indexer.remote_store import write_workspace


def resolve_local_root(path: str) -> tuple[Path, dict]:
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root}")
    return root, {"source": "local", "url": None, "branch": None, "name": root.name}


def fetch_github_workspace(
    project_id: str,
    token: str,
    owner: str,
    repo: str,
    branch: str,
    on_progress=None,
) -> tuple[Path, dict]:
    from server.integrations.github import fetch_repository_files

    if not token:
        raise ValueError("GitHub token is required to read repository via API")

    files = fetch_repository_files(token, owner, repo, branch, on_progress)
    if not files:
        raise RuntimeError("No indexable files fetched from GitHub — check branch and token permissions")

    root = write_workspace(project_id, files)
    return root, {
        "source": "github",
        "url": f"https://github.com/{owner}/{repo}",
        "branch": branch,
        "name": repo,
        "owner": owner,
        "repo": repo,
        "read_mode": "api",
    }


def fetch_gitlab_workspace(
    project_id: str,
    token: str,
    gitlab_project_id: int | str,
    branch: str,
    path_with_namespace: str,
    host: str = "https://gitlab.com",
    on_progress=None,
) -> tuple[Path, dict]:
    from server.integrations.gitlab import fetch_repository_files

    if not token:
        raise ValueError("GitLab token is required to read repository via API")

    files = fetch_repository_files(token, gitlab_project_id, branch, host, on_progress)
    if not files:
        raise RuntimeError("No indexable files fetched from GitLab — check branch and token permissions")

    root = write_workspace(project_id, files)
    return root, {
        "source": "gitlab",
        "url": f"{host.rstrip('/')}/{path_with_namespace}",
        "branch": branch,
        "name": path_with_namespace.split("/")[-1],
        "gitlab_project_id": gitlab_project_id,
        "read_mode": "api",
    }

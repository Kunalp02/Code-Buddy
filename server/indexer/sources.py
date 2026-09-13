import hashlib
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from server.config import settings

GIT_URL_RE = re.compile(
    r"^(?:https?://|git@|ssh://)?(?:[\w.-]+@)?([\w.-]+)[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def _repo_cache_key(url: str, branch: str | None) -> str:
    raw = f"{url.strip().lower()}:{branch or 'default'}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _normalize_git_url(url: str, source: str, token: str | None = None) -> str:
    url = url.strip()
    if url.startswith("git@"):
        return url
    if not url.startswith("http"):
        if source == "github":
            url = f"https://github.com/{url.lstrip('/')}"
        elif source == "gitlab":
            url = f"https://gitlab.com/{url.lstrip('/')}"
        if not url.endswith(".git"):
            url += ".git"

    if token and url.startswith("https://"):
        parsed = urlparse(url)
        host = parsed.netloc
        path = parsed.path
        if "github.com" in host:
            return f"https://{token}@{host}{path}"
        if "gitlab.com" in host or "gitlab" in host:
            return f"https://oauth2:{token}@{host}{path}"
    return url


def _parse_repo_name(url: str) -> str:
    clean = url.rstrip("/").replace(".git", "")
    if "/" in clean:
        return clean.split("/")[-1]
    return clean or "repository"


def clone_repository(url: str, source: str, branch: str | None = None, token: str | None = None) -> Path:
    clone_url = _normalize_git_url(url, source, token)
    cache_key = _repo_cache_key(url, branch)
    target = settings.repos_dir / cache_key

    if target.exists() and (target / ".git").exists():
        _git_pull(target, branch)
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        import shutil
        shutil.rmtree(target)

    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd.extend(["--branch", branch])
    cmd.extend([clone_url, str(target)])

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"Git clone failed: {detail}") from exc
    except FileNotFoundError:
        raise RuntimeError("git is not installed on this system") from None

    return target


def _git_pull(path: Path, branch: str | None) -> None:
    try:
        if branch:
            subprocess.run(
                ["git", "fetch", "origin", branch, "--depth", "1"],
                cwd=path, check=True, capture_output=True, text=True, timeout=120,
            )
            subprocess.run(
                ["git", "checkout", branch],
                cwd=path, check=True, capture_output=True, text=True, timeout=30,
            )
            subprocess.run(
                ["git", "pull", "origin", branch],
                cwd=path, check=True, capture_output=True, text=True, timeout=120,
            )
        else:
            subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=path, check=True, capture_output=True, text=True, timeout=120,
            )
    except subprocess.CalledProcessError:
        pass


def resolve_project_root(
    source: str,
    path: str | None = None,
    url: str | None = None,
    branch: str | None = None,
    token: str | None = None,
) -> tuple[Path, dict]:
    source = (source or "local").lower()

    if source == "local":
        if not path:
            raise ValueError("Local path is required")
        root = Path(path).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"Path does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {root}")
        return root, {"source": "local", "url": None, "branch": None}

    if source not in {"github", "gitlab"}:
        raise ValueError(f"Unsupported source: {source}")

    if not url:
        raise ValueError(f"{source.title()} repository URL is required")

    root = clone_repository(url, source, branch, token)
    return root, {
        "source": source,
        "url": url.strip(),
        "branch": branch,
        "name": _parse_repo_name(url),
    }

"""Write API-fetched files to a sparse workspace (not a git clone)."""

from pathlib import Path

from server.config import settings


def workspace_path(project_id: str) -> Path:
    return settings.data_dir / project_id / "workspace"


def write_workspace(project_id: str, files: dict[str, bytes]) -> Path:
    root = workspace_path(project_id)
    if root.exists():
        import shutil
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return root

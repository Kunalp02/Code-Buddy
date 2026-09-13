from pathlib import Path

from server.config import settings

LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".dart": "dart",
    ".sql": "sql",
    ".sh": "shell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".vue": "vue",
}

COMPOSE_FILENAMES = {
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}


def detect_language(path: Path) -> str | None:
    name_lower = path.name.lower()
    if name_lower == "dockerfile" or name_lower.startswith("dockerfile."):
        return "dockerfile"
    if name_lower in COMPOSE_FILENAMES:
        return "compose"
    return LANGUAGE_MAP.get(path.suffix.lower())


def should_skip_dir(name: str) -> bool:
    return name in settings.skip_dirs or name.startswith(".")


def should_skip_file(path: Path) -> bool:
    if path.suffix.lower() in settings.skip_extensions:
        return True
    if path.name.lower() in COMPOSE_FILENAMES:
        return False
    if path.name.lower() == "dockerfile" or path.name.lower().startswith("dockerfile."):
        return False
    if path.name.startswith(".") and path.suffix not in {".env"}:
        return True
    return False


def walk_project(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root}")

    files: list[Path] = []
    for current_root, dirnames, filenames in root.walk():
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for filename in filenames:
            file_path = current_root / filename
            if should_skip_file(file_path):
                continue
            lang = detect_language(file_path)
            if lang is None:
                continue
            files.append(file_path)
    return sorted(files)


def module_key(root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(root)
    parts = rel.parts
    if len(parts) <= 1:
        return "root"
    top_level_packages = {
        "src", "app", "lib", "pkg", "internal", "server", "web", "apps", "packages",
        "java", "csharp", "rust", "dart", "flutter",
    }
    if len(parts) >= 3 and parts[0] in top_level_packages:
        return "/".join(parts[:2])
    if len(parts) >= 2:
        return parts[0]
    return "root"

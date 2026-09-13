from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

LEGACY_DATA_DIR = Path(".code-buddy-data")
DATA_DIR = Path(".arcfold-data")


def _resolve_data_dir() -> Path:
    if DATA_DIR.exists():
        return DATA_DIR
    if LEGACY_DATA_DIR.exists():
        return LEGACY_DATA_DIR
    return DATA_DIR


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ollama_host: str = "https://ollama.com"
    ollama_api_key: str = ""
    ollama_model: str = "qwen3:8b"
    ollama_model_deep: str = "gpt-oss:120b"

    data_dir: Path = _resolve_data_dir()
    repos_dir: Path = _resolve_data_dir() / "repos"
    max_snippet_lines: int = 120
    max_agent_tool_calls: int = 16

    skip_dirs: set[str] = {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".next",
        ".turbo",
        "target",
        "vendor",
        ".arcfold-data",
        ".code-buddy-data",
        "coverage",
        ".pytest_cache",
        ".mypy_cache",
        ".idea",
        ".vscode",
    }

    skip_extensions: set[str] = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".svg",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp4",
        ".mp3",
        ".zip",
        ".tar",
        ".gz",
        ".7z",
        ".pdf",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".min.js",
        ".min.css",
        ".lock",
    }


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.repos_dir.mkdir(parents=True, exist_ok=True)

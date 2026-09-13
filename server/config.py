from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ollama_host: str = "https://ollama.com"
    ollama_api_key: str = ""
    ollama_model: str = "qwen3:8b"
    ollama_model_deep: str = "gpt-oss:120b"

    data_dir: Path = Path(".code-buddy-data")
    repos_dir: Path = Path(".code-buddy-data") / "repos"
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

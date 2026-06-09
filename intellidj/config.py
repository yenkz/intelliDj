import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    slskd_host: str = "http://localhost:5030"
    slskd_api_key: str = ""
    slskd_url_base: str = "/api/v0"
    slskd_retry_attempts: int = 3
    slskd_retry_backoff: float = 0.5
    slskd_retry_max_delay: float = 8.0
    downloads_dir: str = "~/Soulseek/downloads/complete"
    library_dir: str = "~/Music/DJ/library"


def load_env(env_path: str = ".env") -> None:
    """Load .env file into os.environ (no-op if file doesn't exist)."""
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(env_path, override=False)
        return
    except Exception:
        pass
    path = Path(env_path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _load_toml_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        if sys.version_info >= (3, 11):
            import tomllib
            return tomllib.loads(path.read_text(encoding="utf-8"))
        else:
            import tomli  # type: ignore
            return tomli.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_settings(
    *,
    env_file: str | None = None,
    host: str | None = None,
    api_key: str | None = None,
) -> Settings:
    """Merge config from .env, ~/.config/intellidj/config.toml, env vars, and CLI overrides."""
    effective_env = env_file or os.getenv("INTELLIDJ_ENV", ".env")
    load_env(effective_env)

    toml_cfg = _load_toml_config(Path.home() / ".config" / "intellidj" / "config.toml")

    def _get(env_var: str, toml_key: str, default: str) -> str:
        if cli_val := (host if env_var == "SLSKD_HOST" else api_key if env_var == "SLSKD_API_KEY" else None):
            return cli_val
        if val := os.getenv(env_var):
            return val
        if val := toml_cfg.get(toml_key):
            return str(val)
        return default

    return Settings(
        slskd_host=_get("SLSKD_HOST", "slskd_host", "http://localhost:5030"),
        slskd_api_key=_get("SLSKD_API_KEY", "slskd_api_key", ""),
        slskd_url_base=os.getenv("SLSKD_URL_BASE", toml_cfg.get("slskd_url_base", "/api/v0")),
        slskd_retry_attempts=int(os.getenv("SLSKD_RETRY_ATTEMPTS", str(toml_cfg.get("slskd_retry_attempts", 3)))),
        slskd_retry_backoff=float(os.getenv("SLSKD_RETRY_BACKOFF", str(toml_cfg.get("slskd_retry_backoff", 0.5)))),
        slskd_retry_max_delay=float(os.getenv("SLSKD_RETRY_MAX_DELAY", str(toml_cfg.get("slskd_retry_max_delay", 8.0)))),
        downloads_dir=os.getenv("SLSKD_DOWNLOADS_DIR", toml_cfg.get("downloads_dir", "~/Soulseek/downloads/complete")),
        library_dir=os.getenv("LIBRARY_DIR", toml_cfg.get("library_dir", "~/Music/DJ/library")),
    )

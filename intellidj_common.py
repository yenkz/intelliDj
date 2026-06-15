#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    import tomli as tomllib  # type: ignore


DEFAULT_CONFIG_PATH = "intellidj.toml"


def repo_root_from(script_path: Path) -> Path:
    for parent in [script_path.parent] + list(script_path.parents):
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent
    return script_path.parent


def setup_script_logging(script_file: str | Path) -> None:
    script_path = Path(script_file).resolve()
    repo_root = repo_root_from(script_path)
    log_dir = repo_root / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{script_path.stem}.log"
    log_file = log_path.open("a", encoding="utf-8")

    class Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, data):
            for stream in self.streams:
                stream.write(data)
                stream.flush()

        def flush(self):
            for stream in self.streams:
                stream.flush()

    sys.stdout = Tee(sys.stdout, log_file)
    sys.stderr = Tee(sys.stderr, log_file)


def load_env_file(env_path: str = ".env", override: bool = False) -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        path = Path(env_path).expanduser()
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:
                continue
            if override or key not in os.environ:
                os.environ[key] = value
        return
    load_dotenv(env_path, override=override)


def load_project_config(config_path: str | None = None) -> dict[str, Any]:
    path = Path(config_path or os.getenv("INTELLIDJ_CONFIG", DEFAULT_CONFIG_PATH)).expanduser()
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def cfg_get(config: dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    cur: Any = config
    for part in dotted_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def add_common_config_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=None,
        help="Path to intellidj.toml (default: INTELLIDJ_CONFIG or ./intellidj.toml)",
    )


def add_common_selector_args(parser: argparse.ArgumentParser, *, include_scope: bool = True) -> None:
    if include_scope:
        parser.add_argument(
            "--scope",
            choices=["new", "existing", "all"],
            default=None,
            help="Selection scope for DB-driven stages",
        )
    parser.add_argument("--label", default=None, help="Optional batch label selector")
    parser.add_argument("--batch-id", type=int, default=None, help="Optional batch id selector")


def resolve_scope(args_scope: str | None, config: dict[str, Any], default: str = "new") -> str:
    return str(coalesce(args_scope, cfg_get(config, "pipeline.scope"), default))


def resolve_db_path(args_db_path: str | None, config: dict[str, Any], default: str = "intellidj.db") -> str:
    return str(coalesce(args_db_path, os.getenv("INTELLIDJ_DB_PATH"), cfg_get(config, "db.path"), default))


def resolve_inbox_dir(args_inbox: str | None, config: dict[str, Any]) -> str:
    return str(coalesce(
        args_inbox,
        os.getenv("INTELLIDJ_INBOX_DIR"),
        cfg_get(config, "paths.inbox_dir"),
        os.path.expanduser("~/Music/DJ/inbox"),
    ))

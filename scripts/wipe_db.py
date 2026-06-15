#!/usr/bin/env python3
"""
scripts/wipe_db.py — Wipe the IntelliDJ database and start from scratch.

Deletes the SQLite file (and any WAL/SHM journal files) and immediately
re-creates the empty schema so the database is ready for use.

Usage:
    python scripts/wipe_db.py [--yes]
"""
import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from intellidj_common import (
    add_common_config_arg,
    load_env_file,
    load_project_config,
    resolve_db_path,
)
from intellidj_db import IntelliDJDB


def main() -> None:
    parser = argparse.ArgumentParser(description="Wipe the IntelliDJ database and recreate an empty schema.")
    add_common_config_arg(parser)
    parser.add_argument("--db-path", default=None, help="SQLite path (default: INTELLIDJ_DB_PATH or ./intellidj.db)")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    config = load_project_config(args.config)
    db_path = resolve_db_path(args.db_path, config)
    db_file = Path(db_path).expanduser().resolve()

    print(f"Database: {db_file}")

    if not db_file.exists():
        print("Database file does not exist — nothing to wipe.")
        print("Run any pipeline step to create a fresh database.")
        return

    size_kb = db_file.stat().st_size // 1024
    print(f"Size:     {size_kb} KB")

    if not args.yes:
        answer = input("\nThis will permanently delete ALL data. Type 'yes' to confirm: ").strip().lower()
        if answer != "yes":
            print("Aborted.")
            sys.exit(0)

    # Remove the DB file and any SQLite journal files
    for suffix in ("", "-wal", "-shm"):
        candidate = db_file.parent / (db_file.name + suffix)
        if candidate.exists():
            candidate.unlink()
            print(f"Deleted: {candidate}")

    # Recreate the empty schema
    db = IntelliDJDB(str(db_file))
    db.close()
    print(f"Created fresh database: {db_file}")


if __name__ == "__main__":
    load_env_file()
    main()

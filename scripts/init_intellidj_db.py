#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from intellidj_common import add_common_config_arg, load_project_config, resolve_db_path
from intellidj_db import IntelliDJDB


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the IntelliDj lifecycle SQLite database")
    add_common_config_arg(parser)
    parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite path (default: INTELLIDJ_DB_PATH or ./intellidj.db)",
    )
    args = parser.parse_args()
    config = load_project_config(args.config)
    db_path = resolve_db_path(args.db_path, config)

    db = IntelliDJDB(db_path)
    try:
        print(f"Initialized database at: {db.path}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

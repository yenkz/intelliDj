#!/usr/bin/env python3
# Shim — logic now lives in intellidj.library.playlist
from intellidj.library.playlist import (  # noqa: F401
    normalize,
    clean_filename,
    extract_tags,
    build_index,
    sanitize_filename,
    run_playlist,
)

if __name__ == "__main__":
    import argparse, os
    from intellidj.library.playlist import run_playlist

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="dj_candidates.csv")
    parser.add_argument("--library-dir", default=os.path.expanduser("~/Music/DJ/library"))
    parser.add_argument("--out-dir", default="playlists")
    parser.add_argument("--dry-run", action="store_true")
    run_playlist(parser.parse_args())

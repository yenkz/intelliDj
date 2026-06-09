#!/usr/bin/env python3
# Shim — logic now lives in intellidj.library.enrich
from intellidj.library.enrich import (  # noqa: F401
    normalize,
    clean_filename,
    artist_list,
    generate_keys,
    generate_title_keys,
    best_match,
    best_match_with_duration,
    extract_artist_title_from_filename,
    extract_tags,
    extract_isrc,
    normalize_isrc,
    extract_duration_ms,
    extract_row_duration_ms,
    set_tags_mp3,
    set_tags_flac,
    write_tags,
    run_enrich,
)

if __name__ == "__main__":
    import argparse, os
    from intellidj.library.enrich import run_enrich

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="spotify_export.csv")
    parser.add_argument("--input-dir", default=os.path.expanduser("~/Soulseek/downloads/complete"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-score", type=float, default=0.86)
    parser.add_argument("--min-score-title", type=float, default=0.78)
    parser.add_argument("--duration-tolerance-ms", type=int, default=2000)
    parser.add_argument("--no-duration", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--custom-tags", action="store_true")
    parser.add_argument("--report", default=None)
    parser.add_argument("--no-tags", action="store_true")
    run_enrich(parser.parse_args())

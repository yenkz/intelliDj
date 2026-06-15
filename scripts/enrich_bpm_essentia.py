#!/usr/bin/env python3
"""
scripts/enrich_bpm_essentia.py — Enrich downloaded tracks with BPM, energy, and danceability
using local audio analysis via Essentia.

Targets tracks that have:
  - a completed download (downloads.status = 'completed') with the file on disk
  - bpm = 0 in their candidate_generation stage state

Updates track_stage_state.details_json with computed values and re-runs infer_style()
so that style classification benefits from real BPM/energy even when genres are empty
(e.g. tracks imported via Spotify OAuth after Spotify's November 2024 API deprecations).

Requirements:
    pip install essentia

Usage:
    python scripts/enrich_bpm_essentia.py --db-path intellidj.db
    python scripts/enrich_bpm_essentia.py --db-path intellidj.db --label my_set --dry-run
    python scripts/enrich_bpm_essentia.py --db-path intellidj.db --limit 10
"""
import argparse
import json
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
    setup_script_logging,
)
from intellidj_db import IntelliDJDB
from intellidj.audio_features import analyze_local_audio_features
from intellidj.spotify import infer_style


def find_tracks_needing_enrichment(
    db: IntelliDJDB,
    *,
    label: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """
    Return tracks with bpm=0 in candidate_generation and a completed download on disk.
    Optionally filtered by batch label.
    """
    query = """
        SELECT DISTINCT
            t.id           AS track_id,
            t.artist,
            t.title,
            d.download_path,
            tss.details_json
        FROM tracks t
        JOIN downloads d ON d.track_id = t.id
        JOIN track_stage_state tss ON tss.track_id = t.id
        WHERE d.status = 'completed'
          AND d.download_path IS NOT NULL
          AND tss.stage = 'candidate_generation'
          AND (
              json_extract(tss.details_json, '$.bpm') IS NULL
              OR CAST(json_extract(tss.details_json, '$.bpm') AS REAL) = 0
          )
    """
    params: list = []

    if label:
        query += """
          AND EXISTS (
              SELECT 1 FROM ingestion_batches ib
              JOIN track_stage_state tss2 ON tss2.batch_id = ib.id
              WHERE ib.label = ? AND tss2.track_id = t.id
          )
        """
        params.append(label)

    query += " ORDER BY t.id"

    if limit:
        query += f" LIMIT {int(limit)}"

    rows = db.conn.execute(query, params).fetchall()
    db_count = len(rows)

    result = []
    for row in rows:
        path = Path(row["download_path"])
        if path.exists():
            result.append({
                "track_id": int(row["track_id"]),
                "artist": row["artist"],
                "title": row["title"],
                "path": path,
                "details_json": row["details_json"],
            })

    missing = db_count - len(result)
    print(
        f"  → {db_count} with completed downloads in DB  |  "
        f"{len(result)} file(s) found on disk  |  "
        f"{missing} file(s) missing on disk (skipped)"
    )
    return result


def update_stage_details(
    db: IntelliDJDB,
    track_id: int,
    features: dict,
) -> None:
    """Merge computed audio features into candidate_generation details_json and update style."""
    row = db.conn.execute(
        "SELECT details_json FROM track_stage_state "
        "WHERE track_id = ? AND stage = 'candidate_generation'",
        (track_id,),
    ).fetchone()

    current = json.loads(row["details_json"]) if row and row["details_json"] else {}
    style = infer_style(current.get("genres", ""), features["bpm"], features["energy"])
    current.update({
        "bpm": features["bpm"],
        "energy": features["energy"],
        "danceability": features["danceability"],
        "style": style,
    })

    db.conn.execute(
        "UPDATE track_stage_state SET details_json = ?, updated_at = datetime('now') "
        "WHERE track_id = ? AND stage = 'candidate_generation'",
        (json.dumps(current), track_id),
    )
    db.conn.commit()
    db.update_track_metadata(
        track_id,
        bpm=features["bpm"],
        energy=features["energy"],
        danceability=features["danceability"],
        style=style,
        metadata_source="essentia",
    )


def main() -> None:
    setup_script_logging(__file__)
    load_env_file()

    parser = argparse.ArgumentParser(
        description="Enrich downloaded tracks with BPM/energy/danceability via Essentia"
    )
    add_common_config_arg(parser)
    parser.add_argument("--db-path", default=None, help="SQLite DB path")
    parser.add_argument("--label", default=None, help="Filter to a specific batch label")
    parser.add_argument("--limit", type=int, default=None, help="Max number of tracks to process")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be updated without writing to DB",
    )
    args = parser.parse_args()
    config = load_project_config(args.config)
    db_path = resolve_db_path(args.db_path, config)

    # Verify essentia is importable before opening the DB
    try:
        import essentia  # noqa: F401
    except ImportError:
        raise SystemExit(
            "essentia is not installed.\n"
            "Install it with: pip install essentia"
        )

    db = IntelliDJDB(db_path)
    run_id = db.start_run(
        script_name="enrich_bpm_essentia.py",
        options={
            "db_path": db_path,
            "label": args.label,
            "limit": args.limit,
            "dry_run": args.dry_run,
        },
    )
    pipeline_status = "success"
    total = success = skipped = errors = 0

    try:
        # --- Diagnostic: show bpm=0 tracks broken down by download status ---
        diag_params: list = []
        diag_query = """
            SELECT
                COALESCE(d.status, 'no_download') AS download_status,
                COUNT(DISTINCT t.id) AS track_count
            FROM tracks t
            JOIN track_stage_state tss ON tss.track_id = t.id
            LEFT JOIN downloads d ON d.track_id = t.id
            WHERE tss.stage = 'candidate_generation'
              AND (
                  json_extract(tss.details_json, '$.bpm') IS NULL
                  OR CAST(json_extract(tss.details_json, '$.bpm') AS REAL) = 0
              )
        """
        if args.label:
            diag_query += """
              AND EXISTS (
                  SELECT 1 FROM ingestion_batches ib
                  JOIN track_stage_state tss2 ON tss2.batch_id = ib.id
                  WHERE ib.label = ? AND tss2.track_id = t.id
              )
            """
            diag_params.append(args.label)
        diag_query += " GROUP BY d.status ORDER BY d.status"

        diag_rows = db.conn.execute(diag_query, diag_params).fetchall()
        label_suffix = f" (label={args.label})" if args.label else ""
        print(f"DB scan — tracks with bpm=0 in candidate_generation{label_suffix}:")
        if diag_rows:
            for r in diag_rows:
                note = "  ← eligible" if r["download_status"] == "completed" else ""
                print(f"  {r['download_status']:<16} {r['track_count']}{note}")
        else:
            print("  (none)")
        # ----------------------------------------------------------------------

        tracks = find_tracks_needing_enrichment(db, label=args.label, limit=args.limit)

        if not tracks:
            print("✅ No tracks need BPM enrichment (all have bpm > 0 or no completed downloads on disk).")
            return

        print(f"\n🎵 Found {len(tracks)} track(s) to enrich.")
        if args.dry_run:
            print("[dry-run] No changes will be written.\n")

        for i, track in enumerate(tracks, 1):
            label_str = f"[{i}/{len(tracks)}]"
            print(f"{label_str} {track['artist']} — {track['title']}")
            print(f"         {track['path']}")
            total += 1

            features = analyze_local_audio_features(track["path"])
            if features is None:
                print(f"         ⚠️  Analysis failed — skipping")
                skipped += 1
                db.add_event(
                    run_id=run_id,
                    track_id=track["track_id"],
                    stage="bpm_enrichment",
                    status="error",
                    message=str(track["path"]),
                    file_path=str(track["path"]),
                )
                continue

            print(
                f"         BPM={features['bpm']}  "
                f"energy={features['energy']}  "
                f"danceability={features['danceability']}"
            )

            if not args.dry_run:
                update_stage_details(db, track["track_id"], features)
                db.update_track_status(
                    track["track_id"], status="enriched", file_path=str(track["path"])
                )
                db.add_event(
                    run_id=run_id,
                    track_id=track["track_id"],
                    stage="bpm_enrichment",
                    status="enriched",
                    message=str(track["path"]),
                    details=features,
                    file_path=str(track["path"]),
                )

            success += 1

        errors = total - success - skipped
        verb = "Would update" if args.dry_run else "Updated"
        print(f"\n✅ {verb} {success}/{total} tracks, skipped {skipped} (analysis failed).")

    except Exception:
        pipeline_status = "error"
        errors = 1
        raise
    finally:
        db.finish_run(
            run_id,
            status=pipeline_status,
            total_count=total,
            success_count=success,
            skipped_count=skipped,
            error_count=errors,
        )
        db.close()


if __name__ == "__main__":
    main()

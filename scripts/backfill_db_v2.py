#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from intellidj_common import add_common_config_arg, cfg_get, coalesce, load_project_config, resolve_db_path
from intellidj_db import IntelliDJDB, make_track_key


def backfill_track_metadata(db: IntelliDJDB) -> tuple[int, int]:
    """
    Backfill bpm/energy/danceability/style/genres/metadata_source columns on the tracks table.

    Pass 1: Copy from exportify_tracks (highest fidelity — full Spotify data).
    Pass 2: For remaining tracks with bpm=0 or NULL, copy from track_stage_state.details_json
            (covers OAuth/SoundNet imports and any Essentia-enriched tracks).

    Returns (pass1_count, pass2_count).
    """
    # Pass 1: exportify_tracks → tracks
    pass1 = db.conn.execute(
        """
        SELECT
            t.id       AS track_id,
            et.tempo   AS bpm,
            et.energy,
            et.danceability,
            et.genres,
            ib.import_method
        FROM tracks t
        JOIN exportify_tracks et ON et.track_id = t.id
        JOIN ingestion_batches ib ON ib.id = et.batch_id
        WHERE (t.bpm IS NULL OR t.bpm = 0)
          AND et.tempo IS NOT NULL
        ORDER BY t.id
        """
    ).fetchall()

    pass1_count = 0
    for row in pass1:
        source = row["import_method"] or "exportify_csv"
        db.update_track_metadata(
            row["track_id"],
            bpm=round(float(row["bpm"])) if row["bpm"] else 0,
            energy=round(float(row["energy"]), 2) if row["energy"] is not None else None,
            danceability=round(float(row["danceability"]), 2) if row["danceability"] is not None else None,
            genres=str(row["genres"]) if row["genres"] else None,
            metadata_source=source,
        )
        pass1_count += 1

    # Pass 2: track_stage_state.details_json → tracks (for tracks still missing BPM)
    pass2_rows = db.conn.execute(
        """
        SELECT
            t.id           AS track_id,
            tss.details_json
        FROM tracks t
        JOIN track_stage_state tss ON tss.track_id = t.id AND tss.stage = 'candidate_generation'
        WHERE (t.bpm IS NULL OR t.bpm = 0)
          AND tss.details_json IS NOT NULL
          AND CAST(json_extract(tss.details_json, '$.bpm') AS REAL) > 0
        ORDER BY t.id
        """
    ).fetchall()

    pass2_count = 0
    for row in pass2_rows:
        try:
            details = json.loads(row["details_json"])
        except Exception:
            continue
        bpm = details.get("bpm")
        energy = details.get("energy")
        danceability = details.get("danceability")
        style = details.get("style")
        if not bpm:
            continue
        db.update_track_metadata(
            row["track_id"],
            bpm=int(bpm),
            energy=float(energy) if energy is not None else None,
            danceability=float(danceability) if danceability is not None else None,
            style=style,
            metadata_source="soundnet",
        )
        pass2_count += 1

    # Pass 3: copy style from details_json for tracks that now have BPM but no style
    db.conn.execute(
        """
        UPDATE tracks
        SET style = (
            SELECT json_extract(tss.details_json, '$.style')
            FROM track_stage_state tss
            WHERE tss.track_id = tracks.id AND tss.stage = 'candidate_generation'
              AND json_extract(tss.details_json, '$.style') IS NOT NULL
        )
        WHERE style IS NULL
          AND bpm > 0
        """
    )
    db.conn.commit()

    return pass1_count, pass2_count


def backfill_track_status(db: IntelliDJDB) -> tuple[int, int, int]:
    """
    Backfill status + file_path on tracks from existing downloads and library_files rows.

    Priority (highest wins, only updates tracks still at default 'imported'):
    Pass A: library_files row → in_library + file_path
    Pass B: active/completed downloads → downloading + file_path (if available)
    Pass C: only not_found downloads → not_found

    Returns (library_count, downloading_count, not_found_count).
    """
    # Pass A: library_files → in_library
    lib_rows = db.conn.execute(
        """
        SELECT DISTINCT t.id AS track_id,
               (SELECT lf2.path FROM library_files lf2
                WHERE lf2.track_id = t.id AND lf2.status != 'missing'
                LIMIT 1) AS file_path
        FROM tracks t
        WHERE t.status = 'imported'
          AND EXISTS (SELECT 1 FROM library_files lf WHERE lf.track_id = t.id AND lf.status != 'missing')
        """
    ).fetchall()
    library_count = 0
    for row in lib_rows:
        db.conn.execute(
            "UPDATE tracks SET status = 'in_library', file_path = ? WHERE id = ?",
            (row["file_path"], row["track_id"]),
        )
        library_count += 1
    if library_count:
        db.conn.commit()

    # Pass B: active/completed downloads → downloading + file_path if completed
    dl_rows = db.conn.execute(
        """
        SELECT DISTINCT t.id AS track_id,
               (SELECT d2.download_path FROM downloads d2
                WHERE d2.track_id = t.id AND d2.status = 'completed'
                  AND d2.download_path IS NOT NULL
                LIMIT 1) AS file_path
        FROM tracks t
        WHERE t.status = 'imported'
          AND EXISTS (
              SELECT 1 FROM downloads d WHERE d.track_id = t.id
              AND d.status IN ('completed', 'downloading', 'found', 'searching')
          )
        """
    ).fetchall()
    downloading_count = 0
    for row in dl_rows:
        db.conn.execute(
            "UPDATE tracks SET status = 'downloading', file_path = ? WHERE id = ?",
            (row["file_path"], row["track_id"]),
        )
        downloading_count += 1
    if downloading_count:
        db.conn.commit()

    # Pass C: only not_found downloads → not_found
    not_found_rows = db.conn.execute(
        """
        SELECT DISTINCT t.id AS track_id
        FROM tracks t
        WHERE t.status = 'imported'
          AND EXISTS (SELECT 1 FROM downloads d WHERE d.track_id = t.id AND d.status = 'not_found')
          AND NOT EXISTS (
              SELECT 1 FROM downloads d WHERE d.track_id = t.id
              AND d.status IN ('completed', 'downloading', 'found', 'searching')
          )
        """
    ).fetchall()
    not_found_count = 0
    for row in not_found_rows:
        db.conn.execute(
            "UPDATE tracks SET status = 'not_found' WHERE id = ?",
            (row["track_id"],),
        )
        not_found_count += 1
    if not_found_count:
        db.conn.commit()

    return library_count, downloading_count, not_found_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill new DB-first tables from legacy playlist_entries/track_events")
    add_common_config_arg(parser)
    parser.add_argument("--db-path", default=None, help="SQLite path")
    parser.add_argument("--label", default="legacy-backfill", help="Batch label for migrated rows")
    parser.add_argument("--force", action="store_true", help="Backfill even if exportify_tracks already has rows")
    parser.add_argument("--metadata-only", action="store_true", help="Only backfill tracks metadata columns; skip legacy migration")
    args = parser.parse_args()
    config = load_project_config(args.config)
    db_path = resolve_db_path(args.db_path, config)
    label = str(coalesce(args.label, cfg_get(config, "pipeline.label"), "legacy-backfill"))

    db = IntelliDJDB(db_path)
    try:
        if args.metadata_only:
            print("Running metadata-only backfill (tracks.bpm/energy/danceability/style/genres)...")
            p1, p2 = backfill_track_metadata(db)
            print(f"  Pass 1 (exportify_tracks → tracks): {p1} rows updated")
            print(f"  Pass 2 (details_json → tracks):     {p2} rows updated")
            print("Running status backfill (tracks.status/file_path)...")
            lib, dl, nf = backfill_track_status(db)
            print(f"  Pass A (library_files → in_library): {lib} rows updated")
            print(f"  Pass B (downloads → downloading):    {dl} rows updated")
            print(f"  Pass C (not_found downloads):        {nf} rows updated")
            print("Done.")
            return

        existing = db.conn.execute("SELECT COUNT(*) AS n FROM exportify_tracks").fetchone()["n"]
        if existing and not args.force:
            print(f"Skipping legacy migration: exportify_tracks already contains {existing} rows")
            print("Tip: run with --metadata-only to backfill tracks metadata columns.")
            p1, p2 = backfill_track_metadata(db)
            print(f"  Metadata backfill — Pass 1: {p1} rows, Pass 2: {p2} rows")
            lib, dl, nf = backfill_track_status(db)
            print(f"  Status backfill — in_library: {lib}, downloading: {dl}, not_found: {nf}")
            return

        batch_id = db.create_ingestion_batch(
            source_type="exportify_csv",
            import_method="legacy_backfill",
            label=label,
            source_ref="legacy:playlist_entries",
        )
        run_id = db.start_run(
            script_name="backfill_db_v2.py",
            input_path=str(db.path),
            options={"label": label, "force": args.force, "db_path": db_path},
        )
        inserted = 0
        rows = db.conn.execute(
            """
            SELECT id, track_id, source_csv, row_index, artist, title, search_string, raw_json
            FROM playlist_entries
            ORDER BY id
            """
        ).fetchall()
        for row in rows:
            track_id = row["track_id"]
            parsed = None
            raw = row["raw_json"]
            if raw:
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = None
            if not track_id:
                artist = row["artist"]
                title = row["title"]
                search_string = row["search_string"] or f"{artist or ''} - {title or ''}".strip(" -")
                track_key = make_track_key(artist=artist, title=title, search_string=search_string)
                track_id = db.upsert_track(
                    track_key=track_key,
                    artist=artist,
                    title=title,
                    source_search_string=search_string,
                    source_csv=row["source_csv"],
                )

            db.upsert_track_ingestion(
                track_id=int(track_id),
                batch_id=batch_id,
                source_type="exportify_csv",
                import_method="legacy_backfill",
                row_index=int(row["row_index"]) if row["row_index"] is not None else -1,
                is_new_track=False,
            )

            if isinstance(parsed, dict):
                db.upsert_exportify_track(
                    batch_id=batch_id,
                    track_id=int(track_id),
                    source_csv=row["source_csv"],
                    row_index=int(row["row_index"]) if row["row_index"] is not None else inserted,
                    row=parsed,
                )
            db.upsert_track_stage_state(
                track_id=int(track_id),
                stage="ingestion",
                status="ingested",
                run_id=run_id,
                batch_id=batch_id,
                method="legacy_backfill",
            )
            inserted += 1

        # Backfill candidate generation state from historical events.
        candidate_ids = db.conn.execute(
            """
            SELECT DISTINCT track_id
            FROM track_events
            WHERE stage = 'candidate_generation' AND status = 'candidate_generated' AND track_id IS NOT NULL
            """
        ).fetchall()
        for c in candidate_ids:
            db.upsert_track_stage_state(
                track_id=int(c["track_id"]),
                stage="candidate_generation",
                status="candidate_generated",
                run_id=run_id,
                batch_id=batch_id,
                method="legacy_backfill",
            )

        db.finish_run(
            run_id,
            status="success",
            total_count=len(rows),
            success_count=inserted,
            skipped_count=0,
            error_count=0,
            notes=f"batch_id={batch_id}; label={label}",
        )
        print(f"Legacy backfill complete: rows={inserted}, batch_id={batch_id}, label={label}")

        print("Running metadata backfill (tracks.bpm/energy/danceability/style/genres)...")
        p1, p2 = backfill_track_metadata(db)
        print(f"  Pass 1 (exportify_tracks → tracks): {p1} rows updated")
        print(f"  Pass 2 (details_json → tracks):     {p2} rows updated")
        print("Running status backfill (tracks.status/file_path)...")
        lib, dl, nf = backfill_track_status(db)
        print(f"  Pass A (library_files → in_library): {lib} rows updated")
        print(f"  Pass B (downloads → downloading):    {dl} rows updated")
        print(f"  Pass C (not_found downloads):        {nf} rows updated")
    finally:
        db.close()


if __name__ == "__main__":
    main()

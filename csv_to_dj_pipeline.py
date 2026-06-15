import argparse
import pandas as pd
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from intellidj_common import (
    add_common_config_arg,
    cfg_get,
    coalesce,
    load_project_config,
    resolve_db_path,
    setup_script_logging,
)
from intellidj_db import IntelliDJDB, make_track_key, normalize_text
from intellidj.spotify import (
    build_candidates_dataframe,
    clean_track_name,
    infer_style,
    normalize_artist,
    simplify_for_search,
)


DEFAULT_INPUT_FILE = "spotify_export.csv"

# Maps alternative column names (e.g. Spanish Exportify) to the canonical names.
COLUMN_ALIASES: dict[str, str] = {
    "Nombre de la canción": "Track Name",
    "Nombre(s) del artista": "Artist Name(s)",
    "Duración de la canción (ms)": "Duration (ms)",
    "Song Name": "Track Name",
    "Artist Name": "Artist Name(s)",
    "Track Duration (ms)": "Duration (ms)",
}

# Audio-feature columns that may be absent in basic Exportify exports.
OPTIONAL_NUMERIC_COLUMNS = ["Tempo", "Energy", "Danceability"]
OPTIONAL_STRING_COLUMNS = ["Genres", "Record Label"]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename known alias columns to canonical names and fill in missing optional ones."""
    df = df.rename(columns=COLUMN_ALIASES)
    for col in OPTIONAL_NUMERIC_COLUMNS:
        if col not in df.columns:
            print(f"ℹ️  Column '{col}' not found — defaulting to 0")
            df[col] = 0.0
    for col in OPTIONAL_STRING_COLUMNS:
        if col not in df.columns:
            print(f"ℹ️  Column '{col}' not found — defaulting to empty string")
            df[col] = ""
    return df


def _check_already_in_library(
    db: IntelliDJDB,
    *,
    artist: Optional[str],
    title: Optional[str],
    isrc: Optional[str] = None,
    duration_ms: Optional[int] = None,
    duration_tolerance_ms: int = 4000,
) -> tuple[bool, Optional[int], Optional[str]]:
    """
    Check if a track is already present in the local library by metadata.

    Strategy (in order of confidence):
    1. ISRC match: tracks.isrc JOIN library_files via track_id
    2. Normalized artist + title match in library_files tags
    3. Optional duration tolerance filter on matches found

    Returns (found, library_file_id, path).
    """
    # 1. ISRC-based lookup (most reliable)
    if isrc:
        isrc_norm = normalize_text(isrc).replace(" ", "")
        row = db.conn.execute(
            """
            SELECT lf.id, lf.path FROM library_files lf
            JOIN tracks t ON t.id = lf.track_id
            WHERE t.isrc IS NOT NULL
              AND LOWER(REPLACE(t.isrc, ' ', '')) = ?
            LIMIT 1
            """,
            (isrc_norm,),
        ).fetchone()
        if row:
            if duration_ms and row.get("path"):
                # Verify duration if we have it (skip if library file has no duration)
                lf = db.conn.execute(
                    "SELECT duration_ms FROM library_files WHERE id = ?",
                    (row["id"],),
                ).fetchone()
                if lf and lf["duration_ms"] and abs(lf["duration_ms"] - duration_ms) > duration_tolerance_ms:
                    pass  # Duration mismatch — don't treat as a match
                else:
                    return True, int(row["id"]), str(row["path"])
            else:
                return True, int(row["id"]), str(row["path"])

    # 2. Normalized artist + title match
    if artist and title:
        artist_norm = normalize_text(artist)
        title_norm = normalize_text(title)
        rows = db.conn.execute(
            """
            SELECT lf.id, lf.path, lf.duration_ms, lf.artist_tag, lf.title_tag
            FROM library_files lf
            WHERE LOWER(lf.artist_tag) IS NOT NULL
              AND LOWER(lf.title_tag) IS NOT NULL
            """,
        ).fetchall()
        for r in rows:
            r_artist = normalize_text(r["artist_tag"] or "")
            r_title = normalize_text(r["title_tag"] or "")
            if r_artist == artist_norm and r_title == title_norm:
                if duration_ms and r["duration_ms"]:
                    if abs(r["duration_ms"] - duration_ms) <= duration_tolerance_ms:
                        return True, int(r["id"]), str(r["path"])
                else:
                    return True, int(r["id"]), str(r["path"])

    return False, None, None


def main(
    input_file: str,
    output_file: str | None = None,
    db_path: str | None = None,
    label: str | None = None,
    import_method: str = "exportify_csv",
    dry_run: bool = False,
    check_library: bool = False,
) -> None:
    df = pd.read_csv(input_file)
    df = _normalize_columns(df)

    required_columns = [
        "Artist Name(s)",
        "Track Name",
    ]
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise SystemExit(f"Missing required columns: {', '.join(missing)}")

    df = df.copy()
    for col in ["Artist Name(s)", "Track Name", "Genres", "Record Label"]:
        df[col] = df[col].fillna("").astype(str)

    for col in ["Tempo", "Energy", "Danceability"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        invalid = df[col].isna().sum()
        if invalid:
            print(f"⚠️  {invalid} rows have invalid {col}; defaulting to 0")
        df[col] = df[col].fillna(0)

    empty_artist = df["Artist Name(s)"].str.strip() == ""
    empty_track = df["Track Name"].str.strip() == ""
    if (empty_artist | empty_track).any():
        dropped = int((empty_artist | empty_track).sum())
        print(f"⚠️  Dropping {dropped} rows missing artist or track")
        df = df[~(empty_artist | empty_track)]

    print("📄 Columnas detectadas:")
    print(df.columns.tolist())

    out = build_candidates_dataframe(df)

    if dry_run:
        print(f"[dry-run] input rows={len(df)} candidates={len(out)}")
        if output_file:
            print(f"[dry-run] would write candidates CSV: {output_file}")
        return

    db = IntelliDJDB(db_path)
    run_id = db.start_run(
        script_name="csv_to_dj_pipeline.py",
        input_path=input_file,
        output_path=output_file,
        options={
            "db_path": db_path,
            "label": label,
            "import_method": import_method,
            "dry_run": dry_run,
        },
    )
    pipeline_status = "success"
    total_count = success_count = skipped_count = error_count = 0
    label_value = label or f"{Path(input_file).stem}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    batch_id = db.create_ingestion_batch(
        source_type="exportify_csv",
        import_method=import_method,
        label=label_value,
        source_ref=input_file,
    )

    try:
        # Tracks whose search_string is already matched to an on-disk library file
        already_in_library_keys: set[str] = set()

        for idx, row in df.iterrows():
            artist = normalize_artist(str(row["Artist Name(s)"]))
            track = clean_track_name(str(row["Track Name"]))
            search_string = f"{artist} - {track}"
            isrc = str(row.get("ISRC", "") or "").strip() or None
            duration_ms_raw = row.get("Duration (ms)")
            duration_ms = int(float(duration_ms_raw)) if duration_ms_raw not in (None, "", "nan") else None
            track_key = make_track_key(
                artist=artist,
                title=track,
                isrc=isrc,
                search_string=search_string,
                duration_ms=duration_ms,
            )
            existing_track_id = db.get_track_id_by_key(track_key)
            track_id = db.upsert_track(
                track_key=track_key,
                artist=artist,
                title=track,
                isrc=isrc,
                duration_ms=duration_ms,
                source_search_string=search_string,
                source_csv=input_file,
            )
            db.upsert_track_ingestion(
                track_id=track_id,
                batch_id=batch_id,
                source_type="exportify_csv",
                import_method=import_method,
                row_index=int(idx),
                is_new_track=existing_track_id is None,
            )
            db.add_playlist_entry(
                run_id=run_id,
                track_id=track_id,
                source_csv=input_file,
                row_index=int(idx),
                artist=artist,
                title=track,
                search_string=search_string,
                raw_row=row.to_dict(),
            )
            db.add_event(
                run_id=run_id,
                track_id=track_id,
                stage="csv_review",
                status="reviewed",
                message=search_string,
            )
            db.upsert_track_stage_state(
                track_id=track_id,
                stage="csv_review",
                status="reviewed",
                run_id=run_id,
                batch_id=batch_id,
                method=import_method,
            )
            db.upsert_track_stage_state(
                track_id=track_id,
                stage="ingestion",
                status="ingested",
                run_id=run_id,
                batch_id=batch_id,
                method=import_method,
                details={"source_type": "exportify_csv", "source_ref": input_file},
            )
            db.upsert_exportify_track(
                batch_id=batch_id,
                track_id=track_id,
                source_csv=input_file,
                row_index=int(idx),
                row=row.to_dict(),
            )

            if check_library:
                in_lib, lf_id, lib_path = _check_already_in_library(
                    db,
                    artist=artist,
                    title=track,
                    isrc=isrc,
                    duration_ms=duration_ms,
                )
                if in_lib:
                    already_in_library_keys.add(search_string)
                    db.upsert_track_stage_state(
                        track_id=track_id,
                        stage="candidate_generation",
                        status="already_in_library",
                        run_id=run_id,
                        batch_id=batch_id,
                        method=import_method,
                        details={"library_path": lib_path},
                    )
                    db.add_event(
                        run_id=run_id,
                        track_id=track_id,
                        stage="candidate_generation",
                        status="already_in_library",
                        message=f"Found in local library: {lib_path}",
                        file_path=lib_path,
                    )

        if output_file:
            out.to_csv(output_file, index=False)

        for _, row in out.iterrows():
            search_string = str(row["search_string"])

            # Skip candidate generation if the track is already in the library
            if search_string in already_in_library_keys:
                skipped_count += 1
                continue

            track_key = make_track_key(
                artist=str(row["artist"]),
                title=str(row["track"]),
                search_string=search_string,
            )
            track_id = db.upsert_track(
                track_key=track_key,
                artist=str(row["artist"]),
                title=str(row["track"]),
                source_search_string=search_string,
                source_csv=input_file,
            )
            db.add_event(
                run_id=run_id,
                track_id=track_id,
                stage="candidate_generation",
                status="candidate_generated",
                message=search_string,
                details={
                    "style": row.get("style"),
                    "bpm": row.get("bpm"),
                    "energy": row.get("energy"),
                    "danceability": row.get("danceability"),
                },
            )
            db.upsert_track_stage_state(
                track_id=track_id,
                stage="candidate_generation",
                status="candidate_generated",
                run_id=run_id,
                batch_id=batch_id,
                method=import_method,
                details={
                    "style": row.get("style"),
                    "bpm": row.get("bpm"),
                    "energy": row.get("energy"),
                    "danceability": row.get("danceability"),
                },
            )
            db.update_track_metadata(
                track_id,
                bpm=int(row["bpm"]) if row.get("bpm") is not None else None,
                energy=float(row["energy"]) if row.get("energy") is not None else None,
                danceability=float(row["danceability"]) if row.get("danceability") is not None else None,
                style=row.get("style"),
                genres=str(row["genres"]) if row.get("genres") is not None else None,
                metadata_source=import_method,
            )
            db.update_track_status(track_id, status="imported")

        if output_file:
            print(f"✅ Generado {output_file}")
        else:
            print("✅ Candidate generation stored in DB only")
        print(f"🎧 Tracks procesados: {len(out)}")
        print(f"🏷️  Batch label: {label_value} (batch_id={batch_id})")

        total_count = int(len(df))
        success_count = int(len(out))
        skipped_count = max(total_count - success_count, 0)
    except Exception as exc:
        pipeline_status = "error"
        error_count = 1
        raise
    finally:
        db.finish_run(
            run_id,
            status=pipeline_status,
            total_count=total_count,
            success_count=success_count,
            skipped_count=skipped_count,
            error_count=error_count,
        )
        db.close()


if __name__ == "__main__":
    setup_script_logging(__file__)
    parser = argparse.ArgumentParser(description="Import a Spotify Exportify CSV into the IntelliDJ DB and generate candidates")
    add_common_config_arg(parser)
    parser.add_argument("--input", default=None, help="Path to spotify_export.csv")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional candidates CSV output path (DB remains the source of truth)",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite path for lifecycle tracking (default: INTELLIDJ_DB_PATH or ./intellidj.db)",
    )
    parser.add_argument("--label", default=None, help="Optional batch label to tag this import")
    parser.add_argument("--import-method", default="exportify_csv", help="Import method label stored in DB")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview only; do not write DB/CSV")
    parser.add_argument(
        "--check-library",
        action="store_true",
        default=False,
        help="Before marking a track as a download candidate, check if it already exists in the local library DB",
    )
    args = parser.parse_args()
    config = load_project_config(args.config)
    input_file = coalesce(args.input, cfg_get(config, "paths.spotify_csv"), DEFAULT_INPUT_FILE)
    db_path = resolve_db_path(args.db_path, config)
    label = coalesce(args.label, cfg_get(config, "pipeline.label"))
    import_method = coalesce(args.import_method, cfg_get(config, "pipeline.import_method"), "exportify_csv")
    main(
        input_file=input_file,
        output_file=args.output,
        db_path=db_path,
        label=label,
        import_method=import_method,
        dry_run=args.dry_run,
        check_library=args.check_library,
    )

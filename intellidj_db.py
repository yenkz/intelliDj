#!/usr/bin/env python3
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


DEFAULT_DB_PATH = "intellidj.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    text = value.lower().strip()
    text = re.sub(r"\(.*?\)|\[.*?\]|\{.*?\}", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def make_track_key(
    *,
    artist: Optional[str] = None,
    title: Optional[str] = None,
    isrc: Optional[str] = None,
    search_string: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> str:
    isrc_norm = normalize_text(isrc).replace(" ", "")
    if isrc_norm:
        return f"isrc:{isrc_norm}"

    artist_norm = normalize_text(artist)
    title_norm = normalize_text(title)
    search_norm = normalize_text(search_string)
    duration_bucket = ""
    if duration_ms and duration_ms > 0:
        duration_bucket = str(int(round(duration_ms / 1000.0)))
    base = f"{artist_norm}|{title_norm}|{search_norm}|{duration_bucket}".strip("|")
    if not base:
        base = "unknown"
    return f"meta:{base}"


class IntelliDJDB:
    def __init__(self, db_path: Optional[str] = None):
        path_value = db_path or os.getenv("INTELLIDJ_DB_PATH", DEFAULT_DB_PATH)
        self.path = Path(path_value).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.init_schema()

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_uuid TEXT NOT NULL UNIQUE,
            script_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            status TEXT NOT NULL,
            input_path TEXT,
            output_path TEXT,
            options_json TEXT,
            total_count INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            skipped_count INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_key TEXT NOT NULL UNIQUE,
            artist TEXT,
            title TEXT,
            album TEXT,
            isrc TEXT,
            duration_ms INTEGER,
            source_search_string TEXT,
            source_csv TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS playlist_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            track_id INTEGER,
            source_csv TEXT,
            row_index INTEGER,
            artist TEXT,
            title TEXT,
            search_string TEXT,
            raw_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES pipeline_runs(id) ON DELETE SET NULL,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS track_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            track_id INTEGER,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            details_json TEXT,
            file_path TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES pipeline_runs(id) ON DELETE SET NULL,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER,
            run_id INTEGER,
            asset_type TEXT NOT NULL,
            path TEXT NOT NULL,
            origin TEXT,
            status TEXT,
            size_bytes INTEGER,
            extra_json TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            UNIQUE(asset_type, path),
            FOREIGN KEY(run_id) REFERENCES pipeline_runs(id) ON DELETE SET NULL,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS duplicate_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            group_id INTEGER NOT NULL,
            track_id INTEGER,
            role TEXT NOT NULL,
            action TEXT NOT NULL,
            origin TEXT,
            path TEXT NOT NULL,
            target_path TEXT,
            keep_path TEXT,
            keep_strategy TEXT,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES pipeline_runs(id) ON DELETE SET NULL,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tracks_isrc ON tracks(isrc);
        CREATE INDEX IF NOT EXISTS idx_tracks_artist_title ON tracks(artist, title);
        CREATE INDEX IF NOT EXISTS idx_events_stage_status ON track_events(stage, status);
        CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);

        CREATE TABLE IF NOT EXISTS ingestion_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_uuid TEXT NOT NULL UNIQUE,
            source_type TEXT NOT NULL,
            import_method TEXT,
            label TEXT,
            source_ref TEXT,
            created_at TEXT NOT NULL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS track_ingestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER NOT NULL,
            batch_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            import_method TEXT,
            row_index INTEGER NOT NULL DEFAULT -1,
            is_new_track INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(track_id, batch_id, source_type, row_index),
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE,
            FOREIGN KEY(batch_id) REFERENCES ingestion_batches(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS exportify_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            track_id INTEGER,
            source_csv TEXT,
            row_index INTEGER NOT NULL,
            track_uri TEXT,
            track_name TEXT,
            album_name TEXT,
            artist_names TEXT,
            release_date TEXT,
            duration_ms INTEGER,
            popularity INTEGER,
            explicit TEXT,
            added_by TEXT,
            added_at TEXT,
            genres TEXT,
            record_label TEXT,
            danceability REAL,
            energy REAL,
            key_value TEXT,
            loudness REAL,
            mode_value TEXT,
            speechiness REAL,
            acousticness REAL,
            instrumentalness REAL,
            liveness REAL,
            valence REAL,
            tempo REAL,
            time_signature TEXT,
            raw_row_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(batch_id) REFERENCES ingestion_batches(id) ON DELETE CASCADE,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS library_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER,
            track_id INTEGER,
            path TEXT NOT NULL UNIQUE,
            filename TEXT,
            extension TEXT,
            size_bytes INTEGER,
            duration_ms INTEGER,
            bitrate_kbps INTEGER,
            sample_rate INTEGER,
            bit_depth INTEGER,
            artist_tag TEXT,
            title_tag TEXT,
            album_tag TEXT,
            source_type TEXT,
            status TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            FOREIGN KEY(batch_id) REFERENCES ingestion_batches(id) ON DELETE SET NULL,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS track_stage_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER NOT NULL,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            run_id INTEGER,
            batch_id INTEGER,
            method TEXT,
            details_json TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(track_id, stage),
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE,
            FOREIGN KEY(run_id) REFERENCES pipeline_runs(id) ON DELETE SET NULL,
            FOREIGN KEY(batch_id) REFERENCES ingestion_batches(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS library_fingerprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            library_file_id INTEGER NOT NULL,
            track_id INTEGER,
            fpcalc_fingerprint TEXT,
            fpcalc_duration_sec REAL,
            acoustid_id TEXT,
            acoustid_score REAL,
            acoustid_recording_id TEXT,
            acoustid_title TEXT,
            acoustid_artist TEXT,
            fingerprint_method TEXT NOT NULL DEFAULT 'fpcalc',
            status TEXT NOT NULL DEFAULT 'computed',
            computed_at TEXT NOT NULL,
            UNIQUE(library_file_id),
            FOREIGN KEY(library_file_id) REFERENCES library_files(id) ON DELETE CASCADE,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_fingerprints_acoustid ON library_fingerprints(acoustid_id);
        CREATE INDEX IF NOT EXISTS idx_fingerprints_track ON library_fingerprints(track_id);

        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER NOT NULL,
            batch_id INTEGER,
            run_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            search_string TEXT,
            source_user TEXT,
            source_file TEXT,
            download_path TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            last_error TEXT,
            score REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE,
            FOREIGN KEY(batch_id) REFERENCES ingestion_batches(id) ON DELETE SET NULL,
            FOREIGN KEY(run_id) REFERENCES pipeline_runs(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_downloads_track ON downloads(track_id);
        CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
        CREATE INDEX IF NOT EXISTS idx_ingestion_batches_label ON ingestion_batches(label);
        CREATE INDEX IF NOT EXISTS idx_track_ingestions_batch ON track_ingestions(batch_id, track_id);
        CREATE INDEX IF NOT EXISTS idx_exportify_batch_row ON exportify_tracks(batch_id, row_index);
        CREATE INDEX IF NOT EXISTS idx_library_files_track ON library_files(track_id);
        CREATE INDEX IF NOT EXISTS idx_track_stage_stage_status ON track_stage_state(stage, status);
        """
        self.conn.executescript(schema)
        self.conn.commit()
        # Additive columns on library_files — SQLite does not support IF NOT EXISTS on ALTER TABLE
        for col_sql in (
            "ALTER TABLE library_files ADD COLUMN fingerprint_status TEXT",
            "ALTER TABLE library_files ADD COLUMN content_hash TEXT",
        ):
            try:
                self.conn.execute(col_sql)
                self.conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Additive metadata + operational columns on tracks (source of truth)
        for col_sql in (
            "ALTER TABLE tracks ADD COLUMN bpm INTEGER DEFAULT 0",
            "ALTER TABLE tracks ADD COLUMN energy REAL",
            "ALTER TABLE tracks ADD COLUMN danceability REAL",
            "ALTER TABLE tracks ADD COLUMN style TEXT",
            "ALTER TABLE tracks ADD COLUMN genres TEXT",
            "ALTER TABLE tracks ADD COLUMN metadata_source TEXT",
            "ALTER TABLE tracks ADD COLUMN status TEXT DEFAULT 'imported'",
            "ALTER TABLE tracks ADD COLUMN file_path TEXT",
        ):
            try:
                self.conn.execute(col_sql)
                self.conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists

    def create_ingestion_batch(
        self,
        *,
        source_type: str,
        import_method: Optional[str] = None,
        label: Optional[str] = None,
        source_ref: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO ingestion_batches (
                batch_uuid, source_type, import_method, label, source_ref, created_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                source_type,
                import_method,
                label,
                source_ref,
                utc_now(),
                notes,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_batch(self, batch_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM ingestion_batches WHERE id = ?",
            (int(batch_id),),
        ).fetchone()

    def get_latest_batch(
        self,
        *,
        source_type: Optional[str] = None,
        label: Optional[str] = None,
    ) -> Optional[sqlite3.Row]:
        where = []
        params: list[Any] = []
        if source_type:
            where.append("source_type = ?")
            params.append(source_type)
        if label:
            where.append("label = ?")
            params.append(label)
        sql = "SELECT * FROM ingestion_batches"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT 1"
        return self.conn.execute(sql, tuple(params)).fetchone()

    def resolve_batch_ids(
        self,
        *,
        batch_id: Optional[int] = None,
        label: Optional[str] = None,
        source_type: Optional[str] = None,
        latest_if_empty: bool = False,
    ) -> list[int]:
        if batch_id is not None:
            return [int(batch_id)]
        where = []
        params: list[Any] = []
        if label:
            where.append("label = ?")
            params.append(label)
        if source_type:
            where.append("source_type = ?")
            params.append(source_type)
        sql = "SELECT id FROM ingestion_batches"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC"
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        ids = [int(row["id"]) for row in rows]
        if ids or not latest_if_empty:
            return ids
        latest = self.get_latest_batch(source_type=source_type)
        return [int(latest["id"])] if latest else []

    def start_run(
        self,
        *,
        script_name: str,
        input_path: Optional[str] = None,
        output_path: Optional[str] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> int:
        run_uuid = str(uuid.uuid4())
        now = utc_now()
        cur = self.conn.execute(
            """
            INSERT INTO pipeline_runs (
                run_uuid, script_name, started_at, status, input_path, output_path, options_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_uuid,
                script_name,
                now,
                "running",
                input_path,
                output_path,
                json.dumps(options or {}, ensure_ascii=True),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        total_count: int = 0,
        success_count: int = 0,
        skipped_count: int = 0,
        error_count: int = 0,
        notes: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE pipeline_runs
            SET ended_at = ?, status = ?, total_count = ?, success_count = ?, skipped_count = ?, error_count = ?, notes = ?
            WHERE id = ?
            """,
            (
                utc_now(),
                status,
                int(total_count),
                int(success_count),
                int(skipped_count),
                int(error_count),
                notes,
                int(run_id),
            ),
        )
        self.conn.commit()

    def upsert_track(
        self,
        *,
        track_key: str,
        artist: Optional[str] = None,
        title: Optional[str] = None,
        album: Optional[str] = None,
        isrc: Optional[str] = None,
        duration_ms: Optional[int] = None,
        source_search_string: Optional[str] = None,
        source_csv: Optional[str] = None,
    ) -> int:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO tracks (
                track_key, artist, title, album, isrc, duration_ms, source_search_string, source_csv, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(track_key) DO UPDATE SET
                artist = COALESCE(excluded.artist, tracks.artist),
                title = COALESCE(excluded.title, tracks.title),
                album = COALESCE(excluded.album, tracks.album),
                isrc = COALESCE(excluded.isrc, tracks.isrc),
                duration_ms = COALESCE(excluded.duration_ms, tracks.duration_ms),
                source_search_string = COALESCE(excluded.source_search_string, tracks.source_search_string),
                source_csv = COALESCE(excluded.source_csv, tracks.source_csv),
                last_seen_at = excluded.last_seen_at
            """,
            (
                track_key,
                artist,
                title,
                album,
                isrc,
                duration_ms,
                source_search_string,
                source_csv,
                now,
                now,
            ),
        )
        row = self.conn.execute(
            "SELECT id FROM tracks WHERE track_key = ?",
            (track_key,),
        ).fetchone()
        self.conn.commit()
        return int(row["id"])

    def update_track_metadata(
        self,
        track_id: int,
        *,
        bpm: Optional[int] = None,
        energy: Optional[float] = None,
        danceability: Optional[float] = None,
        style: Optional[str] = None,
        genres: Optional[str] = None,
        metadata_source: Optional[str] = None,
    ) -> None:
        """Update metadata columns on the tracks table. Only provided (non-None) values are written."""
        fields: dict[str, Any] = {}
        if bpm is not None:
            fields["bpm"] = bpm
        if energy is not None:
            fields["energy"] = energy
        if danceability is not None:
            fields["danceability"] = danceability
        if style is not None:
            fields["style"] = style
        if genres is not None:
            fields["genres"] = genres
        if metadata_source is not None:
            fields["metadata_source"] = metadata_source
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE tracks SET {set_clause} WHERE id = ?",
            (*fields.values(), track_id),
        )
        self.conn.commit()

    def update_track_status(
        self,
        track_id: int,
        *,
        status: str,
        file_path: Optional[str] = None,
    ) -> None:
        """Update the operational status (and optionally file_path) on the tracks table."""
        if file_path is not None:
            self.conn.execute(
                "UPDATE tracks SET status = ?, file_path = ? WHERE id = ?",
                (status, file_path, track_id),
            )
        else:
            self.conn.execute(
                "UPDATE tracks SET status = ? WHERE id = ?",
                (status, track_id),
            )
        self.conn.commit()

    def get_track_id_by_key(self, track_key: str) -> Optional[int]:
        row = self.conn.execute(
            "SELECT id FROM tracks WHERE track_key = ?",
            (track_key,),
        ).fetchone()
        if not row:
            return None
        return int(row["id"])

    def add_playlist_entry(
        self,
        *,
        run_id: Optional[int],
        track_id: Optional[int],
        source_csv: Optional[str],
        row_index: int,
        artist: Optional[str],
        title: Optional[str],
        search_string: Optional[str],
        raw_row: Optional[dict[str, Any]] = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO playlist_entries (
                run_id, track_id, source_csv, row_index, artist, title, search_string, raw_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                track_id,
                source_csv,
                row_index,
                artist,
                title,
                search_string,
                json.dumps(raw_row or {}, ensure_ascii=True),
                utc_now(),
            ),
        )
        self.conn.commit()

    def upsert_track_ingestion(
        self,
        *,
        track_id: int,
        batch_id: int,
        source_type: str,
        import_method: Optional[str] = None,
        row_index: Optional[int] = None,
        is_new_track: bool = False,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO track_ingestions (
                track_id, batch_id, source_type, import_method, row_index, is_new_track, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(track_id, batch_id, source_type, row_index) DO UPDATE SET
                import_method = COALESCE(excluded.import_method, track_ingestions.import_method),
                is_new_track = MAX(track_ingestions.is_new_track, excluded.is_new_track)
            """,
            (
                int(track_id),
                int(batch_id),
                source_type,
                import_method,
                int(row_index) if row_index is not None else -1,
                1 if is_new_track else 0,
                utc_now(),
            ),
        )
        self.conn.commit()

    def upsert_track_stage_state(
        self,
        *,
        track_id: int,
        stage: str,
        status: str,
        run_id: Optional[int] = None,
        batch_id: Optional[int] = None,
        method: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO track_stage_state (
                track_id, stage, status, run_id, batch_id, method, details_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(track_id, stage) DO UPDATE SET
                status = excluded.status,
                run_id = COALESCE(excluded.run_id, track_stage_state.run_id),
                batch_id = COALESCE(excluded.batch_id, track_stage_state.batch_id),
                method = COALESCE(excluded.method, track_stage_state.method),
                details_json = COALESCE(excluded.details_json, track_stage_state.details_json),
                updated_at = excluded.updated_at
            """,
            (
                int(track_id),
                stage,
                status,
                run_id,
                batch_id,
                method,
                json.dumps(details or {}, ensure_ascii=True),
                utc_now(),
            ),
        )
        self.conn.commit()

    def upsert_exportify_track(
        self,
        *,
        batch_id: int,
        track_id: Optional[int],
        source_csv: Optional[str],
        row_index: int,
        row: dict[str, Any],
    ) -> None:
        def _num(value: Any) -> Optional[float]:
            if value is None or value == "":
                return None
            try:
                return float(value)
            except Exception:
                return None

        def _int(value: Any) -> Optional[int]:
            n = _num(value)
            return int(n) if n is not None else None

        self.conn.execute(
            """
            INSERT INTO exportify_tracks (
                batch_id, track_id, source_csv, row_index, track_uri, track_name, album_name, artist_names,
                release_date, duration_ms, popularity, explicit, added_by, added_at, genres, record_label,
                danceability, energy, key_value, loudness, mode_value, speechiness, acousticness, instrumentalness,
                liveness, valence, tempo, time_signature, raw_row_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(batch_id),
                track_id,
                source_csv,
                int(row_index),
                row.get("Track URI"),
                row.get("Track Name"),
                row.get("Album Name"),
                row.get("Artist Name(s)"),
                row.get("Release Date"),
                _int(row.get("Duration (ms)")),
                _int(row.get("Popularity")),
                str(row.get("Explicit")) if row.get("Explicit") is not None else None,
                row.get("Added By"),
                row.get("Added At"),
                row.get("Genres"),
                row.get("Record Label"),
                _num(row.get("Danceability")),
                _num(row.get("Energy")),
                row.get("Key"),
                _num(row.get("Loudness")),
                str(row.get("Mode")) if row.get("Mode") is not None else None,
                _num(row.get("Speechiness")),
                _num(row.get("Acousticness")),
                _num(row.get("Instrumentalness")),
                _num(row.get("Liveness")),
                _num(row.get("Valence")),
                _num(row.get("Tempo")),
                str(row.get("Time Signature")) if row.get("Time Signature") is not None else None,
                json.dumps(row, ensure_ascii=True),
                utc_now(),
            ),
        )
        self.conn.commit()

    def get_exportify_rows(
        self,
        *,
        batch_id: Optional[int] = None,
        label: Optional[str] = None,
        scope: str = "new",
    ) -> tuple[Optional[int], list[dict[str, Any]]]:
        resolved_batch_id = batch_id
        if resolved_batch_id is None:
            if label:
                rows = self.conn.execute(
                    "SELECT id FROM ingestion_batches WHERE label = ? ORDER BY id DESC LIMIT 1",
                    (label,),
                ).fetchone()
                if rows:
                    resolved_batch_id = int(rows["id"])
            else:
                latest = self.get_latest_batch(source_type="exportify_csv")
                if latest:
                    resolved_batch_id = int(latest["id"])

        if resolved_batch_id is None:
            return None, []

        where = []
        params: list[Any] = []
        if scope == "new":
            where.append("et.batch_id = ?")
            params.append(int(resolved_batch_id))
        elif scope == "existing":
            where.append("et.batch_id != ?")
            params.append(int(resolved_batch_id))
        elif scope == "all":
            pass
        else:
            raise ValueError(f"Unsupported scope: {scope}")

        sql = "SELECT et.raw_row_json FROM exportify_tracks et"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY et.id ASC"
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            raw = row["raw_row_json"]
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            if isinstance(parsed, dict):
                out.append(parsed)
        if not out:
            legacy_source, legacy_rows = self.get_latest_playlist_rows()
            if legacy_rows:
                return resolved_batch_id, legacy_rows
        return resolved_batch_id, out

    def upsert_library_file(
        self,
        *,
        path: str,
        filename: Optional[str] = None,
        extension: Optional[str] = None,
        size_bytes: Optional[int] = None,
        duration_ms: Optional[int] = None,
        bitrate_kbps: Optional[int] = None,
        sample_rate: Optional[int] = None,
        bit_depth: Optional[int] = None,
        artist_tag: Optional[str] = None,
        title_tag: Optional[str] = None,
        album_tag: Optional[str] = None,
        batch_id: Optional[int] = None,
        track_id: Optional[int] = None,
        source_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO library_files (
                batch_id, track_id, path, filename, extension, size_bytes, duration_ms, bitrate_kbps, sample_rate,
                bit_depth, artist_tag, title_tag, album_tag, source_type, status, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                batch_id = COALESCE(excluded.batch_id, library_files.batch_id),
                track_id = COALESCE(excluded.track_id, library_files.track_id),
                filename = COALESCE(excluded.filename, library_files.filename),
                extension = COALESCE(excluded.extension, library_files.extension),
                size_bytes = COALESCE(excluded.size_bytes, library_files.size_bytes),
                duration_ms = COALESCE(excluded.duration_ms, library_files.duration_ms),
                bitrate_kbps = COALESCE(excluded.bitrate_kbps, library_files.bitrate_kbps),
                sample_rate = COALESCE(excluded.sample_rate, library_files.sample_rate),
                bit_depth = COALESCE(excluded.bit_depth, library_files.bit_depth),
                artist_tag = COALESCE(excluded.artist_tag, library_files.artist_tag),
                title_tag = COALESCE(excluded.title_tag, library_files.title_tag),
                album_tag = COALESCE(excluded.album_tag, library_files.album_tag),
                source_type = COALESCE(excluded.source_type, library_files.source_type),
                status = COALESCE(excluded.status, library_files.status),
                last_seen_at = excluded.last_seen_at
            """,
            (
                batch_id,
                track_id,
                path,
                filename,
                extension,
                size_bytes,
                duration_ms,
                bitrate_kbps,
                sample_rate,
                bit_depth,
                artist_tag,
                title_tag,
                album_tag,
                source_type,
                status,
                now,
                now,
            ),
        )
        self.conn.commit()

    def _resolve_scope_batch(self, scope: str, batch_id: Optional[int], label: Optional[str], source_type: Optional[str]) -> Optional[int]:
        resolved_batch_id = batch_id
        if resolved_batch_id is None:
            latest = self.get_latest_batch(source_type=source_type, label=label)
            if latest:
                resolved_batch_id = int(latest["id"])
        if scope in ("new", "existing") and resolved_batch_id is None:
            return None
        return resolved_batch_id

    def get_tracks_by_scope(
        self,
        *,
        scope: str = "new",
        batch_id: Optional[int] = None,
        label: Optional[str] = None,
        source_type: Optional[str] = None,
        require_search_string: bool = True,
    ) -> list[sqlite3.Row]:
        if scope not in {"new", "existing", "all"}:
            raise ValueError("scope must be one of: new, existing, all")
        resolved_batch = self._resolve_scope_batch(scope, batch_id, label, source_type)
        if scope in {"new", "existing"} and resolved_batch is None:
            return []

        where = []
        params: list[Any] = []
        if require_search_string:
            where.append("t.source_search_string IS NOT NULL AND t.source_search_string != ''")

        if scope == "new":
            where.append(
                """
                EXISTS (
                    SELECT 1 FROM track_ingestions ti
                    JOIN ingestion_batches ib ON ib.id = ti.batch_id
                    WHERE ti.track_id = t.id AND ti.batch_id = ?
                )
                """
            )
            params.append(int(resolved_batch))
        elif scope == "existing":
            where.append(
                """
                NOT EXISTS (
                    SELECT 1 FROM track_ingestions ti
                    WHERE ti.track_id = t.id AND ti.batch_id = ?
                )
                """
            )
            params.append(int(resolved_batch))

        if label and scope == "all":
            where.append(
                """
                EXISTS (
                    SELECT 1 FROM track_ingestions ti2
                    JOIN ingestion_batches ib2 ON ib2.id = ti2.batch_id
                    WHERE ti2.track_id = t.id AND ib2.label = ?
                )
                """
            )
            params.append(label)
        if source_type:
            where.append(
                """
                EXISTS (
                    SELECT 1 FROM track_ingestions ti3
                    JOIN ingestion_batches ib3 ON ib3.id = ti3.batch_id
                    WHERE ti3.track_id = t.id AND ib3.source_type = ?
                )
                """
            )
            params.append(source_type)

        sql = """
        SELECT t.*
        FROM tracks t
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY t.id"
        return self.conn.execute(sql, tuple(params)).fetchall()

    def get_pending_download_queries_v2(
        self,
        *,
        limit: Optional[int] = None,
        scope: str = "new",
        batch_id: Optional[int] = None,
        label: Optional[str] = None,
    ) -> list[tuple[int, str]]:
        if scope not in {"new", "existing", "all"}:
            raise ValueError("scope must be one of: new, existing, all")
        resolved_batch = self._resolve_scope_batch(scope, batch_id, label, "exportify_csv")
        if scope in {"new", "existing"} and resolved_batch is None:
            return []

        where = [
            "t.source_search_string IS NOT NULL",
            "t.source_search_string != ''",
            """
            EXISTS (
                SELECT 1
                FROM track_stage_state ts
                WHERE ts.track_id = t.id
                  AND ts.stage = 'candidate_generation'
                  AND ts.status = 'candidate_generated'
            )
            """,
            """
            NOT EXISTS (
                SELECT 1
                FROM track_stage_state ts2
                WHERE ts2.track_id = t.id
                  AND ts2.stage = 'slskd_queue'
                  AND ts2.status IN ('download_queued', 'download_dry_run_queued')
            )
            """,
        ]
        params: list[Any] = []

        if scope == "new":
            where.append(
                """
                EXISTS (
                    SELECT 1 FROM track_ingestions ti
                    WHERE ti.track_id = t.id AND ti.batch_id = ?
                )
                """
            )
            params.append(int(resolved_batch))
        elif scope == "existing":
            where.append(
                """
                NOT EXISTS (
                    SELECT 1 FROM track_ingestions ti
                    WHERE ti.track_id = t.id AND ti.batch_id = ?
                )
                """
            )
            params.append(int(resolved_batch))

        if label and scope == "all":
            where.append(
                """
                EXISTS (
                    SELECT 1 FROM track_ingestions ti2
                    JOIN ingestion_batches ib2 ON ib2.id = ti2.batch_id
                    WHERE ti2.track_id = t.id AND ib2.label = ?
                )
                """
            )
            params.append(label)

        sql = "SELECT t.id, t.source_search_string FROM tracks t WHERE " + " AND ".join(where) + " ORDER BY t.id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))

        rows = self.conn.execute(sql, tuple(params)).fetchall()
        return [(int(row["id"]), str(row["source_search_string"])) for row in rows]

    def add_event(
        self,
        *,
        run_id: Optional[int],
        track_id: Optional[int],
        stage: str,
        status: str,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        file_path: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO track_events (
                run_id, track_id, stage, status, message, details_json, file_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                track_id,
                stage,
                status,
                message,
                json.dumps(details or {}, ensure_ascii=True),
                file_path,
                utc_now(),
            ),
        )
        self.conn.commit()

    def upsert_asset(
        self,
        *,
        run_id: Optional[int],
        track_id: Optional[int],
        asset_type: str,
        path: str,
        origin: Optional[str] = None,
        status: Optional[str] = None,
        size_bytes: Optional[int] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO assets (
                track_id, run_id, asset_type, path, origin, status, size_bytes, extra_json, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_type, path) DO UPDATE SET
                track_id = COALESCE(excluded.track_id, assets.track_id),
                run_id = COALESCE(excluded.run_id, assets.run_id),
                origin = COALESCE(excluded.origin, assets.origin),
                status = COALESCE(excluded.status, assets.status),
                size_bytes = COALESCE(excluded.size_bytes, assets.size_bytes),
                extra_json = COALESCE(excluded.extra_json, assets.extra_json),
                last_seen_at = excluded.last_seen_at
            """,
            (
                track_id,
                run_id,
                asset_type,
                path,
                origin,
                status,
                size_bytes,
                json.dumps(extra or {}, ensure_ascii=True),
                now,
                now,
            ),
        )
        self.conn.commit()

    def add_duplicate_decision(
        self,
        *,
        run_id: Optional[int],
        group_id: int,
        track_id: Optional[int],
        role: str,
        action: str,
        origin: Optional[str],
        path: str,
        target_path: Optional[str],
        keep_path: Optional[str],
        keep_strategy: Optional[str],
        reason: Optional[str],
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO duplicate_decisions (
                run_id, group_id, track_id, role, action, origin, path, target_path, keep_path, keep_strategy, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                group_id,
                track_id,
                role,
                action,
                origin,
                path,
                target_path,
                keep_path,
                keep_strategy,
                reason,
                utc_now(),
            ),
        )
        self.conn.commit()

    def get_pending_download_queries(self, limit: Optional[int] = None) -> list[tuple[int, str]]:
        sql = """
        SELECT t.id, t.source_search_string
        FROM tracks t
        WHERE t.source_search_string IS NOT NULL
          AND t.source_search_string != ''
          AND (
              EXISTS (
                  SELECT 1
                  FROM track_events e
                  WHERE e.track_id = t.id
                    AND e.stage = 'candidate_generation'
                    AND e.status = 'candidate_generated'
              )
              OR EXISTS (
                  SELECT 1
                  FROM track_stage_state ts
                  WHERE ts.track_id = t.id
                    AND ts.stage = 'candidate_generation'
                    AND ts.status = 'candidate_generated'
              )
          )
          AND NOT (
              EXISTS (
                  SELECT 1
                  FROM track_events e2
                  WHERE e2.track_id = t.id
                    AND e2.stage = 'slskd_queue'
                    AND e2.status IN ('download_queued', 'download_dry_run_queued')
              )
              OR EXISTS (
                  SELECT 1
                  FROM track_stage_state ts2
                  WHERE ts2.track_id = t.id
                    AND ts2.stage = 'slskd_queue'
                    AND ts2.status IN ('download_queued', 'download_dry_run_queued')
              )
          )
        ORDER BY t.id
        """
        params: list[Any] = []
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        return [(int(row["id"]), str(row["source_search_string"])) for row in rows]

    def upsert_fingerprint(
        self,
        *,
        library_file_id: int,
        track_id: Optional[int],
        fpcalc_fingerprint: Optional[str],
        fpcalc_duration_sec: Optional[float],
        acoustid_id: Optional[str] = None,
        acoustid_score: Optional[float] = None,
        acoustid_recording_id: Optional[str] = None,
        acoustid_title: Optional[str] = None,
        acoustid_artist: Optional[str] = None,
        fingerprint_method: str = "fpcalc",
        status: str = "computed",
    ) -> None:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO library_fingerprints (
                library_file_id, track_id, fpcalc_fingerprint, fpcalc_duration_sec,
                acoustid_id, acoustid_score, acoustid_recording_id,
                acoustid_title, acoustid_artist, fingerprint_method, status, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(library_file_id) DO UPDATE SET
                track_id = COALESCE(excluded.track_id, library_fingerprints.track_id),
                fpcalc_fingerprint = COALESCE(excluded.fpcalc_fingerprint, library_fingerprints.fpcalc_fingerprint),
                fpcalc_duration_sec = COALESCE(excluded.fpcalc_duration_sec, library_fingerprints.fpcalc_duration_sec),
                acoustid_id = COALESCE(excluded.acoustid_id, library_fingerprints.acoustid_id),
                acoustid_score = COALESCE(excluded.acoustid_score, library_fingerprints.acoustid_score),
                acoustid_recording_id = COALESCE(excluded.acoustid_recording_id, library_fingerprints.acoustid_recording_id),
                acoustid_title = COALESCE(excluded.acoustid_title, library_fingerprints.acoustid_title),
                acoustid_artist = COALESCE(excluded.acoustid_artist, library_fingerprints.acoustid_artist),
                fingerprint_method = excluded.fingerprint_method,
                status = excluded.status,
                computed_at = excluded.computed_at
            """,
            (
                int(library_file_id),
                track_id,
                fpcalc_fingerprint,
                fpcalc_duration_sec,
                acoustid_id,
                acoustid_score,
                acoustid_recording_id,
                acoustid_title,
                acoustid_artist,
                fingerprint_method,
                status,
                now,
            ),
        )
        self.conn.execute(
            "UPDATE library_files SET fingerprint_status = ? WHERE id = ?",
            (status, int(library_file_id)),
        )
        self.conn.commit()

    def get_library_file_by_path(self, path: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM library_files WHERE path = ?",
            (path,),
        ).fetchone()

    def find_matching_fingerprint(
        self,
        fpcalc_fingerprint: str,
        duration_sec: float,
        *,
        duration_tolerance_sec: float = 5.0,
    ) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT lf.*, fp.acoustid_id, fp.acoustid_title, fp.acoustid_artist
            FROM library_fingerprints fp
            JOIN library_files lf ON lf.id = fp.library_file_id
            WHERE fp.fpcalc_fingerprint = ?
              AND fp.fpcalc_duration_sec IS NOT NULL
              AND ABS(fp.fpcalc_duration_sec - ?) <= ?
            LIMIT 1
            """,
            (fpcalc_fingerprint, float(duration_sec), float(duration_tolerance_sec)),
        ).fetchone()

    def get_unfingerprinted_library_files(
        self,
        *,
        batch_id: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[sqlite3.Row]:
        where = [
            """
            NOT EXISTS (
                SELECT 1 FROM library_fingerprints fp WHERE fp.library_file_id = lf.id
            )
            """
        ]
        params: list[Any] = []
        if batch_id is not None:
            where.append("lf.batch_id = ?")
            params.append(int(batch_id))
        sql = "SELECT lf.* FROM library_files lf WHERE " + " AND ".join(where) + " ORDER BY lf.id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return self.conn.execute(sql, tuple(params)).fetchall()

    def get_latest_playlist_rows(self, source_csv: Optional[str] = None) -> tuple[Optional[str], list[dict[str, Any]]]:
        rows: list[sqlite3.Row] = []
        selected_source_csv = source_csv

        if source_csv:
            rows = self.conn.execute(
                """
                SELECT raw_json, source_csv
                FROM playlist_entries
                WHERE source_csv = ?
                ORDER BY row_index ASC, id ASC
                """,
                (source_csv,),
            ).fetchall()
        else:
            latest_run = self.conn.execute(
                """
                SELECT id, input_path
                FROM pipeline_runs
                WHERE script_name = 'csv_to_dj_pipeline.py'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            if latest_run:
                rows = self.conn.execute(
                    """
                    SELECT raw_json, source_csv
                    FROM playlist_entries
                    WHERE run_id = ?
                    ORDER BY row_index ASC, id ASC
                    """,
                    (int(latest_run["id"]),),
                ).fetchall()
                selected_source_csv = latest_run["input_path"] or None

            if not rows:
                latest_source = self.conn.execute(
                    """
                    SELECT source_csv
                    FROM playlist_entries
                    WHERE source_csv IS NOT NULL AND source_csv != ''
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()
                if latest_source and latest_source["source_csv"]:
                    selected_source_csv = str(latest_source["source_csv"])
                    rows = self.conn.execute(
                        """
                        SELECT raw_json, source_csv
                        FROM playlist_entries
                        WHERE source_csv = ?
                        ORDER BY row_index ASC, id ASC
                        """,
                        (selected_source_csv,),
                    ).fetchall()

        decoded: list[dict[str, Any]] = []
        for row in rows:
            raw_json = row["raw_json"]
            if not raw_json:
                continue
            try:
                parsed = json.loads(raw_json)
            except Exception:
                continue
            if isinstance(parsed, dict):
                decoded.append(parsed)
            if not selected_source_csv and row["source_csv"]:
                selected_source_csv = str(row["source_csv"])

        return selected_source_csv, decoded

    # ------------------------------------------------------------------ #
    # Downloads state machine                                              #
    # ------------------------------------------------------------------ #

    def create_download(
        self,
        *,
        track_id: int,
        batch_id: Optional[int] = None,
        run_id: Optional[int] = None,
        search_string: Optional[str] = None,
        max_retries: int = 3,
    ) -> int:
        now = utc_now()
        cur = self.conn.execute(
            """
            INSERT INTO downloads
                (track_id, batch_id, run_id, status, search_string, max_retries, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (int(track_id), batch_id, run_id, search_string, int(max_retries), now, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_download(
        self,
        download_id: int,
        *,
        status: str,
        source_user: Optional[str] = None,
        source_file: Optional[str] = None,
        download_path: Optional[str] = None,
        last_error: Optional[str] = None,
        score: Optional[float] = None,
    ) -> None:
        sets = ["status = ?", "updated_at = ?"]
        params: list[Any] = [status, utc_now()]
        if source_user is not None:
            sets.append("source_user = ?")
            params.append(source_user)
        if source_file is not None:
            sets.append("source_file = ?")
            params.append(source_file)
        if download_path is not None:
            sets.append("download_path = ?")
            params.append(download_path)
        if last_error is not None:
            sets.append("last_error = ?")
            params.append(last_error)
        if score is not None:
            sets.append("score = ?")
            params.append(float(score))
        params.append(int(download_id))
        self.conn.execute(
            f"UPDATE downloads SET {', '.join(sets)} WHERE id = ?",
            tuple(params),
        )
        self.conn.commit()

    def get_downloads_for_retry(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM downloads
            WHERE status = 'failed' AND retry_count < max_retries
            ORDER BY created_at ASC
            """
        ).fetchall()

    def get_failed_downloads(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT d.*, t.artist, t.title
            FROM downloads d
            LEFT JOIN tracks t ON t.id = d.track_id
            WHERE d.status = 'failed' AND d.retry_count >= d.max_retries
            ORDER BY d.created_at ASC
            """
        ).fetchall()

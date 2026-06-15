import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from intellidj_db import IntelliDJDB
from scripts.check_db_integrity import (
    check_assets,
    check_completed_downloads,
    check_library_files,
    check_tracks_without_files,
    check_untracked_files_vs_db,
)


@pytest.fixture
def db(tmp_path):
    d = IntelliDJDB(str(tmp_path / "test.db"))
    yield d
    d.close()


def _insert_library_file(db: IntelliDJDB, path: str, status: str = "indexed") -> int:
    db.conn.execute(
        """
        INSERT INTO library_files (path, filename, extension, status, first_seen_at, last_seen_at)
        VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (path, Path(path).name, Path(path).suffix, status),
    )
    db.conn.commit()
    return db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_asset(db: IntelliDJDB, path: str, status: str = "indexed") -> int:
    db.conn.execute(
        """
        INSERT INTO assets (asset_type, path, status, first_seen_at, last_seen_at)
        VALUES ('library_file', ?, ?, datetime('now'), datetime('now'))
        """,
        (path, status),
    )
    db.conn.commit()
    return db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_track(db: IntelliDJDB, artist: str = "A", title: str = "T") -> int:
    db.conn.execute(
        """
        INSERT INTO tracks (track_key, artist, title, first_seen_at, last_seen_at)
        VALUES (?, ?, ?, datetime('now'), datetime('now'))
        """,
        (f"meta:{artist}|{title}", artist, title),
    )
    db.conn.commit()
    return db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_download(db: IntelliDJDB, track_id: int, status: str, download_path: str | None) -> int:
    db.conn.execute(
        """
        INSERT INTO downloads
            (track_id, status, search_string, download_path, max_retries, retry_count, created_at, updated_at)
        VALUES (?, ?, 'search', ?, 3, 0, datetime('now'), datetime('now'))
        """,
        (track_id, status, download_path),
    )
    db.conn.commit()
    return db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# ---------------------------------------------------------------------------
# check_library_files
# ---------------------------------------------------------------------------


def test_library_files_no_issues(db, tmp_path):
    real_file = tmp_path / "track.mp3"
    real_file.write_bytes(b"")
    _insert_library_file(db, str(real_file))

    result = check_library_files(db, fix=False)
    assert result.issue_count == 0
    assert result.total_checked == 1


def test_library_files_detects_missing(db, tmp_path):
    _insert_library_file(db, str(tmp_path / "ghost.mp3"))

    result = check_library_files(db, fix=False)
    assert result.issue_count == 1
    assert result.issues[0]["path"] == str(tmp_path / "ghost.mp3")


def test_library_files_skips_already_missing_status(db, tmp_path):
    _insert_library_file(db, str(tmp_path / "ghost.mp3"), status="missing")

    result = check_library_files(db, fix=False)
    assert result.issue_count == 0


def test_library_files_fix_marks_missing(db, tmp_path):
    _insert_library_file(db, str(tmp_path / "gone.mp3"))

    result = check_library_files(db, fix=True)
    assert result.issue_count == 1
    assert result.fixed == 1

    row = db.conn.execute("SELECT status FROM library_files WHERE path = ?", (str(tmp_path / "gone.mp3"),)).fetchone()
    assert row["status"] == "missing"


# ---------------------------------------------------------------------------
# check_assets
# ---------------------------------------------------------------------------


def test_assets_no_issues(db, tmp_path):
    real_file = tmp_path / "track.flac"
    real_file.write_bytes(b"")
    _insert_asset(db, str(real_file))

    result = check_assets(db, fix=False)
    assert result.issue_count == 0


def test_assets_detects_missing(db, tmp_path):
    _insert_asset(db, str(tmp_path / "ghost.flac"))

    result = check_assets(db, fix=False)
    assert result.issue_count == 1


def test_assets_fix_marks_missing(db, tmp_path):
    _insert_asset(db, str(tmp_path / "gone.flac"))

    result = check_assets(db, fix=True)
    assert result.fixed == 1

    row = db.conn.execute("SELECT status FROM assets WHERE path = ?", (str(tmp_path / "gone.flac"),)).fetchone()
    assert row["status"] == "missing"


def test_assets_skips_already_missing(db, tmp_path):
    _insert_asset(db, str(tmp_path / "already.flac"), status="missing")
    result = check_assets(db, fix=False)
    assert result.issue_count == 0


# ---------------------------------------------------------------------------
# check_completed_downloads
# ---------------------------------------------------------------------------


def test_completed_downloads_no_issues(db, tmp_path):
    real_file = tmp_path / "dl.mp3"
    real_file.write_bytes(b"")
    track_id = _insert_track(db)
    _insert_download(db, track_id, "completed", str(real_file))

    result = check_completed_downloads(db, fix=False)
    assert result.issue_count == 0


def test_completed_downloads_detects_missing(db, tmp_path):
    track_id = _insert_track(db)
    _insert_download(db, track_id, "completed", str(tmp_path / "gone.mp3"))

    result = check_completed_downloads(db, fix=False)
    assert result.issue_count == 1


def test_completed_downloads_ignores_other_statuses(db, tmp_path):
    track_id = _insert_track(db)
    # pending download with no path — should not appear
    _insert_download(db, track_id, "pending", None)

    result = check_completed_downloads(db, fix=False)
    assert result.issue_count == 0


def test_completed_downloads_fix_resets_to_pending(db, tmp_path):
    track_id = _insert_track(db)
    dl_id = _insert_download(db, track_id, "completed", str(tmp_path / "gone.mp3"))

    result = check_completed_downloads(db, fix=True)
    assert result.fixed == 1

    row = db.conn.execute("SELECT status, retry_count FROM downloads WHERE id = ?", (dl_id,)).fetchone()
    assert row["status"] == "pending"
    assert row["retry_count"] == 1


# ---------------------------------------------------------------------------
# check_tracks_without_files
# ---------------------------------------------------------------------------


def test_tracks_without_files_detects_orphan(db, tmp_path):
    _insert_track(db, "Artist", "Title")

    result = check_tracks_without_files(db)
    assert result.issue_count == 1
    assert result.issues[0]["artist"] == "Artist"


def test_tracks_without_files_ok_when_linked(db, tmp_path):
    real_file = tmp_path / "track.mp3"
    real_file.write_bytes(b"")
    track_id = _insert_track(db)
    # Link the library_file to the track
    db.conn.execute(
        """
        INSERT INTO library_files (track_id, path, filename, extension, status, first_seen_at, last_seen_at)
        VALUES (?, ?, ?, ?, 'indexed', datetime('now'), datetime('now'))
        """,
        (track_id, str(real_file), real_file.name, real_file.suffix),
    )
    db.conn.commit()

    result = check_tracks_without_files(db)
    assert result.issue_count == 0


# ---------------------------------------------------------------------------
# check_untracked_files_vs_db
# ---------------------------------------------------------------------------


def test_untracked_files_empty_dir(db, tmp_path):
    result = check_untracked_files_vs_db(db, [tmp_path])
    assert result.issue_count == 0


def test_untracked_files_detects_unregistered(db, tmp_path):
    (tmp_path / "unknown.mp3").write_bytes(b"")
    result = check_untracked_files_vs_db(db, [tmp_path])
    assert result.issue_count == 1


def test_untracked_files_skips_known(db, tmp_path):
    f = tmp_path / "known.flac"
    f.write_bytes(b"")
    _insert_library_file(db, str(f))
    result = check_untracked_files_vs_db(db, [tmp_path])
    assert result.issue_count == 0


def test_untracked_files_no_scan_dirs(db):
    result = check_untracked_files_vs_db(db, [])
    assert result.issue_count == 0
    assert result.total_checked == 0

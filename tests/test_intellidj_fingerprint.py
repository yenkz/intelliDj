from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import intellidj_fingerprint as mod
from intellidj_db import IntelliDJDB, make_track_key


def test_fingerprint_file_raises_if_fpcalc_missing():
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="fpcalc not found"):
            mod.fingerprint_file(Path("/tmp/test.flac"))


def test_fingerprint_file_returns_none_on_nonzero_exit():
    with patch("shutil.which", return_value="/usr/bin/fpcalc"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
            fp, dur = mod.fingerprint_file(Path("/tmp/test.flac"))
    assert fp is None
    assert dur is None


def test_fingerprint_file_parses_output():
    fake_output = "DURATION=234.5\nFINGERPRINT=1234567890abcdef"
    with patch("shutil.which", return_value="/usr/bin/fpcalc"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=fake_output)
            fp, dur = mod.fingerprint_file(Path("/tmp/test.flac"))
    assert fp == "1234567890abcdef"
    assert dur == pytest.approx(234.5)


def test_fingerprint_file_handles_timeout():
    import subprocess

    with patch("shutil.which", return_value="/usr/bin/fpcalc"):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("fpcalc", 30)):
            fp, dur = mod.fingerprint_file(Path("/tmp/test.flac"))
    assert fp is None
    assert dur is None


def test_is_in_library_returns_false_when_no_match(tmp_path):
    db = IntelliDJDB(str(tmp_path / "test.db"))
    with patch.object(mod, "fingerprint_file", return_value=("aaabbbccc", 200.0)):
        found, path = mod.is_in_library(Path("/tmp/test.flac"), db)
    assert found is False
    assert path is None
    db.close()


def test_is_in_library_returns_false_when_fingerprint_fails(tmp_path):
    db = IntelliDJDB(str(tmp_path / "test.db"))
    with patch.object(mod, "fingerprint_file", return_value=(None, None)):
        found, path = mod.is_in_library(Path("/tmp/test.flac"), db)
    assert found is False
    assert path is None
    db.close()


def test_is_in_library_returns_true_when_fingerprint_matches(tmp_path):
    db = IntelliDJDB(str(tmp_path / "test.db"))
    track_id = db.upsert_track(
        track_key=make_track_key(artist="Artist", title="Track"),
        artist="Artist",
        title="Track",
    )
    db.upsert_library_file(path="/tmp/existing.flac", track_id=track_id, status="indexed")
    lf_row = db.get_library_file_by_path("/tmp/existing.flac")
    db.upsert_fingerprint(
        library_file_id=lf_row["id"],
        track_id=track_id,
        fpcalc_fingerprint="aaabbbccc",
        fpcalc_duration_sec=200.0,
        status="computed",
    )
    with patch.object(mod, "fingerprint_file", return_value=("aaabbbccc", 200.0)):
        found, match_path = mod.is_in_library(Path("/tmp/new.flac"), db)
    assert found is True
    assert match_path == "/tmp/existing.flac"
    db.close()


def test_is_in_library_duration_tolerance(tmp_path):
    db = IntelliDJDB(str(tmp_path / "test.db"))
    track_id = db.upsert_track(
        track_key=make_track_key(artist="A", title="T"),
        artist="A",
        title="T",
    )
    db.upsert_library_file(path="/tmp/song.flac", track_id=track_id, status="indexed")
    lf_row = db.get_library_file_by_path("/tmp/song.flac")
    db.upsert_fingerprint(
        library_file_id=lf_row["id"],
        track_id=track_id,
        fpcalc_fingerprint="fingerprint123",
        fpcalc_duration_sec=200.0,
        status="computed",
    )
    # Within tolerance (default 5s): should match
    with patch.object(mod, "fingerprint_file", return_value=("fingerprint123", 202.0)):
        found, _ = mod.is_in_library(Path("/tmp/new.flac"), db, duration_tolerance_sec=5.0)
    assert found is True

    # Outside tolerance: should NOT match
    with patch.object(mod, "fingerprint_file", return_value=("fingerprint123", 210.0)):
        found, _ = mod.is_in_library(Path("/tmp/new.flac"), db, duration_tolerance_sec=5.0)
    assert found is False
    db.close()


def test_fingerprint_directory_dry_run(tmp_path):
    db = IntelliDJDB(str(tmp_path / "test.db"))
    run_id = db.start_run(script_name="test_fingerprint_directory")
    track_id = db.upsert_track(
        track_key=make_track_key(artist="A", title="T"),
        artist="A",
        title="T",
    )
    audio_file = tmp_path / "song.flac"
    audio_file.write_bytes(b"fake audio data")
    db.upsert_library_file(path=str(audio_file), track_id=track_id, status="indexed")

    stats = mod.fingerprint_directory(tmp_path, db, run_id=run_id, dry_run=True)
    # In dry-run, file is skipped (not computed)
    assert stats["computed"] == 0
    assert stats["skipped"] >= 1
    db.close()

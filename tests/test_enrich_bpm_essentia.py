import json
import struct
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    import essentia  # noqa: F401
    essentia_available = True
except ImportError:
    essentia_available = False

import scripts.enrich_bpm_essentia as mod
from intellidj.audio_features import analyze_local_audio_features


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sine_wav(path: Path, frequency: float = 120.0, duration_sec: float = 10.0, sample_rate: int = 44100) -> Path:
    """Write a pure-tone WAV file."""
    import math
    n_samples = int(sample_rate * duration_sec)
    amplitude = 16000
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = struct.pack(
            f"<{n_samples}h",
            *[int(amplitude * math.sin(2 * math.pi * frequency * t / sample_rate)) for t in range(n_samples)],
        )
        wf.writeframes(frames)
    return path


def _make_db_with_row(existing_details: dict, download_path: str) -> tuple[MagicMock, list]:
    """
    Return a mock DB whose execute() records UPDATE calls for inspection.
    Also returns a list that captures written JSON strings on UPDATE.
    """
    written: list[str] = []

    def execute_side_effect(sql, params=()):
        mock_result = MagicMock()
        if "SELECT" in sql:
            mock_result.fetchone.return_value = {"details_json": json.dumps(existing_details)}
        elif "UPDATE" in sql:
            written.append(params[0])  # params[0] = json.dumps(current)
            mock_result.fetchone.return_value = None
        return mock_result

    db = MagicMock()
    db.conn.execute.side_effect = execute_side_effect
    return db, written


# ---------------------------------------------------------------------------
# analyze_local_audio_features
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not essentia_available, reason="essentia not installed")
def test_analyze_missing_file():
    result = analyze_local_audio_features("/nonexistent/path/track.mp3")
    assert result is None


@pytest.mark.skipif(not essentia_available, reason="essentia not installed")
def test_analyze_ok(tmp_path):
    wav = _make_sine_wav(tmp_path / "sine.wav")
    result = analyze_local_audio_features(wav)
    assert result is not None
    assert "bpm" in result and "energy" in result and "danceability" in result
    assert result["bpm"] > 0
    assert 0.0 <= result["energy"] <= 1.0
    assert 0.0 <= result["danceability"] <= 1.0


@pytest.mark.skipif(not essentia_available, reason="essentia not installed")
def test_analyze_returns_int_bpm(tmp_path):
    wav = _make_sine_wav(tmp_path / "sine.wav")
    result = analyze_local_audio_features(wav)
    assert isinstance(result["bpm"], int)


def test_analyze_raises_on_missing_essentia(tmp_path):
    with patch.dict("sys.modules", {"essentia": None, "essentia.standard": None}):
        import importlib
        import intellidj.audio_features as af_mod
        importlib.reload(af_mod)
        with pytest.raises(RuntimeError, match="essentia is not installed"):
            af_mod.analyze_local_audio_features("/some/file.mp3")
        importlib.reload(af_mod)


# ---------------------------------------------------------------------------
# find_tracks_needing_enrichment
# ---------------------------------------------------------------------------


def test_find_tracks_skips_nonexistent_files(tmp_path):
    db = MagicMock()
    missing_path = str(tmp_path / "missing.mp3")
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "track_id": 1, "artist": "A", "title": "T",
        "download_path": missing_path,
        "details_json": json.dumps({"bpm": 0}),
    }[k]
    db.conn.execute.return_value.fetchall.return_value = [row]

    result = mod.find_tracks_needing_enrichment(db)
    assert result == []


def test_find_tracks_includes_existing_files(tmp_path):
    db = MagicMock()
    real_path = tmp_path / "track.mp3"
    real_path.write_bytes(b"fake audio")
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "track_id": 1, "artist": "A", "title": "T",
        "download_path": str(real_path),
        "details_json": json.dumps({"bpm": 0}),
    }[k]
    db.conn.execute.return_value.fetchall.return_value = [row]

    result = mod.find_tracks_needing_enrichment(db)
    assert len(result) == 1
    assert result[0]["track_id"] == 1
    assert result[0]["path"] == real_path


def test_find_tracks_passes_label_param():
    db = MagicMock()
    db.conn.execute.return_value.fetchall.return_value = []

    mod.find_tracks_needing_enrichment(db, label="my_set")

    call_args = db.conn.execute.call_args
    query = call_args[0][0]
    params = call_args[0][1]
    assert "ingestion_batches" in query
    assert "my_set" in params


# ---------------------------------------------------------------------------
# update_stage_details
# ---------------------------------------------------------------------------


def test_update_stage_details_merges_existing_keys():
    existing = {"bpm": 0, "energy": 0.0, "danceability": 0.0, "genres": "deep house", "style": "Deep House"}
    db, written = _make_db_with_row(existing, "/tmp/track.mp3")

    mod.update_stage_details(db, track_id=42, features={"bpm": 128, "energy": 0.72, "danceability": 0.65})

    assert len(written) == 1
    result = json.loads(written[0])
    assert result["bpm"] == 128
    assert result["energy"] == pytest.approx(0.72)
    assert result["danceability"] == pytest.approx(0.65)
    assert result["genres"] == "deep house"  # existing key preserved


def test_update_stage_details_recomputes_style_deep():
    existing = {"bpm": 0, "energy": 0.0, "genres": ""}
    db, written = _make_db_with_row(existing, "/tmp/track.mp3")

    mod.update_stage_details(db, track_id=1, features={"bpm": 122, "energy": 0.45, "danceability": 0.5})

    assert json.loads(written[0])["style"] == "Deep House"


def test_update_stage_details_recomputes_style_peak():
    existing = {"bpm": 0, "energy": 0.0, "genres": ""}
    db, written = _make_db_with_row(existing, "/tmp/track.mp3")

    mod.update_stage_details(db, track_id=1, features={"bpm": 130, "energy": 0.80, "danceability": 0.7})

    assert json.loads(written[0])["style"] == "Peak House"


def test_update_stage_details_empty_existing_json():
    existing = {}
    db, written = _make_db_with_row(existing, "/tmp/track.mp3")
    # Simulate fetchone returning None details_json
    db.conn.execute.side_effect = None
    db.conn.execute.return_value.fetchone.return_value = {"details_json": None}

    captured: list[str] = []

    def capture(sql, params=()):
        result = MagicMock()
        if "SELECT" in sql:
            result.fetchone.return_value = {"details_json": None}
        elif "UPDATE" in sql:
            captured.append(params[0])
        return result

    db.conn.execute.side_effect = capture

    mod.update_stage_details(db, track_id=5, features={"bpm": 126, "energy": 0.70, "danceability": 0.60})

    assert len(captured) == 1
    assert json.loads(captured[0])["bpm"] == 126

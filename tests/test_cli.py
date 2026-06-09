import sys
import types

import pytest
from typer.testing import CliRunner

# Inject slskd_api shim before importing cli (which imports downloader)
if "slskd_api" not in sys.modules:
    sys.modules["slskd_api"] = types.SimpleNamespace(SlskdClient=object)

from intellidj.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "candidates" in result.output
    assert "download" in result.output
    assert "enrich" in result.output
    assert "playlist" in result.output
    assert "dedupe" in result.output
    assert "run" in result.output


def test_candidates_help():
    result = runner.invoke(app, ["candidates", "--help"])
    assert result.exit_code == 0
    assert "--output" in result.output
    assert "--dry-run" in result.output


def test_candidates_missing_input():
    result = runner.invoke(app, ["candidates", "nonexistent_file_xyz.csv"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_candidates_dry_run(tmp_path):
    import pandas as pd

    csv_path = tmp_path / "spotify.csv"
    pd.DataFrame([{
        "Artist Name(s)": "Artist A",
        "Track Name": "My Track",
        "Tempo": 128.0,
        "Energy": 0.8,
        "Danceability": 0.7,
        "Genres": "tech house",
        "Record Label": "Label",
    }]).to_csv(csv_path, index=False)

    result = runner.invoke(app, ["candidates", str(csv_path), "--dry-run"])
    assert result.exit_code == 0
    assert "Artist A - My Track" in result.output


def test_download_no_source_no_queries():
    # CliRunner provides empty stdin; no source given → "No queries" error
    result = runner.invoke(app, ["download"])
    assert result.exit_code != 0


def test_download_help():
    result = runner.invoke(app, ["download", "--help"])
    assert result.exit_code == 0
    assert "--csv" in result.output
    assert "--artist" in result.output
    assert "--stdin" in result.output


def test_enrich_help():
    result = runner.invoke(app, ["enrich", "--help"])
    assert result.exit_code == 0
    assert "--input-dir" in result.output
    assert "--custom-tags" in result.output


def test_playlist_help():
    result = runner.invoke(app, ["playlist", "--help"])
    assert result.exit_code == 0
    assert "--library-dir" in result.output
    assert "--out-dir" in result.output


def test_dedupe_help():
    result = runner.invoke(app, ["dedupe", "--help"])
    assert result.exit_code == 0
    assert "--match-mode" in result.output
    assert "--action" in result.output


def test_dedupe_missing_source():
    result = runner.invoke(app, ["dedupe", "/nonexistent/path/xyz"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_dedupe_dry_run(tmp_path):
    # Create two identical files
    a = tmp_path / "a.mp3"
    b = tmp_path / "b.mp3"
    a.write_bytes(b"same content")
    b.write_bytes(b"same content")

    result = runner.invoke(app, ["dedupe", str(tmp_path), "--match-mode", "hash", "--dry-run"])
    assert result.exit_code == 0
    assert "Scanned tracks" in result.output


def test_run_help():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--skip-download" in result.output
    assert "--dry-run" in result.output

import sys
import types

import pytest

# Avoid hard dependency on slskd_api during test import.
if "slskd_api" not in sys.modules:
    sys.modules["slskd_api"] = types.SimpleNamespace(SlskdClient=object)

import dj_to_slskd_pipeline as mod


def test_build_api_base():
    assert mod.build_api_base("http://localhost:5030/") == "http://localhost:5030"
    assert mod.build_api_base("http://host/api/v0") == "http://host"
    assert mod.build_api_base("http://host/api/v0/") == "http://host"


def test_normalize_responses():
    assert mod.normalize_responses(None) == []
    assert mod.normalize_responses([{"a": 1}]) == [{"a": 1}]
    assert mod.normalize_responses({"responses": [{"b": 2}]}) == [{"b": 2}]
    assert mod.normalize_responses({"items": [{"c": 3}]}) == [{"c": 3}]
    assert mod.normalize_responses({"nope": 1}) == []


def test_iter_files_prefers_files_key():
    response = {
        "files": [{"filename": "a"}],
        "fileInfos": [{"filename": "b"}],
    }
    assert mod.iter_files(response) == [{"filename": "a"}]


def test_iter_files_other_keys():
    response = {"results": [{"filename": "a"}]}
    assert mod.iter_files(response) == [{"filename": "a"}]


def test_score_file():
    score, size = mod.score_file({"filename": "Track.flac", "extension": "", "size": 123})
    assert score == 120
    assert size == 123

    score, _ = mod.score_file({"filename": "Track 320.mp3", "extension": "mp3"})
    assert score == 15


def test_pick_best_file():
    responses = [
        {"username": "u1", "files": [{"filename": "song.mp3", "extension": "mp3", "size": 100}]},
        {"username": "u2", "files": [{"filename": "song.flac", "extension": "flac", "size": 50}]},
    ]
    user, file_info = mod.pick_best_file(responses)
    assert user == "u2"
    assert file_info["filename"].endswith(".flac")


def test_pick_best_file_tie_breaks_on_size():
    responses = [
        {"username": "u1", "files": [{"filename": "a.flac", "extension": "flac", "size": 10}]},
        {"username": "u2", "files": [{"filename": "b.flac", "extension": "flac", "size": 20}]},
    ]
    user, file_info = mod.pick_best_file(responses)
    assert user == "u2"
    assert file_info["filename"] == "b.flac"


def test_load_search_strings(tmp_path):
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("search_string\n Artist - Track \n\n", encoding="utf-8")
    assert mod.load_search_strings(str(csv_path), None) == ["Artist - Track"]
    assert mod.load_search_strings(str(csv_path), 1) == ["Artist - Track"]


def test_load_search_strings_missing_column(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("foo\nbar\n", encoding="utf-8")
    with pytest.raises(ValueError, match="search_string"):
        mod.load_search_strings(str(csv_path), None)


def test_fetch_search_responses_404(monkeypatch):
    class DummyResp:
        def __init__(self):
            self.status_code = 404

        def raise_for_status(self):
            raise AssertionError("should not be called")

    def fake_get(url, headers, timeout):
        return DummyResp()

    monkeypatch.setattr(mod.requests, "get", fake_get)
    assert mod.fetch_search_responses("http://host", "key", "id") == []


def test_fetch_search_responses_list(monkeypatch):
    class DummyResp:
        def __init__(self):
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return [{"ok": True}]

    def fake_get(url, headers, timeout):
        return DummyResp()

    monkeypatch.setattr(mod.requests, "get", fake_get)
    assert mod.fetch_search_responses("http://host", "key", "id") == [{"ok": True}]


def test_fetch_search_responses_non_list(monkeypatch):
    class DummyResp:
        def __init__(self):
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"not": "list"}

    def fake_get(url, headers, timeout):
        return DummyResp()

    monkeypatch.setattr(mod.requests, "get", fake_get)
    assert mod.fetch_search_responses("http://host", "key", "id") == []

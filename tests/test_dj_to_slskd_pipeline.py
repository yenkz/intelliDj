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
    rel, fmt, size = mod.score_file({"filename": "Track.flac", "extension": "", "size": 123})
    assert fmt == 120
    assert size == 123

    rel, fmt, _ = mod.score_file({"filename": "Track 320.mp3", "extension": "mp3", "size": 100})
    assert fmt == 15


def test_score_file_with_query():
    rel, fmt, _ = mod.score_file(
        {"filename": "Artist - Song.flac", "extension": "flac", "size": 100},
        query="Artist - Song",
    )
    assert rel == 100  # all query words match
    assert fmt == 120

    rel, _, _ = mod.score_file(
        {"filename": "Unrelated File.flac", "extension": "flac", "size": 100},
        query="Artist - Song",
    )
    assert rel == 0  # no query words match


def test_score_file_filters_non_audio():
    rel, fmt, size = mod.score_file({"filename": "readme.txt", "extension": "txt", "size": 100})
    assert (rel, fmt, size) == (0, 0, 0)

    rel, fmt, size = mod.score_file({"filename": "cover.jpg", "extension": "jpg", "size": 100})
    assert (rel, fmt, size) == (0, 0, 0)


def test_relevance_score():
    assert mod.relevance_score("Artist - Song.flac", "Artist - Song") == 100
    assert mod.relevance_score("Other - File.flac", "Artist - Song") == 0
    # Partial match (artist present, track missing)
    score = mod.relevance_score("Artist - Different.flac", "Artist - Song")
    assert 0 < score < 100


def test_pick_best_file():
    responses = [
        {"username": "u1", "files": [{"filename": "song.mp3", "extension": "mp3", "size": 100}]},
        {"username": "u2", "files": [{"filename": "song.flac", "extension": "flac", "size": 50}]},
    ]
    user, file_info = mod.pick_best_file(responses)
    assert user == "u2"
    assert file_info["filename"].endswith(".flac")


def test_pick_best_file_with_query_filters_irrelevant():
    responses = [
        {"username": "u1", "files": [{"filename": "Wrong Artist - Wrong Song.flac", "extension": "flac", "size": 1000}]},
        {"username": "u2", "files": [{"filename": "Correct Artist - Correct Song.mp3", "extension": "mp3", "size": 50}]},
    ]
    user, file_info = mod.pick_best_file(responses, query="Correct Artist - Correct Song")
    assert user == "u2"
    assert "Correct" in file_info["filename"]


def test_pick_best_file_tie_breaks_on_size():
    responses = [
        {"username": "u1", "files": [{"filename": "a.flac", "extension": "flac", "size": 10}]},
        {"username": "u2", "files": [{"filename": "b.flac", "extension": "flac", "size": 20}]},
    ]
    user, file_info = mod.pick_best_file(responses)
    assert user == "u2"
    assert file_info["filename"] == "b.flac"


def test_build_search_queries():
    # Simple query produces variants
    queries = mod.build_search_queries("Stimming - Your Dreams - Lucid Version")
    assert queries[0] == "Stimming - Your Dreams - Lucid Version"
    assert len(queries) >= 2
    # Simplified version should not contain "Version"
    assert "version" not in queries[1].lower()

    # Simple query with no remix stays as-is
    queries = mod.build_search_queries("Hotlane - Whenever")
    assert queries[0] == "Hotlane - Whenever"


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

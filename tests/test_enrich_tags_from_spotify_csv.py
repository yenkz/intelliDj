import scripts.enrich_tags_from_spotify_csv as mod


def test_normalize():
    assert mod.normalize("Café (Remix) & Co.") == "cafe and co"
    assert mod.normalize("  Multiple   Spaces ") == "multiple spaces"


def test_clean_filename():
    assert mod.clean_filename("01 - Track Name") == "Track Name"
    assert mod.clean_filename("001_Track Name") == "Track Name"


def test_artist_list():
    assert mod.artist_list("A; B ; C") == ["A", "B", "C"]
    assert mod.artist_list("") == []


def test_generate_keys():
    row = {
        "Track Name": "Song - Remix",
        "Artist Name(s)": "Artist A; Artist B",
    }
    keys = mod.generate_keys(row)
    assert mod.normalize("Artist A - Song - Remix") in keys
    assert mod.normalize("Artist A & Artist B - Song - Remix") in keys
    assert mod.normalize("Artist A - Song") in keys


def test_generate_title_keys():
    row = {"Track Name": "Song - Remix"}
    keys = mod.generate_title_keys(row)
    assert mod.normalize("Song - Remix") in keys
    assert mod.normalize("Song") in keys


def test_best_match_exact():
    candidates = [("hello", {"id": 1}), ("world", {"id": 2})]
    row, score, key = mod.best_match("hello", candidates, 0.8)
    assert row["id"] == 1
    assert score == 1.0
    assert key == "hello"


def test_best_match_threshold():
    candidates = [("hello world", {"id": 1})]
    row, score, key = mod.best_match("hello worl", candidates, 0.99)
    assert row is None
    assert score == 0.0
    assert key is None


def test_best_match_with_duration_prefers_tolerance():
    candidates = [
        ("key", {"id": 1, "Duration (ms)": "1000"}),
        ("key", {"id": 2, "Duration (ms)": "5000"}),
    ]
    row, score, key = mod.best_match_with_duration("key", candidates, 0.5, 1000, 50)
    assert row["id"] == 1
    assert key == "key"


def test_best_match_with_duration_fallback():
    candidates = [("hello", {"id": 1, "Duration (ms)": "9999"})]
    row, score, key = mod.best_match_with_duration("hello", candidates, 0.5, 1000, 10)
    assert row["id"] == 1
    assert key == "hello"


def test_extract_artist_title_from_filename():
    artist, title = mod.extract_artist_title_from_filename("01 - Artist - Title")
    assert artist == "Artist"
    assert title == "Title"

    artist, title = mod.extract_artist_title_from_filename("TitleOnly")
    assert artist is None
    assert title == "TitleOnly"


def test_normalize_isrc():
    assert mod.normalize_isrc("us-abc-12-12345") == "USABC1212345"
    assert mod.normalize_isrc("") is None


def test_extract_row_duration_ms():
    assert mod.extract_row_duration_ms({"Duration (ms)": "1234.5"}) == 1234
    assert mod.extract_row_duration_ms({"Duration": "2000"}) == 2000
    assert mod.extract_row_duration_ms({"Duration": ""}) is None
    assert mod.extract_row_duration_ms({}) is None

from pathlib import Path

import scripts.scan_local_music as mod


def test_extract_from_filename_artist_title():
    artist, title = mod._extract_from_filename(Path("/tmp/Artist - Title.flac"))
    assert artist == "Artist"
    assert title == "Title"


def test_extract_from_filename_title_only():
    artist, title = mod._extract_from_filename(Path("/tmp/OnlyTitle.mp3"))
    assert artist is None
    assert title == "OnlyTitle"

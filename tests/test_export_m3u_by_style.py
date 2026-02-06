import scripts.export_m3u_by_style as mod


def test_normalize():
    assert mod.normalize("Café & Co.") == "cafe and co"


def test_clean_filename():
    assert mod.clean_filename("01 - Track") == "Track"
    assert mod.clean_filename("001_Track") == "Track"


def test_sanitize_filename():
    assert mod.sanitize_filename("Deep/House") == "Deep-House"
    assert mod.sanitize_filename("Bad*Chars??") == "BadChars"


def test_build_index_uses_tags_and_filename(tmp_path, monkeypatch):
    files = [
        tmp_path / "01 - Artist - Title.mp3",
        tmp_path / "Other Artist - Song.flac",
        tmp_path / "Unknown.wav",
    ]
    for f in files:
        f.write_bytes(b"")

    def fake_extract_tags(path):
        if path.name == "01 - Artist - Title.mp3":
            return "Artist", "Title"
        return None, None

    monkeypatch.setattr(mod, "extract_tags", fake_extract_tags)

    index, title_index = mod.build_index(tmp_path)
    assert mod.normalize("Artist - Title") in index
    assert mod.normalize("Title") in title_index
    assert mod.normalize("Other Artist - Song") in index
    assert mod.normalize("Unknown") in index

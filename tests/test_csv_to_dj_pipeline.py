import pandas as pd

import csv_to_dj_pipeline as mod


def test_clean_track_name():
    assert mod.clean_track_name("Song (Extended Mix)") == "Song"
    assert mod.clean_track_name("Song - original mix") == "Song"


def test_normalize_artist():
    assert mod.normalize_artist("A; B") == "A"
    assert mod.normalize_artist("Solo") == "Solo"


def test_infer_style_rules():
    assert mod.infer_style("garage", 120, 0.8) == "Garage / Breaky"
    assert mod.infer_style("minimal", 120, 0.8) == "Minimal / Micro"
    assert mod.infer_style("tech house", 120, 0.8) == "Tech House"
    assert mod.infer_style("deep", 124, 0.7) == "Deep House"
    assert mod.infer_style("unknown", 124, 0.5) == "Deep House"
    assert mod.infer_style("unknown", 126, 0.65) == "Peak House"
    assert mod.infer_style("unknown", 120, 0.9) == "House / Groovy"


def test_build_candidates_dataframe():
    df = pd.DataFrame(
        [
            {
                "Artist Name(s)": "Artist A; Artist B",
                "Track Name": "Track (Extended Mix)",
                "Tempo": 128.2,
                "Energy": 0.7,
                "Danceability": 0.5,
                "Genres": "tech house",
                "Record Label": "Label",
            }
        ]
    )
    out = mod.build_candidates_dataframe(df)
    assert set(out.columns) == {
        "artist",
        "track",
        "bpm",
        "energy",
        "danceability",
        "style",
        "label",
        "genres",
        "search_string",
    }
    row = out.iloc[0]
    assert row["artist"] == "Artist A"
    assert row["track"] == "Track"
    assert row["style"] == "Tech House"
    assert row["search_string"] == "Artist A - Track"


def test_build_candidates_dataframe_empty():
    df = pd.DataFrame(
        columns=[
            "Artist Name(s)",
            "Track Name",
            "Tempo",
            "Energy",
            "Danceability",
            "Genres",
            "Record Label",
        ]
    )
    out = mod.build_candidates_dataframe(df)
    assert out.empty
    assert list(out.columns) == [
        "artist",
        "track",
        "bpm",
        "energy",
        "danceability",
        "style",
        "label",
        "genres",
        "search_string",
    ]


def test_default_output_for_input():
    assert mod.default_output_for_input("spotify_export.csv") == "spotify_export_dj_candidates.csv"
    assert mod.default_output_for_input("csv/Liked_Songs.csv") == "csv/Liked_Songs_dj_candidates.csv"

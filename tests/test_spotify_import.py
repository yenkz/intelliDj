import sys
import types

import pytest

# Stub spotipy if not installed (keeps tests runnable without credentials)
if "spotipy" not in sys.modules:
    fake_spotipy = types.ModuleType("spotipy")
    fake_spotipy.Spotify = object
    sys.modules["spotipy"] = fake_spotipy
    oauth2_mod = types.ModuleType("spotipy.oauth2")
    oauth2_mod.SpotifyOAuth = object
    sys.modules["spotipy.oauth2"] = oauth2_mod

import scripts.spotify_import as mod


# ---------------------------------------------------------------------------
# _extract_playlist_id
# ---------------------------------------------------------------------------

def test_extract_playlist_id_raw():
    assert mod._extract_playlist_id("37i9dQZF1DX4sWSpwq3LiO") == "37i9dQZF1DX4sWSpwq3LiO"


def test_extract_playlist_id_url():
    url = "https://open.spotify.com/playlist/37i9dQZF1DX4sWSpwq3LiO?si=abc"
    assert mod._extract_playlist_id(url) == "37i9dQZF1DX4sWSpwq3LiO"


def test_extract_playlist_id_url_no_query():
    url = "https://open.spotify.com/playlist/37i9dQZF1DX4sWSpwq3LiO"
    assert mod._extract_playlist_id(url) == "37i9dQZF1DX4sWSpwq3LiO"


# ---------------------------------------------------------------------------
# tracks_to_dataframe — column names
# ---------------------------------------------------------------------------

EXPECTED_COLUMNS = {
    "Artist Name(s)",
    "Track Name",
    "Album Name",
    "Release Date",
    "Duration (ms)",
    "ISRC",
    "Tempo",
    "Energy",
    "Danceability",
    "Genres",
    "Record Label",
    "Track URI",
}


def _make_enriched(
    *,
    track_id="abc123",
    name="Test Track",
    artists=None,
    duration_ms=210000,
    isrc="USABC1234567",
    album_name="Test Album",
    release_date="2024-01-01",
    tempo=128.0,
    energy=0.8,
    danceability=0.7,
    genres=None,
):
    if artists is None:
        artists = [{"id": "a1", "name": "Artist A"}]
    if genres is None:
        genres = ["tech house"]
    return {
        "track": {
            "id": track_id,
            "name": name,
            "artists": artists,
            "duration_ms": duration_ms,
            "external_ids": {"isrc": isrc},
            "album": {"name": album_name, "release_date": release_date},
        },
        "features": {"id": track_id, "tempo": tempo, "energy": energy, "danceability": danceability},
        "genres": genres,
    }


def test_tracks_to_dataframe_columns():
    df = mod.tracks_to_dataframe([_make_enriched()])
    assert set(df.columns) == EXPECTED_COLUMNS


def test_tracks_to_dataframe_values():
    item = _make_enriched(
        name="My Song",
        artists=[{"id": "a1", "name": "DJ A"}, {"id": "a2", "name": "MC B"}],
        isrc="USABC1234567",
        tempo=130.5,
        energy=0.75,
        danceability=0.6,
        genres=["house", "tech house"],
    )
    df = mod.tracks_to_dataframe([item])
    row = df.iloc[0]
    assert row["Artist Name(s)"] == "DJ A; MC B"
    assert row["Track Name"] == "My Song"
    assert row["ISRC"] == "USABC1234567"
    assert row["Tempo"] == pytest.approx(130.5)
    assert row["Energy"] == pytest.approx(0.75)
    assert row["Danceability"] == pytest.approx(0.6)
    assert row["Genres"] == "house; tech house"
    assert row["Track URI"] == "spotify:track:abc123"


# ---------------------------------------------------------------------------
# tracks_to_dataframe — missing audio features default to 0
# ---------------------------------------------------------------------------

def test_tracks_to_dataframe_missing_features_default_to_zero():
    item = _make_enriched()
    item["features"] = {}  # no audio features at all
    df = mod.tracks_to_dataframe([item])
    row = df.iloc[0]
    assert row["Tempo"] == pytest.approx(0.0)
    assert row["Energy"] == pytest.approx(0.0)
    assert row["Danceability"] == pytest.approx(0.0)


def test_tracks_to_dataframe_none_feature_values_default_to_zero():
    item = _make_enriched()
    item["features"] = {"id": "abc123", "tempo": None, "energy": None, "danceability": None}
    df = mod.tracks_to_dataframe([item])
    row = df.iloc[0]
    assert row["Tempo"] == pytest.approx(0.0)
    assert row["Energy"] == pytest.approx(0.0)
    assert row["Danceability"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# tracks_to_dataframe — edge cases
# ---------------------------------------------------------------------------

def test_tracks_to_dataframe_empty_list():
    df = mod.tracks_to_dataframe([])
    assert df.empty


def test_tracks_to_dataframe_no_genres():
    item = _make_enriched(genres=[])
    df = mod.tracks_to_dataframe([item])
    assert df.iloc[0]["Genres"] == ""


def test_tracks_to_dataframe_record_label_always_empty():
    df = mod.tracks_to_dataframe([_make_enriched()])
    assert df.iloc[0]["Record Label"] == ""


def test_tracks_to_dataframe_multiple_tracks():
    items = [_make_enriched(track_id="t1", name="Track 1"), _make_enriched(track_id="t2", name="Track 2")]
    df = mod.tracks_to_dataframe(items)
    assert len(df) == 2
    assert list(df["Track Name"]) == ["Track 1", "Track 2"]

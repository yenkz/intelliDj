import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from intellidj.audio_features import fetch_soundnet_features


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _mock_error_response(status_code: int = 403) -> MagicMock:
    from requests import HTTPError
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status.side_effect = HTTPError(response=resp)
    return resp


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_fetch_soundnet_features_ok():
    payload = {"tempo": 128, "energy": 75, "danceability": 82}
    with patch("intellidj.audio_features.requests.get", return_value=_mock_response(payload)):
        result = fetch_soundnet_features("abc123", "test_key")
    assert result is not None
    assert result["tempo"] == pytest.approx(128.0)
    assert result["energy"] == pytest.approx(0.75)
    assert result["danceability"] == pytest.approx(0.82)


def test_fetch_soundnet_features_normalises_scale():
    payload = {"tempo": 125, "energy": 80, "danceability": 50}
    with patch("intellidj.audio_features.requests.get", return_value=_mock_response(payload)):
        result = fetch_soundnet_features("abc123", "test_key")
    assert result["energy"] == pytest.approx(0.80)
    assert result["danceability"] == pytest.approx(0.50)


def test_fetch_soundnet_features_full_scale():
    payload = {"tempo": 140, "energy": 100, "danceability": 0}
    with patch("intellidj.audio_features.requests.get", return_value=_mock_response(payload)):
        result = fetch_soundnet_features("abc123", "test_key")
    assert result["energy"] == pytest.approx(1.0)
    assert result["danceability"] == pytest.approx(0.0)


def test_fetch_soundnet_features_float_input():
    # SoundNet may return floats; should still normalise correctly
    payload = {"tempo": 127.5, "energy": 73.4, "danceability": 61.8}
    with patch("intellidj.audio_features.requests.get", return_value=_mock_response(payload)):
        result = fetch_soundnet_features("abc123", "test_key")
    assert result["tempo"] == pytest.approx(127.5)
    assert result["energy"] == pytest.approx(0.734)
    assert result["danceability"] == pytest.approx(0.618)


# ---------------------------------------------------------------------------
# Missing fields default to 0.0
# ---------------------------------------------------------------------------


def test_fetch_soundnet_features_missing_energy():
    payload = {"tempo": 130, "danceability": 70}
    with patch("intellidj.audio_features.requests.get", return_value=_mock_response(payload)):
        result = fetch_soundnet_features("abc123", "test_key")
    assert result["energy"] == pytest.approx(0.0)
    assert result["tempo"] == pytest.approx(130.0)


def test_fetch_soundnet_features_missing_danceability():
    payload = {"tempo": 130, "energy": 60}
    with patch("intellidj.audio_features.requests.get", return_value=_mock_response(payload)):
        result = fetch_soundnet_features("abc123", "test_key")
    assert result["danceability"] == pytest.approx(0.0)


def test_fetch_soundnet_features_missing_all_audio_fields():
    payload = {"key": "C", "mode": "major"}
    with patch("intellidj.audio_features.requests.get", return_value=_mock_response(payload)):
        result = fetch_soundnet_features("abc123", "test_key")
    assert result is not None
    assert result["tempo"] == pytest.approx(0.0)
    assert result["energy"] == pytest.approx(0.0)
    assert result["danceability"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Error cases return None
# ---------------------------------------------------------------------------


def test_fetch_soundnet_features_http_error():
    with patch("intellidj.audio_features.requests.get", return_value=_mock_error_response(403)):
        result = fetch_soundnet_features("abc123", "bad_key")
    assert result is None


def test_fetch_soundnet_features_network_error():
    from requests import ConnectionError as RequestsConnectionError
    with patch("intellidj.audio_features.requests.get", side_effect=RequestsConnectionError("timeout")):
        result = fetch_soundnet_features("abc123", "test_key")
    assert result is None


def test_fetch_soundnet_features_bad_json():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.side_effect = ValueError("not json")
    with patch("intellidj.audio_features.requests.get", return_value=resp):
        result = fetch_soundnet_features("abc123", "test_key")
    assert result is None


# ---------------------------------------------------------------------------
# Request shape — correct headers and URL
# ---------------------------------------------------------------------------


def test_fetch_soundnet_features_request_shape():
    payload = {"tempo": 120, "energy": 65, "danceability": 55}
    with patch("intellidj.audio_features.requests.get", return_value=_mock_response(payload)) as mock_get:
        fetch_soundnet_features("TRACK_ID_XYZ", "MY_API_KEY")

    call_kwargs = mock_get.call_args
    url = call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("url", "")
    headers = call_kwargs.kwargs.get("headers", {})

    assert "TRACK_ID_XYZ" in url
    assert "track-analysis.p.rapidapi.com" in url
    assert "/pktx/spotify/" in url
    assert headers["x-rapidapi-key"] == "MY_API_KEY"
    assert headers["x-rapidapi-host"] == "track-analysis.p.rapidapi.com"

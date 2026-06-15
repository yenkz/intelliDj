"""
intellidj.audio_features — Audio feature lookup.

Two backends:
  fetch_soundnet_features()      — SoundNet RapidAPI (cloud, needs API key)
  analyze_local_audio_features() — Essentia (local, needs audio file on disk)

Pure functions — no DB access, no side effects.
"""
import logging
import requests

log = logging.getLogger(__name__)

SOUNDNET_HOST = "track-analysis.p.rapidapi.com"
_SOUNDNET_URL = f"https://{SOUNDNET_HOST}/pktx/spotify/{{spotify_id}}"


def fetch_soundnet_features(spotify_track_id: str, api_key: str) -> dict | None:
    """
    Call SoundNet 'GET Track Analysis by Spotify ID'.

    Returns a dict with keys:
        tempo        (float) — BPM, same scale as Spotify
        energy       (float) — 0.0–1.0  (SoundNet returns 0–100; normalised here)
        danceability (float) — 0.0–1.0  (SoundNet returns 0–100; normalised here)

    Returns None on any HTTP or parse error so callers can degrade gracefully.
    """
    url = _SOUNDNET_URL.format(spotify_id=spotify_track_id)
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": SOUNDNET_HOST,
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 429:
            log.warning("SoundNet quota exceeded (429) for %s — upgrade your RapidAPI plan", spotify_track_id)
            return None
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("SoundNet request failed for %s: %s", spotify_track_id, exc)
        return None

    raw_tempo        = data.get("tempo")
    raw_energy       = data.get("energy")
    raw_danceability = data.get("danceability")

    return {
        "tempo":        float(raw_tempo)               if raw_tempo        is not None else 0.0,
        "energy":       float(raw_energy) / 100        if raw_energy       is not None else 0.0,
        "danceability": float(raw_danceability) / 100  if raw_danceability is not None else 0.0,
    }


def analyze_local_audio_features(audio_path) -> dict | None:
    """
    Compute BPM, energy, and danceability from a local audio file using Essentia.

    Returns a dict with keys:
        bpm          (int)   — BPM, same scale as Spotify
        energy       (float) — 0.0–1.0, RMS-based approximation
        danceability (float) — 0.0–1.0, normalised from Essentia's 0–3 range

    NOTE: energy is an approximation (mean per-frame RMS ÷ 0.3). It is not
    identical to Spotify's perceptual energy; infer_style() thresholds (0.6/0.65)
    may misclassify borderline tracks.

    Raises RuntimeError if essentia is not installed.
    Returns None on any analysis error (corrupt file, read error, etc.).
    """
    try:
        import essentia.standard as es
        import numpy as np
    except ImportError:
        raise RuntimeError(
            "essentia is not installed. Run:\n"
            "  pip install essentia"
        )

    try:
        audio = es.MonoLoader(filename=str(audio_path), sampleRate=44100)()

        # BPM — directly comparable to Spotify's tempo field
        bpm, _, _, _, _ = es.RhythmExtractor2013(method="multifeature")(audio)

        # Danceability — Essentia returns 0–3; normalise to 0–1
        danceability_raw, _ = es.Danceability()(audio)
        danceability = min(float(danceability_raw) / 3.0, 1.0)

        # Energy — mean per-frame RMS normalised to 0–1
        # Typical music RMS per frame: 0.01–0.3; divide by 0.3 → full energy = 1.0
        rms_algo = es.RMS()
        rms_values = [
            rms_algo(frame)
            for frame in es.FrameGenerator(audio, frameSize=2048, hopSize=1024, startFromZero=True)
        ]
        mean_rms = float(np.mean(rms_values)) if rms_values else 0.0
        energy = min(mean_rms / 0.3, 1.0)

        return {
            "bpm": round(float(bpm)),
            "energy": round(energy, 2),
            "danceability": round(danceability, 2),
        }
    except Exception as exc:
        log.warning("Essentia analysis failed for %s: %s", audio_path, exc)
        return None

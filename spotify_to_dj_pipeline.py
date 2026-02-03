import re
import spotipy
import pandas as pd
from spotipy.oauth2 import SpotifyOAuth

# -------- CONFIG --------
SCOPE = "playlist-read-private playlist-read-collaborative"
OUTPUT_FILE = "dj_candidates.csv"

# -------- HELPERS --------
def clean_track_name(name):
    # Remove common junk
    junk_patterns = [
        r"\(.*extended.*\)",
        r"\(.*original.*\)",
        r"\(.*radio.*\)",
        r"\[.*\]",
        r"- extended.*",
        r"- original.*",
    ]
    cleaned = name.lower()
    for p in junk_patterns:
        cleaned = re.sub(p, "", cleaned, flags=re.IGNORECASE)

    return cleaned.strip().title()

def infer_style(energy, tempo):
    if tempo < 122:
        return "Warm / Deep"
    if tempo < 125 and energy < 0.6:
        return "Deep / Minimal"
    if tempo >= 125 and energy >= 0.6:
        return "Tech / Peak"
    return "Groovy House"

# -------- MAIN --------
sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(scope=SCOPE)
)

rows = []

playlists = sp.current_user_playlists(limit=50)

for playlist in playlists["items"]:
    playlist_name = playlist["name"]
    playlist_id = playlist["id"]

    tracks = sp.playlist_items(playlist_id, additional_types=["track"])

    for item in tracks["items"]:
        track = item["track"]
        if not track:
            continue

        artist = track["artists"][0]["name"]
        title = clean_track_name(track["name"])
        track_id = track["id"]

        features = sp.audio_features([track_id])[0]
        if not features:
            continue

        tempo = round(features["tempo"])
        energy = round(features["energy"], 2)
        danceability = round(features["danceability"], 2)

        style = infer_style(energy, tempo)

        rows.append({
            "artist": artist,
            "track": title,
            "playlist_source": playlist_name,
            "bpm_est": tempo,
            "energy": energy,
            "danceability": danceability,
            "style": style,
            "search_string": f"{artist} - {title}"
        })

df = pd.DataFrame(rows)
df.drop_duplicates(subset=["search_string"], inplace=True)
df.sort_values(by=["style", "bpm_est"], inplace=True)

df.to_csv(OUTPUT_FILE, index=False)

print(f"✅ Archivo generado: {OUTPUT_FILE}")
print(f"🎧 Tracks procesados: {len(df)}")
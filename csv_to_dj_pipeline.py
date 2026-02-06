import argparse
import pandas as pd
import re
import sys
from pathlib import Path


def _setup_logging() -> None:
    script_path = Path(__file__).resolve()
    repo_root = None
    for parent in [script_path.parent] + list(script_path.parents):
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            repo_root = parent
            break
    if repo_root is None:
        repo_root = script_path.parent
    log_dir = repo_root / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{script_path.stem}.log"
    log_file = log_path.open("a", encoding="utf-8")

    class Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, data):
            for stream in self.streams:
                stream.write(data)
                stream.flush()

        def flush(self):
            for stream in self.streams:
                stream.flush()

    sys.stdout = Tee(sys.stdout, log_file)
    sys.stderr = Tee(sys.stderr, log_file)


DEFAULT_INPUT_FILE = "spotify_export.csv"
DEFAULT_OUTPUT_FILE = "dj_candidates.csv"

# ---------------- HELPERS ----------------

def clean_track_name(name):
    junk = [
        r"\(.*extended.*\)",
        r"\(.*original.*\)",
        r"\(.*radio.*\)",
        r"\(.*remaster.*\)",
        r"\[.*\]",
        r"- extended.*",
        r"- original.*",
    ]
    cleaned = str(name)
    for j in junk:
        cleaned = re.sub(j, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def normalize_artist(artist):
    # Soulseek suele fallar con múltiples artistas
    return artist.split(";")[0].strip()

def infer_style(genres, bpm, energy):
    g = str(genres).lower()

    if "garage" in g or "break" in g:
        return "Garage / Breaky"
    if "minimal" in g or "micro" in g:
        return "Minimal / Micro"
    if "tech house" in g:
        return "Tech House"
    if "deep" in g or energy < 0.6:
        return "Deep House"
    if bpm >= 126 and energy >= 0.65:
        return "Peak House"
    return "House / Groovy"


def build_candidates_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, row in df.iterrows():
        artist_raw = row["Artist Name(s)"]
        artist = normalize_artist(artist_raw)

        track = clean_track_name(row["Track Name"])

        bpm = round(row["Tempo"])
        energy = round(row["Energy"], 2)
        danceability = round(row["Danceability"], 2)
        genres = row["Genres"]
        label = row["Record Label"]

        style = infer_style(genres, bpm, energy)

        rows.append({
            "artist": artist,
            "track": track,
            "bpm": bpm,
            "energy": energy,
            "danceability": danceability,
            "style": style,
            "label": label,
            "genres": genres,
            "search_string": f"{artist} - {track}",
        })

    out = pd.DataFrame(rows)

    out.drop_duplicates(subset=["search_string"], inplace=True)
    out.sort_values(by=["style", "bpm"], inplace=True)
    return out

def main(input_file: str, output_file: str) -> None:
    df = pd.read_csv(input_file)

    required_columns = [
        "Artist Name(s)",
        "Track Name",
        "Tempo",
        "Energy",
        "Danceability",
        "Genres",
        "Record Label",
    ]
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise SystemExit(f"Missing required columns: {', '.join(missing)}")

    df = df.copy()
    for col in ["Artist Name(s)", "Track Name", "Genres", "Record Label"]:
        df[col] = df[col].fillna("").astype(str)

    for col in ["Tempo", "Energy", "Danceability"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        invalid = df[col].isna().sum()
        if invalid:
            print(f"⚠️  {invalid} rows have invalid {col}; defaulting to 0")
        df[col] = df[col].fillna(0)

    empty_artist = df["Artist Name(s)"].str.strip() == ""
    empty_track = df["Track Name"].str.strip() == ""
    if (empty_artist | empty_track).any():
        dropped = int((empty_artist | empty_track).sum())
        print(f"⚠️  Dropping {dropped} rows missing artist or track")
        df = df[~(empty_artist | empty_track)]

    print("📄 Columnas detectadas:")
    print(df.columns.tolist())

    out = build_candidates_dataframe(df)
    out.to_csv(output_file, index=False)

    print(f"✅ Generado {output_file}")
    print(f"🎧 Tracks procesados: {len(out)}")


if __name__ == "__main__":
    _setup_logging()
    parser = argparse.ArgumentParser(description="Generate dj_candidates.csv from a Spotify export")
    parser.add_argument("--input", default=DEFAULT_INPUT_FILE, help="Path to spotify_export.csv")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="Path to dj_candidates.csv")
    args = parser.parse_args()
    main(args.input, args.output)

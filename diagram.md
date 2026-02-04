# Workflow Diagram

```mermaid
flowchart TD
  A["Spotify Playlists\n(curated in Spotify)"] --> B["Exportify CSV\nDownload spotify_export.csv"]
  B --> C["csv_to_dj_pipeline.py\nClean names, infer style, output dj_candidates.csv"]
  C --> D["dj_to_slskd_pipeline.py\nSearch slskd + enqueue downloads from dj_candidates.csv"]
  D --> E["slskd (Docker)\nDownloads audio files to ~/Soulseek/downloads/complete"]
  E --> F["enrich_tags_from_spotify_csv.py\nRe-apply Spotify metadata to downloaded files"]
  F --> G["beets_import.sh\nAutomated import + move into ~/Music/DJ/library"]
  G --> H["beets (config.yaml)\nTag cleanup, replaygain, BPM/key, rename files"]
  H --> I["Music Library\n~/Music/DJ/library"]
  I --> J["DJ Software\n(Traktor / Rekordbox)"]

  %% Optional / automation
  E --> K["beets_import.sh (cron/launchd)\nRuns periodic imports"]
```

# Rekordbox Automation

## Import (No Watch Folder)

Rekordbox does not provide a documented watch‑folder feature. Use one of these:

### Option A: Drag & Drop Folder

1. Open **Collection**.
2. Drag `~/Music/DJ/library` into Rekordbox to import tracks.

### Option B: Import M3U Playlists

1. **File → Import → Import Playlist**.
2. Select a `.m3u` file from `playlists/`.
3. Rekordbox will import and analyze those tracks (if Auto Analysis is enabled).

## Auto-Analyze on Import

Enable auto‑analysis for BPM/Key so new tracks are analyzed when they appear.

## Playlist Automation (M3U)

Generate style-based playlists from `dj_candidates.csv`:

```bash
make playlists
```

This creates M3U files in `playlists/` (ignored by git). Import them into Rekordbox to get ready-made style playlists.

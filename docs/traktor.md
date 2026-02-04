# Traktor Automation

## Auto-Import (Music Folders)

Traktor imports new tracks from your Music Folders on startup.

1. Open **Preferences → File Management**.
2. Under **Music Folders**, click **Add…** and select `~/Music/DJ/library`.
3. Enable **Import Music‑Folders at Startup**.
4. (Optional) Enable **Analyze new imported tracks** for BPM/Key analysis.
5. To import immediately without restarting, right‑click **Track Collection** → **Import Music Folders**.

## Auto-Analyze on Import

Enable Traktor’s auto-analysis for BPM/Key so new tracks are analyzed when they appear.

## Playlist Automation (M3U)

Generate style-based playlists from `dj_candidates.csv`:

```bash
make playlists
```

This creates M3U files in `playlists/` (ignored by git). Import them into Traktor to get ready-made style playlists.

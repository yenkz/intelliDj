# Recommendations

## Re-apply Spotify Metadata After Download

Yes, you can enrich downloaded files with Spotify CSV metadata. A reliable approach:

1. Use `spotify_export.csv` as the source of truth for tags.
2. Match downloaded files using `search_string` or a simplified artist/title match.
3. Write tags into the audio files before running beets (so beets can keep or improve them).

Recommended tags to write:

- `artist`, `title`, `album`, `date`
- `label`, `genre`
- `isrc`
- `bpm`, `energy`, `danceability` as custom tags

If you want, I can add a tagging script using `mutagen` that reads `spotify_export.csv` and writes tags to files in `~/Soulseek/downloads/complete`.

## Improve Match Quality

- Prefer FLAC or 320kbps MP3 in slskd searches.
- Strip remix/extended markers when searching, but keep original titles for tagging.
- Deduplicate by `ISRC` when available.

## Reduce Manual Work

- Keep `quiet_fallback: asis` and `fromfilename` in beets so unmatched files still import.
- Use `scripts/beets_import.sh` on a schedule for automatic cleanup.

## Keep an Audit Trail

- Save the original `spotify_export.csv` as an archive for future re-tagging.
- Log beets imports (`import.log`) to review mismatches or skips.

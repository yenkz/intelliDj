# Beets Cleanup Workflow

This workflow imports downloaded tracks, fixes tags, and moves files into a flat library structure.

## Config

Create `~/.config/beets/config.yaml`:

```yaml
directory: ~/Music
library: ~/.config/beets/library.db

import:
  move: true
  copy: false
  write: true
  resume: ask
  timid: false
  autotag: true
  quiet_fallback: skip
  default_action: apply
  log: ~/.config/beets/import.log

paths:
  default: $artist - $title
  singleton: $artist - $title

replace:
  '[\\/]': '_'
  '^\\.+': '_'
  '\\s+$': ''
```

## Dependencies

Some plugins require external tools:

- `ffmpeg` (for `replaygain`)
- Key detection via the `keyfinder` plugin requires either the KeyFinder app or `keyfinder-cli` on your PATH.

On macOS, install the KeyFinder app manually from:

- https://www.ibrahimshaath.co.uk/keyfinder/

Then set the binary path explicitly, for example:

```yaml
keyfinder:
  bin: /Applications/KeyFinder.app/Contents/MacOS/KeyFinder
```

If you use `keyfinder-cli`, the binary must be named `keyfinder-cli`.

Install tools via your OS package manager (e.g. Homebrew on macOS, apt on Debian/Ubuntu), or run:

```bash
make install-beets-deps
```

### keyfinder-cli (macOS)

To build and install `keyfinder-cli` from source (macOS):

```bash
make install-keyfinder-cli
```

This uses `scripts/install_keyfinder_cli.sh` and installs the binary to `$(brew --prefix)/bin/keyfinder-cli`.

Set your beets config:

```yaml
keyfinder:
  bin: /opt/homebrew/bin/keyfinder-cli
```

## Plugin Checklist

Verify your plugins are available:

```bash
poetry run beet version
poetry run beet config -p
```

If you see “plugin not found”, remove it from `plugins:` or install the required package.

## More Automatic Imports (Optional)

If you want fewer prompts, set:

```yaml
import:
  quiet: yes
  timid: no
  default_action: apply
  quiet_fallback: skip
```

## Dry-run (preview)

```bash
poetry run beet -c ~/.config/beets/config.yaml import -p -s ~/Soulseek/downloads/complete
```
## Optional: Tag Enrichment Before Import

If you want to re-apply Spotify CSV metadata before beets, run:

```bash
poetry run python scripts/enrich_tags_from_spotify_csv.py --csv spotify_export.csv --input-dir ~/Soulseek/downloads/complete --custom-tags
```

Matching is more accurate when ISRC and duration are available (the script writes ISRC tags when present in the CSV). You can also generate a report to see why files were skipped:

```bash
poetry run python scripts/enrich_tags_from_spotify_csv.py \
  --csv spotify_export.csv \
  --input-dir ~/Soulseek/downloads/complete \
  --custom-tags \
  --report tag_enrichment_report.csv
```

Optional flags:

- `--duration-tolerance-ms 2000` tighten/loosen duration matching (defaults to 2000ms).
- `--no-duration` disable duration-based matching if file durations are missing or unreliable.
## Import

```bash
poetry run beet -c ~/.config/beets/config.yaml import -s ~/Soulseek/downloads/complete
```

## Optional: Loudness Normalization (2-pass loudnorm)

If you want to normalize volume in-place after import, use the provided script:

```bash
scripts/normalize_loudness.sh --input-dir ~/Music/DJ/library
```

Defaults are set to:

- Integrated loudness (LUFS): `-9`
- True peak: `-1.0 dB`
- Loudness range (LRA): `9`

You can override these with environment variables:

```bash
TARGET_LUFS=-9 TARGET_TP=-1.0 TARGET_LRA=9 \
  scripts/normalize_loudness.sh --input-dir ~/Music/DJ/library
```

Add `--dry-run` to preview which files would be processed.

## Automation

Use the helper script to import new downloads periodically:

```bash
scripts/beets_import.sh
```

### macOS (launchd)

Create `~/Library/LaunchAgents/com.intellidj.beets.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key><string>com.intellidj.beets</string>
    <key>ProgramArguments</key>
    <array>
      <string>/bin/sh</string>
      <string>/Users/cpecile/Code/intelliDj/scripts/beets_import.sh</string>
    </array>
    <key>StartInterval</key><integer>300</integer>
    <key>RunAtLoad</key><true/>
  </dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.intellidj.beets.plist
```

### Cron (alternative)

```bash
crontab -e
```

Add:

```
*/5 * * * * /bin/sh /Users/cpecile/Code/intelliDj/scripts/beets_import.sh
```

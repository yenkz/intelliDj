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

## Dry-run

```bash
poetry run beet -c ~/.config/beets/config.yaml import -n -s ~/Soulseek/downloads/complete
```

## Import

```bash
poetry run beet -c ~/.config/beets/config.yaml import -s ~/Soulseek/downloads/complete
```

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

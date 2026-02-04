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

# slskd (Docker + API Downloads)

## Run slskd with Docker

1. Install Docker Desktop (macOS/Windows) or Docker Engine + Compose (Linux).
2. Start the container:
   ```bash
   docker-compose up -d
   ```
3. Open the web UI at `http://localhost:5030`.
4. Copy `.env.example` to `.env` and set credentials (web UI + Soulseek).
5. Ensure `slskd_data/slskd.yml` contains your API key with `readwrite` role, then restart the container.

To stop:

```bash
docker-compose down
```

## API Downloads

Use `dj_to_slskd_pipeline.py` to queue downloads from `dj_candidates.csv`.

1. Ensure dependencies are installed (`make install-python` or `poetry install`).
2. Load environment variables:
   ```bash
   set -a && source .env && set +a
   ```
3. Run the downloader:
   ```bash
   poetry run python dj_to_slskd_pipeline.py --csv dj_candidates.csv
   ```

Notes:

- The script stops each search after it finds results to clear the “in progress” status and make responses available.
- Use `--no-stop` to keep searches running.
- Use `--dry-run` to preview what would be queued without downloading.

## Optional: Spotify CSV Tag Enrichment

After downloads complete, you can re-apply Spotify metadata:

```bash
poetry run python scripts/enrich_tags_from_spotify_csv.py --csv spotify_export.csv --input-dir ~/Soulseek/downloads/complete --custom-tags
```

To diagnose skipped matches:

```bash
poetry run python scripts/enrich_tags_from_spotify_csv.py --csv spotify_export.csv --input-dir ~/Soulseek/downloads/complete --report tag_report.csv
```

## Optional: Traktor/Rekordbox Playlists (M3U)

Generate style-based playlists after imports:

```bash
make playlists
```

## Ports

- `5030` (HTTP)
- `5031` (HTTPS, self-signed)
- `50300` (Soulseek inbound)

## Recommended Configuration (Example)

Below is a safe baseline configuration inspired by typical slskd setups. Replace the placeholders with your own values and keep secrets in `.env`.

```yaml
web:
  # web settings omitted for brevity

authentication:
  disabled: false
  username: ${SLSKD_USERNAME}
  password: ${SLSKD_PASSWORD}

api_keys:
  primary:
    key: ${SLSKD_API_KEY}
    role: readwrite
    cidr: 0.0.0.0/0,::/0

directories:
  downloads: /app/downloads
  incomplete: /app/incomplete

soulseek:
  address: vps.slsknet.org
  port: 2271
  username: ${SLSKD_SLSK_USERNAME}
  password: ${SLSKD_SLSK_PASSWORD}

# Optional: restrict or tune usage
global:
  upload:
    slots: 20
  download:
    slots: 500
```

Notes:

- Keep `authentication.disabled: false` and change the default web UI credentials.
- Use `readwrite` API keys for automation; avoid exposing the UI publicly.
- If you don’t need remote config changes, set `SLSKD_REMOTE_CONFIGURATION=false`.

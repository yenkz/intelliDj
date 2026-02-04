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

## Ports

- `5030` (HTTP)
- `5031` (HTTPS, self-signed)
- `50300` (Soulseek inbound)

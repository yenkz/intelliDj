OS_NAME := $(shell uname -s 2>/dev/null || echo unknown)
CSV ?= dj_candidates.csv
EXPORTIFY_CSV ?= spotify_export.csv
LIBRARY_DIR ?= ~/Music/DJ/library
PLAYLIST_OUT ?= playlists
SCAN_DIR ?=
DB_PATH ?= intellidj.db
IMPORT_LABEL ?=
PROCESS_SCOPE ?= new
BATCH_ID ?=
DLS_DIR ?= ~/Soulseek/downloads/complete
DLS_FOLDER ?=
SINCE ?=
MOVE ?= 0
DEDUPE ?= 0
RUN_BEETS ?= 0
RUN_COVER_ART ?= 0
COVER_ART_FORCE ?= 0
COVER_ART_SKIP_EMBED ?= 0
DUP_SOURCE ?= ~/Music/DJ/library
DUP_COMPARE ?=
DUP_ACTION ?= report
DUP_KEEP ?= best
DUP_MATCH ?= hybrid
DUP_REVIEW ?= duplicate_review
DUP_DRY_RUN ?= 1
DUP_PREFER_ORIGIN ?=
DUP_CLEANUP_EMPTY ?= 0
INTEGRITY_FIX ?= 0
INTEGRITY_DIRS ?=

ifeq ($(OS),Windows_NT)
  DETECTED_OS := windows
else ifeq ($(OS_NAME),Darwin)
  DETECTED_OS := macos
else
  DETECTED_OS := linux
endif

.PHONY: prereqs install-docker install-uv install-python install-python-pip install-beets-deps install-keyfinder-cli beets-import cover-art enrich-bpm playlists slskd-download slskd-download-db scan-local import-csv-db export-db-csv pipeline-run backfill-db duplicates ui duplicates-ui test test-cov init-db check-integrity wipe-db stage-downloads

prereqs:
	@echo "Detected OS: $(DETECTED_OS)"
	@if [ "$(DETECTED_OS)" = "macos" ]; then \
		if ! command -v brew >/dev/null 2>&1; then \
			echo "Homebrew not found. Install it from https://brew.sh/"; exit 1; \
		fi; \
		if ! command -v docker >/dev/null 2>&1; then \
			echo "Docker not found. Run 'make install-docker' or install Docker Desktop."; \
		fi; \
		if ! command -v uv >/dev/null 2>&1; then \
			echo "uv not found. Run 'make install-uv'."; \
		fi; \
		echo "Prereq check complete."; \
	elif [ "$(DETECTED_OS)" = "windows" ]; then \
		echo "Windows detected. Please install Docker Desktop manually from https://www.docker.com/products/docker-desktop/"; \
		echo "Then install uv: powershell -ExecutionPolicy Bypass -c \"irm https://astral.sh/uv/install.ps1 | iex\""; \
	else \
		echo "Linux detected. Install Docker Engine + Compose via your distro packages."; \
		echo "Then install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"; \
	fi

install-docker:
	@if [ "$(DETECTED_OS)" = "macos" ]; then \
		brew install --cask docker; \
		echo "Docker Desktop installed. Start it from Applications."; \
	elif [ "$(DETECTED_OS)" = "windows" ]; then \
		echo "Please install Docker Desktop manually from https://www.docker.com/products/docker-desktop/"; \
	else \
		echo "Please install Docker Engine and Docker Compose via your distro packages."; \
	fi

install-uv:
	@if [ "$(DETECTED_OS)" = "windows" ]; then \
		powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"; \
	else \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi

install-python:
	@if [ "$(DETECTED_OS)" = "windows" ]; then \
		powershell -ExecutionPolicy Bypass -File .\\scripts\\install_python_deps.ps1; \
	else \
		scripts/install_python_deps.sh; \
	fi

install-python-pip:
	@if [ "$(DETECTED_OS)" = "windows" ]; then \
		powershell -ExecutionPolicy Bypass -File .\\scripts\\install_python_deps_pip.ps1; \
	else \
		scripts/install_python_deps_pip.sh; \
	fi

install-beets-deps:
	@if [ "$(DETECTED_OS)" = "macos" ]; then \
		brew install ffmpeg; \
		if ! command -v keyfinder-cli >/dev/null 2>&1 && [ ! -x "/Applications/KeyFinder.app/Contents/MacOS/KeyFinder" ]; then \
			echo "KeyFinder not found. Install the KeyFinder app or keyfinder-cli, then set keyfinder.bin in your beets config."; \
		fi; \
	elif [ "$(DETECTED_OS)" = "windows" ]; then \
		echo "Please install ffmpeg and keyfinder manually, then ensure they are on PATH."; \
	else \
		echo "Please install ffmpeg and keyfinder via your distro packages."; \
	fi

install-keyfinder-cli:
	@scripts/install_keyfinder_cli.sh

beets-import:
	@CMD='poetry run python scripts/run_beets_import.py --db-path "$(DB_PATH)" --input-dir "$(DLS_DIR)" --scope "$(PROCESS_SCOPE)"'; \
	if [ -n "$(IMPORT_LABEL)" ]; then CMD="$$CMD --label \"$(IMPORT_LABEL)\""; fi; \
	if [ -n "$(BATCH_ID)" ]; then CMD="$$CMD --batch-id \"$(BATCH_ID)\""; fi; \
	echo "$$CMD"; \
	eval "$$CMD"

cover-art:
	@CMD='poetry run python scripts/run_cover_art.py --db-path "$(DB_PATH)" --scope "$(PROCESS_SCOPE)"'; \
	if [ -n "$(IMPORT_LABEL)" ]; then CMD="$$CMD --label \"$(IMPORT_LABEL)\""; fi; \
	if [ -n "$(BATCH_ID)" ]; then CMD="$$CMD --batch-id \"$(BATCH_ID)\""; fi; \
	echo "$$CMD"; \
	eval "$$CMD"

enrich-bpm:
	@CMD='poetry run python scripts/enrich_bpm_essentia.py --db-path "$(DB_PATH)"'; \
	if [ -n "$(IMPORT_LABEL)" ]; then CMD="$$CMD --label \"$(IMPORT_LABEL)\""; fi; \
	if [ -n "$(LIMIT)" ]; then CMD="$$CMD --limit \"$(LIMIT)\""; fi; \
	if [ "$(DRY_RUN)" = "true" ]; then CMD="$$CMD --dry-run"; fi; \
	echo "$$CMD"; \
	eval "$$CMD"

playlists:
	@uv run python scripts/export_m3u_by_style.py --csv $(CSV) --library-dir $(LIBRARY_DIR) --out-dir $(PLAYLIST_OUT)

stage-downloads:
	@CMD='poetry run python scripts/move_downloads_to_inbox.py --downloads-dir "$(DLS_DIR)"'; \
	if [ -n "$(SINCE)" ]; then CMD="$$CMD --since \"$(SINCE)\""; fi; \
	if [ -n "$(DLS_FOLDER)" ]; then CMD="$$CMD --folder \"$(DLS_FOLDER)\""; fi; \
	if [ "$(MOVE)" = "1" ]; then CMD="$$CMD --move"; fi; \
	if [ "$(DEDUPE)" = "1" ]; then CMD="$$CMD --dedupe"; fi; \
	if [ "$(DRY_RUN)" = "1" ]; then CMD="$$CMD --dry-run"; fi; \
	echo "$$CMD"; \
	eval "$$CMD"

slskd-download:
	@uv run python dj_to_slskd_pipeline.py --csv $(CSV)

slskd-download-db:
	@CMD='poetry run python dj_to_slskd_pipeline.py --db-path "$(DB_PATH)" --scope "$(PROCESS_SCOPE)"'; \
	if [ -n "$(IMPORT_LABEL)" ]; then CMD="$$CMD --label \"$(IMPORT_LABEL)\""; fi; \
	if [ -n "$(BATCH_ID)" ]; then CMD="$$CMD --batch-id \"$(BATCH_ID)\""; fi; \
	echo "$$CMD"; \
	eval "$$CMD"

scan-local:
	@CMD='poetry run python scripts/scan_local_music.py --input-dir "$(SCAN_DIR)" --db-path "$(DB_PATH)"'; \
	if [ -n "$(IMPORT_LABEL)" ]; then CMD="$$CMD --label \"$(IMPORT_LABEL)\""; fi; \
	echo "$$CMD"; \
	eval "$$CMD"

import-csv-db:
	@CMD='poetry run python csv_to_dj_pipeline.py --input "$(EXPORTIFY_CSV)" --db-path "$(DB_PATH)"'; \
	if [ -n "$(IMPORT_LABEL)" ]; then CMD="$$CMD --label \"$(IMPORT_LABEL)\""; fi; \
	echo "$$CMD"; \
	eval "$$CMD"

export-db-csv:
	@CMD='poetry run python scripts/export_db_csv.py --db-path "$(DB_PATH)" --out "$(CSV)" --dataset tracks --scope "$(PROCESS_SCOPE)"'; \
	if [ -n "$(IMPORT_LABEL)" ]; then CMD="$$CMD --label \"$(IMPORT_LABEL)\""; fi; \
	if [ -n "$(BATCH_ID)" ]; then CMD="$$CMD --batch-id \"$(BATCH_ID)\""; fi; \
	echo "$$CMD"; \
	eval "$$CMD"

pipeline-run:
	@CMD='poetry run python scripts/run_pipeline.py --db-path "$(DB_PATH)" --downloads-dir "$(DLS_DIR)" --scope "$(PROCESS_SCOPE)"'; \
	if [ -n "$(EXPORTIFY_CSV)" ]; then CMD="$$CMD --csv \"$(EXPORTIFY_CSV)\""; fi; \
	if [ -n "$(SCAN_DIR)" ]; then CMD="$$CMD --scan-dir \"$(SCAN_DIR)\""; fi; \
	if [ -n "$(IMPORT_LABEL)" ]; then CMD="$$CMD --label \"$(IMPORT_LABEL)\""; fi; \
	if [ "$(RUN_BEETS)" = "1" ]; then CMD="$$CMD --run-beets"; fi; \
	if [ "$(RUN_COVER_ART)" = "1" ]; then CMD="$$CMD --run-cover-art"; fi; \
	if [ "$(COVER_ART_FORCE)" = "1" ]; then CMD="$$CMD --cover-art-force"; fi; \
	if [ "$(COVER_ART_SKIP_EMBED)" = "1" ]; then CMD="$$CMD --skip-cover-art-embed"; fi; \
	echo "$$CMD"; \
	eval "$$CMD"

backfill-db:
	@CMD='poetry run python scripts/backfill_db_v2.py --db-path "$(DB_PATH)"'; \
	if [ -n "$(IMPORT_LABEL)" ]; then CMD="$$CMD --label \"$(IMPORT_LABEL)\""; fi; \
	echo "$$CMD"; \
	eval "$$CMD"

init-db:
	@poetry run python scripts/init_intellidj_db.py --db-path "$(DB_PATH)"

wipe-db:
	@poetry run python scripts/wipe_db.py --db-path "$(DB_PATH)" --yes

check-integrity:
	@CMD='poetry run python scripts/check_db_integrity.py --db-path "$(DB_PATH)"'; \
	if [ "$(INTEGRITY_FIX)" = "1" ]; then CMD="$$CMD --fix"; fi; \
	if [ -n "$(INTEGRITY_DIRS)" ]; then CMD="$$CMD --scan-dirs $(INTEGRITY_DIRS)"; fi; \
	echo "$$CMD"; \
	eval "$$CMD"

duplicates:
	@CMD='uv run python scripts/find_duplicate_tracks.py --source-dir "$(DUP_SOURCE)" --match-mode "$(DUP_MATCH)" --action "$(DUP_ACTION)" --keep-strategy "$(DUP_KEEP)"'; \
	if [ -n "$(DUP_COMPARE)" ]; then CMD="$$CMD --compare-dir \"$(DUP_COMPARE)\""; fi; \
	if [ -n "$(DUP_PREFER_ORIGIN)" ]; then CMD="$$CMD --prefer-origin \"$(DUP_PREFER_ORIGIN)\""; fi; \
	if [ "$(DUP_ACTION)" = "move" ]; then CMD="$$CMD --review-dir \"$(DUP_REVIEW)\""; fi; \
	if [ "$(DUP_ACTION)" = "delete" ] && [ "$(DUP_CLEANUP_EMPTY)" = "1" ]; then CMD="$$CMD --cleanup-empty-dirs"; fi; \
	if [ "$(DUP_DRY_RUN)" = "1" ]; then CMD="$$CMD --dry-run"; fi; \
	if [ "$(DUP_ACTION)" != "report" ] && [ "$(DUP_DRY_RUN)" != "1" ]; then CMD="$$CMD --yes"; fi; \
	echo "$$CMD"; \
	eval "$$CMD"

ui:
	@uv run streamlit run ui/streamlit_app.py

duplicates-ui:
	@uv run streamlit run ui/streamlit_duplicates_app.py

test:
	@uv run pytest

test-cov:
	@uv run pytest --cov=. --cov-report=term-missing

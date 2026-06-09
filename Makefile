OS_NAME := $(shell uname -s 2>/dev/null || echo unknown)
CSV ?= spotify_export.csv
CANDIDATES_CSV ?= dj_candidates.csv
LIBRARY_DIR ?= ~/Music/DJ/library
PLAYLIST_OUT ?= playlists
DOWNLOADS_DIR ?= ~/Soulseek/downloads/complete
DUP_SOURCE ?= ~/Music/DJ/library
DUP_COMPARE ?=
DUP_ACTION ?= report
DUP_KEEP ?= best
DUP_MATCH ?= hybrid
DUP_REVIEW ?= duplicate_review
DUP_DRY_RUN ?= 1
DUP_PREFER_ORIGIN ?=
DUP_CLEANUP_EMPTY ?= 0
LIMIT ?=

ifeq ($(OS),Windows_NT)
  DETECTED_OS := windows
else ifeq ($(OS_NAME),Darwin)
  DETECTED_OS := macos
else
  DETECTED_OS := linux
endif

.PHONY: prereqs install-docker install-poetry install-python install-python-pip \
        install-beets-deps install-keyfinder-cli beets-import \
        candidates download enrich playlist dedupe run \
        test test-cov

prereqs:
	@echo "Detected OS: $(DETECTED_OS)"
	@if [ "$(DETECTED_OS)" = "macos" ]; then \
		if ! command -v brew >/dev/null 2>&1; then \
			echo "Homebrew not found. Install it from https://brew.sh/"; exit 1; \
		fi; \
		if ! command -v docker >/dev/null 2>&1; then \
			echo "Docker not found. Run 'make install-docker' or install Docker Desktop."; \
		fi; \
		if ! command -v poetry >/dev/null 2>&1; then \
			echo "Poetry not found. Run 'make install-poetry'."; \
		fi; \
		echo "Prereq check complete."; \
	elif [ "$(DETECTED_OS)" = "windows" ]; then \
		echo "Windows detected. Please install Docker Desktop manually from https://www.docker.com/products/docker-desktop/"; \
		echo "Then install Poetry: python -m pip install poetry"; \
	else \
		echo "Linux detected. Install Docker Engine + Compose via your distro packages."; \
		echo "Then install Poetry: python -m pip install poetry"; \
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

install-poetry:
	@python -m pip install poetry

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
	elif [ "$(DETECTED_OS)" = "windows" ]; then \
		echo "Please install ffmpeg and keyfinder manually, then ensure they are on PATH."; \
	else \
		echo "Please install ffmpeg and keyfinder via your distro packages."; \
	fi

install-keyfinder-cli:
	@scripts/install_keyfinder_cli.sh

beets-import:
	@if [ "$(DETECTED_OS)" = "windows" ]; then \
		powershell -ExecutionPolicy Bypass -File .\\scripts\\beets_import.ps1; \
	else \
		scripts/beets_import.sh; \
	fi

# ── Pipeline commands ──────────────────────────────────────────────────────────

candidates:
	@poetry run intellidj candidates $(CSV) $(if $(LIMIT),--limit $(LIMIT),)

download:
	@poetry run intellidj download --csv $(CANDIDATES_CSV) $(if $(LIMIT),--limit $(LIMIT),)

enrich:
	@poetry run intellidj enrich --csv $(CSV) --input-dir $(DOWNLOADS_DIR)

playlist:
	@poetry run intellidj playlist --csv $(CANDIDATES_CSV) --library-dir "$(LIBRARY_DIR)" --out-dir $(PLAYLIST_OUT)

dedupe:
	@CMD='poetry run intellidj dedupe "$(DUP_SOURCE)" --match-mode "$(DUP_MATCH)" --action "$(DUP_ACTION)" --keep-strategy "$(DUP_KEEP)"'; \
	if [ -n "$(DUP_COMPARE)" ]; then CMD="$$CMD --compare-dir \"$(DUP_COMPARE)\""; fi; \
	if [ -n "$(DUP_PREFER_ORIGIN)" ]; then CMD="$$CMD --prefer-origin \"$(DUP_PREFER_ORIGIN)\""; fi; \
	if [ "$(DUP_ACTION)" = "move" ]; then CMD="$$CMD --review-dir \"$(DUP_REVIEW)\""; fi; \
	if [ "$(DUP_CLEANUP_EMPTY)" = "1" ]; then CMD="$$CMD --cleanup-empty-dirs"; fi; \
	if [ "$(DUP_DRY_RUN)" = "1" ]; then CMD="$$CMD --dry-run"; fi; \
	if [ "$(DUP_ACTION)" != "report" ] && [ "$(DUP_DRY_RUN)" != "1" ]; then CMD="$$CMD --yes"; fi; \
	echo "$$CMD"; \
	eval "$$CMD"

run:
	@poetry run intellidj run --csv $(CSV)

# ── Testing ───────────────────────────────────────────────────────────────────

test:
	@poetry run pytest

test-cov:
	@poetry run pytest --cov=intellidj --cov-report=term-missing

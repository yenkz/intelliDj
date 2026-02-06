OS_NAME := $(shell uname -s 2>/dev/null || echo unknown)
CSV ?= dj_candidates.csv
LIBRARY_DIR ?= ~/Music/DJ/library
PLAYLIST_OUT ?= playlists

ifeq ($(OS),Windows_NT)
  DETECTED_OS := windows
else ifeq ($(OS_NAME),Darwin)
  DETECTED_OS := macos
else
  DETECTED_OS := linux
endif

.PHONY: prereqs install-docker install-poetry install-python install-python-pip install-beets-deps install-keyfinder-cli beets-import playlists slskd-download ui test test-cov

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
	@scripts/install_python_deps.sh

install-python-pip:
	@scripts/install_python_deps_pip.sh

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
	@scripts/beets_import.sh

playlists:
	@poetry run python scripts/export_m3u_by_style.py --csv $(CSV) --library-dir $(LIBRARY_DIR) --out-dir $(PLAYLIST_OUT)

slskd-download:
	@poetry run python dj_to_slskd_pipeline.py --csv $(CSV)

ui:
	@poetry run streamlit run ui/streamlit_app.py

test:
	@poetry run pytest

test-cov:
	@poetry run pytest --cov=. --cov-report=term-missing

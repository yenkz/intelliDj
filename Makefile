OS_NAME := $(shell uname -s 2>/dev/null || echo unknown)

ifeq ($(OS),Windows_NT)
  DETECTED_OS := windows
else ifeq ($(OS_NAME),Darwin)
  DETECTED_OS := macos
else
  DETECTED_OS := linux
endif

.PHONY: prereqs install-docker install-poetry install-python

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

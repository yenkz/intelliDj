#!/bin/sh
set -e

if ! command -v poetry >/dev/null 2>&1; then
  python -m pip install poetry
fi

poetry install --no-root

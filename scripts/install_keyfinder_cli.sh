#!/bin/sh
set -e

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew not found. Install it from https://brew.sh/" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git not found. Install Xcode Command Line Tools or git." >&2
  exit 1
fi

if ! command -v cmake >/dev/null 2>&1; then
  brew install cmake
fi

brew install ffmpeg libkeyfinder

PREFIX="$(brew --prefix)"
WORKDIR="${HOME}/.cache/keyfinder-cli"

rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"

git clone https://github.com/evanpurkhiser/keyfinder-cli.git "$WORKDIR"

cmake -DCMAKE_INSTALL_PREFIX="$PREFIX" -S "$WORKDIR" -B "$WORKDIR/build"
cmake --build "$WORKDIR/build"
cmake --install "$WORKDIR/build"

echo "Installed keyfinder-cli to: $PREFIX/bin/keyfinder-cli"

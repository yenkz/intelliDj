# Setup and Prerequisites

## Requirements

- Python 3.10+
- Docker Desktop or Docker Engine + Compose (for slskd)

## Dependency Installation

Poetry (recommended):

```bash
make install-python
```

Pip-only (fallback):

```bash
make install-python-pip
```

If you want to run Poetry directly:

```bash
poetry install
```

Run scripts with Poetry:

```bash
poetry run python <script>.py
```

## Makefile Helpers

```bash
make prereqs
make install-docker
make install-python
make install-python-pip
```

# Setup and Prerequisites

## Requirements

- Python 3.10+
- Poetry (installed automatically by `make install-python` or manually with `pip install poetry`)
- Docker Desktop or Docker Engine + Compose (for slskd)

## Makefile Helpers

```bash
make prereqs
make install-docker
make install-python
```

## Poetry

Install dependencies:

```bash
poetry install
```

Run scripts with Poetry:

```bash
poetry run python <script>.py
```

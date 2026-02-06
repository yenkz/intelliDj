import sys
from pathlib import Path

# Ensure repo root is on sys.path for script-style modules.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

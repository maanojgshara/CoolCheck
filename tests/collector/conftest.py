import sys
from pathlib import Path

_scripts = Path(__file__).resolve().parents[2] / "scripts"
for _p in ("backfill", "collector", "checks"):
    sys.path.insert(0, str(_scripts / _p))

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("AFO_DATA_DIR", tempfile.mkdtemp(prefix="afo_tests_"))

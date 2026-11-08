"""Autoprueba integrada completa (interfaz + QWebChannel + motor) en un proceso aparte."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_selftest(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "app"), AFO_DATA_DIR=str(tmp_path / "data"))
    if sys.platform.startswith("linux") and not env.get("DISPLAY"):
        pytest.skip("Linux sin DISPLAY: ejecutar con xvfb-run")
    report = tmp_path / "report.json"
    r = subprocess.run([sys.executable, "-m", "allforone", "--selftest", "--report", str(report)],
                       cwd=ROOT / "app", env=env, capture_output=True, text=True, timeout=240)
    data = json.loads(report.read_text(encoding="utf-8"))
    failed = [x for x in data["results"] if x["status"] == "fail"]
    assert r.returncode == 0 and not failed, (failed, r.stdout[-2000:], r.stderr[-2000:])

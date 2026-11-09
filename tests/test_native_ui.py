"""Autoprueba integrada (motor + interfaz Qt Quick, sin Chromium) en un proceso aparte y diseño guardado."""
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
    names = {x["name"] for x in data["results"] if x["status"] == "ok"}
    assert r.returncode == 0 and not failed, (failed, r.stdout[-2000:], r.stderr[-2000:])
    assert "interfaz QML cargada sin avisos" in names and "14 módulos en el lienzo" in names


def test_layout_store_roundtrip(tmp_path):
    from allforone.native_ui import LayoutStore

    store = LayoutStore(tmp_path / "diseno.json")
    assert store.load() == "{}"
    store.save(json.dumps({"pos": {"pistas": [1, 2, 300]}, "theme": "dark"}))
    assert json.loads(store.load())["theme"] == "dark"
    store.save("esto no es json")                      # se ignora: el archivo anterior sigue válido
    assert json.loads(store.load())["pos"]["pistas"] == [1, 2, 300]


def test_qml_has_no_web():
    qml = ROOT / "app" / "allforone" / "qml"
    text = "".join(p.read_text(encoding="utf-8") for p in [*qml.rglob("*.qml"), *qml.rglob("*.js")])
    assert len(list(qml.rglob("*.qml"))) > 25
    for web in ("QtWebEngine", "WebEngineView", "QtWebChannel", "WebView"):
        assert web not in text, web


def test_app_has_no_web():
    """La interfaz web se retiró: ni su carpeta ni Qt WebEngine en el código de la aplicación."""
    app = ROOT / "app" / "allforone"
    assert not (app / "ui").exists()
    for p in app.glob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert "QtWebEngine" not in text and "QWebChannel" not in text, p.name


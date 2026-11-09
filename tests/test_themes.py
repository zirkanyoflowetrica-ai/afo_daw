"""Temas en templates/ y el «pedal» del buscador de plugins (sin abrir plugins reales)."""
import json
from pathlib import Path

import pytest

from allforone import paths, themes

ROOT = Path(__file__).resolve().parents[1]


def test_repo_themes_are_valid():
    names = {t["name"] for t in themes.list_themes()}
    assert {"AllForOne", "AllForOne Oscuro", "Professional"} <= names
    pro = themes.load("Professional")
    assert pro["dark"] and pro["style"]["frame"] == 0 and pro["style"]["knob"] == "arc"
    assert themes.list_themes()[0]["name"] == "AllForOne"      # el de fábrica primero


def test_shared_theme_folder_is_picked_up(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_root", lambda: tmp_path)
    (tmp_path / "templates" / "Amigo").mkdir(parents=True)
    (tmp_path / "templates" / "Amigo" / "theme.json").write_text(json.dumps({"name": "De mi amigo", "dark": True}), encoding="utf-8")
    (tmp_path / "templates" / "Roto").mkdir()
    (tmp_path / "templates" / "Roto" / "theme.json").write_text("{no es json", encoding="utf-8")
    (tmp_path / "templates" / "Vacio").mkdir()
    assert [t["name"] for t in themes.list_themes()] == ["De mi amigo"]
    assert themes.load("Amigo")["name"] == "De mi amigo"      # por carpeta o por nombre
    with pytest.raises(FileNotFoundError):
        themes.load("No existe")


def test_scan_pedal_is_utf16(tmp_path):
    pytest.importorskip("PySide6")
    from allforone.plugin_scan import PluginScanner

    sc = PluginScanner(tmp_path / "plugins_vst3.xml")
    f = r"C:\Program Files\Common Files\VST3\Plugín.vst3"
    sc.pedal.write_bytes(b"\xff\xfe" + (f + "\r\n").encode("utf-16-le"))   # como lo escribe JUCE
    assert sc._current() == f
    sc.pedal.write_text("", encoding="utf-8")
    assert sc._current() == ""
    prog, args = sc.command()
    assert args[-2:] == ["--scan-plugins", str(tmp_path / "plugins_vst3.xml")]

"""Temas en templates/ y el «pedal» del buscador de plugins (sin abrir plugins reales)."""
import json
from pathlib import Path

import pytest

from allforone import paths, themes

ROOT = Path(__file__).resolve().parents[1]


def test_familia_de_temas():
    """F9 (FLUJO_PROFESIONAL §6): Oscuro, Grafito y Claro, en ese orden; los temas de antes no salen."""
    names = [t["name"] for t in themes.list_themes()]
    assert names[:3] == ["Oscuro", "Grafito", "Claro"], names
    assert not {"AllForOne", "AllForOne Oscuro", "Professional", "Sobrio"} & set(names)
    assert themes.load("Sobrio")["legacy"]                     # se cargan por nombre (diseños guardados)
    # un tema de la familia solo cambia la luz: los colores con significado, los de zona y la forma son comunes
    fijos = {"rec", "ai", "meterOk", "meterWarn", "meterPeak", "ledOff"}
    for n in ("Oscuro", "Grafito", "Claro"):
        t = themes.load(n)
        assert t.get("family") and "modules" not in t and "style" not in t, n
        assert not fijos & set(t.get("colors", {})), n
    assert len(themes.load("Claro")["tracks"]) == 12


def test_sin_colores_fijos_en_la_interfaz():
    """F9: ningún QML ni JS de la interfaz lleva un color «#…» propio; todos salen de theme/Theme.qml."""
    import re
    qml = ROOT / "app" / "allforone" / "qml"
    pat = re.compile(r"""["'](#[0-9a-fA-F]{3,8})["']""")
    found = []
    for f in list(qml.rglob("*.qml")) + list(qml.rglob("*.js")):
        if f.parent.name == "theme":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line):
                found.append(f"{f.relative_to(qml)}:{i}")
    assert not found, found


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

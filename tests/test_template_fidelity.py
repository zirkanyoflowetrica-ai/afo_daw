"""La interfaz de AllForOne ES la plantilla original: solo se permiten las sustituciones documentadas."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "allforone" / "ui"

FONT_OLD = '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">'
FONT_NEW = '<link href="fonts/space-grotesk.css" rel="stylesheet">'
SCRIPTS = '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>\n<script src="afo_bridge.js"></script>\n</body>'


def test_index_is_original_plus_documented_changes():
    original = (ROOT / "PLANTILLA_DAW.html").read_text(encoding="utf-8")
    index = (UI / "index.html").read_text(encoding="utf-8")
    expected = original.replace(FONT_OLD, FONT_NEW).replace("</body>", SCRIPTS)
    assert index == expected


def test_original_colors_preserved():
    index = (UI / "index.html").read_text(encoding="utf-8")
    for color in ["#fff1c9", "#ffc233", "#b79bff", "#5ee0b0", "#ff7a70", "#6ab8ff", "#ff9ee0", "#d4f26a", "#c9ccd2"]:
        assert color in index


def test_fonts_are_local_and_licensed():
    css = (UI / "fonts" / "space-grotesk.css").read_text(encoding="utf-8")
    assert 'font-family:"Space Grotesk"' in css
    assert (UI / "fonts" / "space-grotesk-latin-wght-normal.woff2").stat().st_size > 10_000
    assert "Open Font License" in (UI / "fonts" / "OFL-SpaceGrotesk.txt").read_text(encoding="utf-8")
    assert "googleapis" not in (UI / "index.html").read_text(encoding="utf-8")


def test_bridge_has_no_fake_meters():
    js = (UI / "afo_bridge.js").read_text(encoding="utf-8")
    assert "Math.random" not in js

"""F10: el fondo opcional se prepara una vez (backdrop.py): copia en datos/fondos, tamaño máximo,
capas de parallax en orden y los píxeles extremos con los que el selftest mide el contraste."""
import numpy as np
import pytest

pytest.importorskip("PySide6")
from PySide6.QtGui import QGuiApplication, QImage

from allforone import backdrop


@pytest.fixture(scope="module", autouse=True)
def qt():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture(autouse=True)
def datos(tmp_path, monkeypatch):
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))


def _png(path, w, h, rgb, alpha=255):
    a = np.zeros((h, w, 4), np.uint8)
    a[..., :3] = rgb
    a[..., 3] = alpha
    QImage(a.tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888).copy().save(str(path))
    return path


def test_imagen(tmp_path):
    src = _png(tmp_path / "foto.png", 3000, 400, (30, 60, 90))
    r = backdrop.prepare("image", str(src))
    assert r["ok"] and r["mode"] == "image" and len(r["layers"]) == 1
    out = QImage(r["layers"][0])
    assert out.width() == backdrop.MAX_W                        # reducida para la gráfica
    assert r["dark"] == r["light"] == "#1e3c5a"
    assert "fondos" in r["dir"] and src.is_file()               # el original no se toca


def test_parallax_en_orden(tmp_path):
    d = tmp_path / "capas"
    d.mkdir()
    for n in (10, 2, 1):                                         # 1, 2, 10: por número, no por texto
        _png(d / f"{n}.png", 200, 100, (n * 20, 0, 0))
    (d / "notas.txt").write_text("no es una capa")
    r = backdrop.prepare("parallax", str(d))
    assert r["ok"] and len(r["layers"]) == 3
    reds = [QImage(p).pixelColor(150, 50).red() for p in r["layers"]]
    assert reds == [20, 40, 200]


def test_errores(tmp_path):
    d = tmp_path / "una"
    d.mkdir()
    _png(d / "1.png", 50, 50, (0, 0, 0))
    assert not backdrop.prepare("parallax", str(d))["ok"]                    # hace falta más de una capa
    assert not backdrop.prepare("image", str(tmp_path / "no_existe.png"))["ok"]
    (tmp_path / "roto.png").write_bytes(b"no es png")
    assert not backdrop.prepare("image", str(tmp_path / "roto.png"))["ok"]
    assert not backdrop.prepare("video", str(d))["ok"]

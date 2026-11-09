"""Comparación visual: la plantilla de referencia (templates/AllForOne/PLANTILLA_DAW.html) vs la interfaz nativa.

Uso:  python tools/native_compare.py [--out logs/visual_nativo] [--size 1600x900]

Herramienta de desarrollo: dibuja la plantilla con Qt WebEngine (viene con PySide6; la aplicación
ya no lo usa) y la interfaz QML con datos limpios y el diseño inicial. Mide por separado la
cabecera (transporte y chips de módulos) y el lienzo, donde AllForOne tiene más módulos que la
plantilla (Audios, Afinador, Master IA, Antes / Después, Efectos) y pistas reales en vez de la
demo. La fuente Space Grotesk se sirve desde app/allforone/qml/assets/fonts (sin internet).
Genera plantilla.png, nativo.png, diff.png (en rojo lo que cambia), side_by_side.png y
native_report.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
TEMPLATE = ROOT / "templates" / "AllForOne" / "PLANTILLA_DAW.html"
FONTS = ROOT / "app" / "allforone" / "qml" / "assets" / "fonts"
GOOGLE_FONT = '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">'


def local_template() -> str:
    faces = "".join(
        f"@font-face{{font-family:'Space Grotesk';font-weight:{w};src:url('{(FONTS / f).as_uri()}')}}"
        for w, f in ((400, "SpaceGrotesk-Medium.ttf"), (500, "SpaceGrotesk-Medium.ttf"),
                     (600, "SpaceGrotesk-SemiBold.ttf"), (700, "SpaceGrotesk-Bold.ttf")))
    html = TEMPLATE.read_text(encoding="utf-8")
    assert GOOGLE_FONT in html, "la plantilla cambió su enlace de fuentes"
    return html.replace(GOOGLE_FONT, f"<style>{faces}</style>")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "logs" / "visual_nativo"))
    ap.add_argument("--size", default="1600x900")
    ap.add_argument("--settle", type=float, default=4.0)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    w, h = map(int, args.size.lower().split("x"))

    os.environ["AFO_DATA_DIR"] = tempfile.mkdtemp(prefix="afo_nativo_cmp_")
    from allforone.main import _prepare_qt_environment, setup_logging
    setup_logging()
    _prepare_qt_environment()

    import numpy as np
    from PySide6.QtCore import QCoreApplication, Qt, QUrl
    from PySide6.QtGui import QImage
    from PySide6.QtQuick import QQuickWindow  # noqa: F401  (tipa la ventana raíz como QQuickWindow)
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv[:1])
    from allforone.engine_host import EngineHost
    from allforone.native_ui import build_native_window

    def wait(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)

    view = QWebEngineView()
    view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    view.setHtml(local_template(), QUrl.fromLocalFile(str(TEMPLATE)))
    view.setFixedSize(w, h)
    view.show()
    wait(args.settle)
    view.page().runJavaScript("fit(['inst','drums','pistas'])")   # mismo encuadre inicial que la nativa
    wait(1.0)
    img_ref = view.grab().toImage()
    view.close()

    host = EngineHost.create()
    qml_engine, qwin, _b2 = build_native_window(host)
    qwin.setWidth(w)
    qwin.setHeight(h)
    qwin.show()
    wait(args.settle)
    img_nat = qwin.grabWindow()
    qwin.close()

    def to_np(img: QImage):
        img = img.convertToFormat(QImage.Format.Format_RGB888)
        arr = np.frombuffer(img.constBits(), np.uint8, img.bytesPerLine() * img.height()).reshape(img.height(), img.bytesPerLine())
        return arr[:, : img.width() * 3].reshape(img.height(), img.width(), 3).copy()

    a, b = to_np(img_ref), to_np(img_nat)
    hh, ww = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    a, b = a[:hh, :ww], b[:hh, :ww]
    mask = np.abs(a.astype(int) - b.astype(int)).max(axis=2) > 24
    head = 102
    diff = (a * 0.35).astype(np.uint8)
    diff[mask] = [255, 40, 40]

    def save(arr, name):
        arr = np.ascontiguousarray(arr)
        QImage(arr.data, arr.shape[1], arr.shape[0], arr.shape[1] * 3, QImage.Format.Format_RGB888).save(str(out / name))

    save(a, "plantilla.png")
    save(b, "nativo.png")
    save(diff, "diff.png")
    save(np.concatenate([a, np.full((hh, 12, 3), 0, np.uint8), b], axis=1), "side_by_side.png")
    report = {"size": [ww, hh], "threshold": 24, "reference": "templates/AllForOne/PLANTILLA_DAW.html",
              "header_pixels_changed_pct": round(float(mask[:head].mean() * 100), 3),
              "canvas_pixels_changed_pct": round(float(mask[head:].mean() * 100), 3),
              "total_pixels_changed_pct": round(float(mask.mean() * 100), 3)}
    (out / "native_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report), "->", out)
    host.engine = None
    return 0


if __name__ == "__main__":
    sys.exit(main())

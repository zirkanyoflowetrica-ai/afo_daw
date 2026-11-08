"""Comparación visual: interfaz web actual (Qt WebEngine) vs interfaz nativa (Qt Quick).

Uso:  python tools/native_compare.py [--out logs/visual_nativo] [--size 1600x900] [--oscuro]

Ambas arrancan con datos limpios y el diseño inicial. Mide por separado la cabecera (barra de
transporte y módulos), donde el contenido es el mismo, y la ventana entera, donde los cuerpos de
los módulos que aún no se han migrado son distintos a propósito. Genera web.png, nativo.png,
diff.png (en rojo lo que cambia), side_by_side.png y native_report.json.
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "logs" / "visual_nativo"))
    ap.add_argument("--size", default="1600x900")
    ap.add_argument("--settle", type=float, default=4.0)
    ap.add_argument("--oscuro", action="store_true", help="comparar el tema oscuro")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    w, h = map(int, args.size.lower().split("x"))

    os.environ["AFO_DATA_DIR"] = tempfile.mkdtemp(prefix="afo_nativo_cmp_")
    from allforone.main import _prepare_qt_environment, setup_logging
    setup_logging()
    _prepare_qt_environment()

    import numpy as np
    from PySide6.QtCore import QCoreApplication, QMetaObject, Q_ARG, Qt
    from PySide6.QtGui import QImage
    from PySide6.QtQuick import QQuickWindow  # noqa: F401  (tipa la ventana raíz como QQuickWindow)
    from PySide6.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv[:1])
    from allforone.engine_host import EngineHost
    from allforone.main import build_window
    from allforone.native_ui import build_native_window

    def wait(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)

    host = EngineHost.create()
    win, view, _bridge = build_window(host)
    view.setFixedSize(w, h)
    win.show()
    wait(args.settle)
    if args.oscuro:
        view.page().runJavaScript("AFO.setTheme('dark')")
        wait(0.5)
    img_web = view.grab().toImage()
    win.close()

    qml_engine, qwin, _b2 = build_native_window(host)
    qwin.setWidth(w)
    qwin.setHeight(h)
    qwin.show()
    if args.oscuro:
        QMetaObject.invokeMethod(qwin, "setDark", Q_ARG("QVariant", True))
    wait(args.settle)
    img_nat = qwin.grabWindow()
    qwin.close()

    def to_np(img: QImage):
        img = img.convertToFormat(QImage.Format.Format_RGB888)
        arr = np.frombuffer(img.constBits(), np.uint8, img.bytesPerLine() * img.height()).reshape(img.height(), img.bytesPerLine())
        return arr[:, : img.width() * 3].reshape(img.height(), img.width(), 3).copy()

    a, b = to_np(img_web), to_np(img_nat)
    hh, ww = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    a, b = a[:hh, :ww], b[:hh, :ww]
    mask = np.abs(a.astype(int) - b.astype(int)).max(axis=2) > 24
    head = 102
    diff = (a * 0.35).astype(np.uint8)
    diff[mask] = [255, 40, 40]

    def save(arr, name):
        arr = np.ascontiguousarray(arr)
        QImage(arr.data, arr.shape[1], arr.shape[0], arr.shape[1] * 3, QImage.Format.Format_RGB888).save(str(out / name))

    save(a, "web.png")
    save(b, "nativo.png")
    save(diff, "diff.png")
    save(np.concatenate([a, np.full((hh, 12, 3), 0, np.uint8), b], axis=1), "side_by_side.png")
    report = {"size": [ww, hh], "threshold": 24, "theme": "oscuro" if args.oscuro else "claro",
              "header_pixels_changed_pct": round(float(mask[:head].mean() * 100), 3),
              "canvas_pixels_changed_pct": round(float(mask[head:].mean() * 100), 3),
              "total_pixels_changed_pct": round(float(mask.mean() * 100), 3)}
    (out / "native_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report), "->", out)
    host.engine = None
    return 0


if __name__ == "__main__":
    sys.exit(main())

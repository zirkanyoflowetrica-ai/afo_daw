"""Comparación visual: PLANTILLA_DAW.html original vs AllForOne (misma ventana, distribución inicial).

Uso:  python tools/visual_compare.py [--out logs/visual] [--size 1600x900]

Renderiza ambas con el mismo motor (Qt WebEngine) y almacenamiento limpio. Para que la
comparación mida la interfaz y no la disponibilidad de Internet, la plantilla original se
renderiza con su fuente servida localmente (única sustitución, la misma que usa AllForOne).
Genera: original.png, allforone.png, diff.png (en rojo lo que cambia), side_by_side.png y
visual_report.json con el porcentaje de píxeles distintos y las zonas afectadas.
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
    ap.add_argument("--out", default=str(ROOT / "logs" / "visual"))
    ap.add_argument("--size", default="1600x900")
    ap.add_argument("--settle", type=float, default=4.0, help="segundos de espera (los avisos duran 2.4 s)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    w, h = map(int, args.size.lower().split("x"))

    os.environ["AFO_DATA_DIR"] = tempfile.mkdtemp(prefix="afo_visual_")  # perfil y layout limpios
    from allforone.main import _prepare_qt_environment, setup_logging
    setup_logging()
    _prepare_qt_environment()

    import numpy as np
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QImage
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    from allforone import paths
    from allforone.engine_host import EngineHost
    from allforone.main import build_window

    # Original con la fuente local (misma sustitución que AllForOne; nada más cambia)
    src = (ROOT / "PLANTILLA_DAW.html").read_text(encoding="utf-8")
    font_old = '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">'
    original_local = paths.ui_dir() / "_original_localfont.html"
    original_local.write_text(src.replace(font_old, '<link href="fonts/space-grotesk.css" rel="stylesheet">'), encoding="utf-8")

    def wait(seconds, host=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            if host:
                host.pump()
            time.sleep(0.01)

    try:
        prof = QWebEngineProfile()  # sin almacenamiento persistente
        v1 = QWebEngineView()
        v1.setPage(QWebEnginePage(prof, v1))
        v1.resize(w, h)
        v1.setUrl(QUrl.fromLocalFile(str(original_local)))
        v1.show()
        wait(args.settle)
        img1 = v1.grab().toImage()
        v1.close()

        host = EngineHost.create()
        win, view, _bridge = build_window(host)
        win.setCentralWidget(view)
        view.resize(w, h)
        win.resize(w, h)
        win.show()
        view.setFixedSize(w, h)
        wait(args.settle, host)
        img2 = view.grab().toImage()
        win.close()
    finally:
        original_local.unlink(missing_ok=True)

    def to_np(img: QImage):
        img = img.convertToFormat(QImage.Format.Format_RGB888)
        ptr = img.constBits()
        arr = np.frombuffer(ptr, np.uint8, img.bytesPerLine() * img.height()).reshape(img.height(), img.bytesPerLine())
        return arr[:, : img.width() * 3].reshape(img.height(), img.width(), 3).copy()

    a, b = to_np(img1), to_np(img2)
    hh, ww = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    a, b = a[:hh, :ww], b[:hh, :ww]
    delta = np.abs(a.astype(int) - b.astype(int)).max(axis=2)
    mask = delta > 24
    pct = float(mask.mean() * 100)

    # zonas: rejilla de 40 px con cambios
    cell = 40
    zones = []
    for y in range(0, hh, cell):
        for x in range(0, ww, cell):
            frac = mask[y:y + cell, x:x + cell].mean()
            if frac > 0.02:
                zones.append([x, y])
    diff = (a * 0.35).astype(np.uint8)
    diff[mask] = [255, 40, 40]

    def save(arr, name):
        arr = np.ascontiguousarray(arr)
        QImage(arr.data, arr.shape[1], arr.shape[0], arr.shape[1] * 3, QImage.Format.Format_RGB888).save(str(out / name))

    save(a, "original.png")
    save(b, "allforone.png")
    save(diff, "diff.png")
    save(np.concatenate([a, np.full((hh, 12, 3), 0, np.uint8), b], axis=1), "side_by_side.png")
    report = {"size": [ww, hh], "pixels_changed_pct": round(pct, 3), "threshold": 24,
              "changed_cells_40px": len(zones), "total_cells_40px": ((hh + cell - 1) // cell) * ((ww + cell - 1) // cell),
              "zones": zones}
    (out / "visual_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"Píxeles distintos: {pct:.2f} % ({len(zones)} celdas de 40 px) -> {out}")
    host.engine = None
    return 0


if __name__ == "__main__":
    sys.exit(main())

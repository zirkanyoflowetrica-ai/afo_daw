"""F10: fondo opcional de la ventana (FLUJO_PROFESIONAL §7): una imagen o capas de parallax.

Al elegirlo, se copia a `datos/fondos/<fecha>/` ya preparado, una sola vez:
  * cada capa se reduce a 2560 px de ancho como mucho (memoria de la gráfica);
  * la de atrás se desenfoca un poco (reducir y volver a ampliar con suavizado), así no compite con
    la interfaz; las de delante quedan nítidas y con su transparencia;
  * se mide el píxel más oscuro y el más claro (por luminancia) de lo que se verá, para que el
    selftest compruebe el contraste de los textos con el peor caso.
La interfaz solo traslada `Image`: nada de sombreadores ni desenfoque en vivo, y el audio no se entera.
El programa no trae ni descarga imágenes: las pone el usuario.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import numpy as np

from . import paths

MAX_W = 2560
EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def folder() -> Path:
    p = paths.user_data_dir() / "fondos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _layers_of(src: Path) -> list[Path]:
    """Capas de una carpeta de parallax: 1.png (fondo) … n.png (delante); si no van numeradas, por nombre."""
    files = [p for p in src.iterdir() if p.suffix.lower() in EXT]

    def key(p: Path):
        m = re.match(r"^(\d+)", p.stem)
        return (0, int(m.group(1)), p.name) if m else (1, 0, p.name.lower())
    return sorted(files, key=key)


def _rgba(img) -> np.ndarray:
    from PySide6.QtGui import QImage
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    a = np.frombuffer(img.constBits(), np.uint8, count=img.sizeInBytes())
    return a.reshape(h, img.bytesPerLine())[:, : w * 4].reshape(h, w, 4).copy()   # copia: la QImage convertida muere aquí


def _extremes(arrs: list[np.ndarray]) -> tuple[str, str]:
    """Píxel más oscuro y más claro (luminancia relativa) de las partes visibles de las capas."""
    best_lo, best_hi = (2.0, "#000000"), (-1.0, "#ffffff")
    for a in arrs:
        px = a[a[..., 3] > 127][:, :3]
        if px.size == 0:
            continue
        c = px.astype(np.float64) / 255
        lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
        y = lin @ np.array([0.2126, 0.7152, 0.0722])
        i, j = int(np.argmin(y)), int(np.argmax(y))
        if y[i] < best_lo[0]:
            best_lo = (float(y[i]), "#%02x%02x%02x" % tuple(px[i]))
        if y[j] > best_hi[0]:
            best_hi = (float(y[j]), "#%02x%02x%02x" % tuple(px[j]))
    return best_lo[1], best_hi[1]


def prepare(mode: str, src: str) -> dict:
    """Copia y prepara el fondo. mode «image» (un archivo) o «parallax» (carpeta de capas)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    s = Path(src)
    if mode == "image":
        if not s.is_file() or s.suffix.lower() not in EXT:
            return {"ok": False, "error": f"No es una imagen que se pueda usar (PNG, JPG, WebP o BMP): {s.name}"}
        sources = [s]
    elif mode == "parallax":
        if not s.is_dir():
            return {"ok": False, "error": f"No existe la carpeta {s}"}
        sources = _layers_of(s)
        if len(sources) < 2:
            return {"ok": False, "error": "Para el parallax hacen falta al menos 2 capas (1.png el fondo … n.png la de delante)"}
        sources = sources[:8]
    else:
        return {"ok": False, "error": f"Modo de fondo desconocido: {mode}"}
    out = folder() / f"fondo_{datetime.now():%Y%m%d_%H%M%S_%f}"
    out.mkdir(parents=True)
    layers, arrs = [], []
    for i, p in enumerate(sources):
        img = QImage(str(p))
        if img.isNull():
            return {"ok": False, "error": f"No se pudo leer la imagen {p.name}"}
        if img.width() > MAX_W:
            img = img.scaledToWidth(MAX_W, Qt.TransformationMode.SmoothTransformation)
        if i == 0:                                # la de atrás: desenfoque suave, una vez
            w, h = img.width(), img.height()
            small = img.scaled(max(1, w // 10), max(1, h // 10), Qt.AspectRatioMode.IgnoreAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            img = small.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        dst = out / f"{i + 1}.png"
        if not img.save(str(dst), "PNG"):
            return {"ok": False, "error": f"No se pudo guardar {dst}"}
        layers.append(str(dst))
        arrs.append(_rgba(img))
    dark, light = _extremes(arrs)
    return {"ok": True, "mode": mode, "dir": str(out), "name": s.name, "layers": layers, "dark": dark, "light": light}

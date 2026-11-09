"""Temas de la interfaz: carpeta `templates/` junto al programa (la raíz del proyecto en desarrollo).

Cada subcarpeta con un `theme.json` es un tema; para compartirlo basta copiar la carpeta. El
contenido lo interpreta `qml/theme/Theme.qml` (lo que falte toma el valor del tema AllForOne).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from . import paths

log = logging.getLogger("allforone.themes")
DEFAULT = "AllForOne"


def folder() -> Path:
    p = paths.app_root() / "templates"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read(d: Path) -> dict | None:
    try:
        t = json.loads((d / "theme.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        if (d / "theme.json").exists():
            log.warning("Tema ilegible %s: %s", d, exc)
        return None
    if not isinstance(t, dict):
        return None
    t.setdefault("name", d.name)
    return t


def list_themes() -> list[dict]:
    out = []
    for d in sorted(folder().iterdir(), key=lambda p: p.name.lower()):
        if d.is_dir() and (t := _read(d)):
            out.append({"name": t["name"], "folder": d.name, "description": t.get("description", ""), "dark": bool(t.get("dark"))})
    # AllForOne primero (es el de fábrica)
    out.sort(key=lambda t: (t["name"] != DEFAULT, t["name"].lower()))
    return out


def load(name: str) -> dict:
    for d in folder().iterdir():
        if d.is_dir() and (t := _read(d)) and (t["name"] == name or d.name == name):
            return t
    raise FileNotFoundError(f"no hay ningún tema «{name}» en {folder()}")

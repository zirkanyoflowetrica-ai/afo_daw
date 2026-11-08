"""Rutas de recursos y datos de usuario. Nunca dependen de la ubicación del código fuente."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "AllForOne"


def package_dir() -> Path:
    """Carpeta del paquete allforone (funciona en desarrollo y en la distribución de Nuitka)."""
    return Path(__file__).resolve().parent


def ui_dir() -> Path:
    return package_dir() / "ui"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) or "__compiled__" in globals())


def app_root() -> Path:
    """Carpeta del programa: la del AllForOne.exe empaquetado, o la raíz del proyecto en desarrollo."""
    if is_frozen():
        return Path(sys.argv[0]).resolve().parent
    return package_dir().parents[1]


def user_data_dir() -> Path:
    """Todo lo que AllForOne escribe vive junto al programa (portátil, nada en %APPDATA%):
       EXE\\datos con el ejecutable, o data\\ en la carpeta del proyecto durante el desarrollo."""
    override = os.environ.get("AFO_DATA_DIR")
    base = Path(override) if override else app_root() / ("datos" if is_frozen() else "data")
    base.mkdir(parents=True, exist_ok=True)
    return base


def logs_dir() -> Path:
    p = user_data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def media_dir() -> Path:
    p = user_data_dir() / "media"
    p.mkdir(parents=True, exist_ok=True)
    return p


def web_profile_dir() -> Path:
    p = user_data_dir() / "web"
    p.mkdir(parents=True, exist_ok=True)
    return p

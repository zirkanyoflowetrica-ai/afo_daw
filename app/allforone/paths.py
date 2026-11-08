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


def user_data_dir() -> Path:
    override = os.environ.get("AFO_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
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

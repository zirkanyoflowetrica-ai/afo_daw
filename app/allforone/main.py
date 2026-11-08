"""Arranque de AllForOne: motor nativo + interfaz Qt Quick (QML), sin navegador interno."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from . import __version__, paths

log = logging.getLogger("allforone")


def setup_logging(verbose: bool = False) -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = RotatingFileHandler(paths.logs_dir() / "allforone.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if sys.stderr is not None:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)


def _prepare_qt_environment() -> None:
    os.environ.setdefault("QT_DISABLE_SHADER_DISK_CACHE", "1")   # no escribir cachés de Qt fuera de la carpeta
    # Temporales de Python, del mezclador y de librerías dentro de la carpeta de datos
    tmp = paths.user_data_dir() / "temporales"
    tmp.mkdir(parents=True, exist_ok=True)
    for var in ("TEMP", "TMP", "TMPDIR"):
        os.environ[var] = str(tmp)
    import tempfile
    tempfile.tempdir = str(tmp)
    os.environ.setdefault("NUMBA_CACHE_DIR", str(paths.user_data_dir() / "cache" / "numba"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="AllForOne")
    parser.add_argument("--selftest", action="store_true", help="Ejecuta la verificación integrada y sale")
    parser.add_argument("--report", help="Ruta del informe JSON de --selftest")
    parser.add_argument("--screenshot", help="Ruta de la captura de --selftest")
    parser.add_argument("--nativo", action="store_true", help=argparse.SUPPRESS)   # antes elegía la interfaz nativa; hoy es la única
    parser.add_argument("--verbose", action="store_true")
    args, qt_args = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    setup_logging(args.verbose)
    _prepare_qt_environment()
    log.info("AllForOne %s | Python %s | %s", __version__, sys.version.split()[0], sys.executable)

    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("AllForOne")
    app.setOrganizationName("AllForOne")

    from .engine_host import EngineHost

    host = EngineHost.create()

    if args.selftest:
        from .selftest import run_selftest

        try:
            return run_selftest(app, host, args.report, args.screenshot)
        finally:
            host.engine = None  # cerrar el motor (hilos de audio) antes que Python

    from .native_ui import build_native_window

    qml_engine, window, _bridge = build_native_window(host)
    window.show()
    rc = app.exec()
    if host.ok:
        host.engine.stop()
    del window, qml_engine
    host.engine = None  # destruir el motor antes que QApplication
    return rc

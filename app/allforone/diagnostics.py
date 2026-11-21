"""Rastro de fallos: errores de QML, excepciones de Python y cierres del proceso, al registro.

Sin esto, en AllForOne.exe (sin consola) los avisos de QML y las excepciones dentro de un slot se
pierden, y un cierre nativo no deja nada. Todo va a `logs/allforone.log`; un cierre nativo (acceso
inválido en el motor, un driver o un plugin) deja la pila de Python en `logs/cierre.log`.
"""
from __future__ import annotations

import faulthandler
import logging
import sys
import threading

from . import paths

log = logging.getLogger("allforone.diag")
_crash_file = None
_qt_counts: dict[str, int] = {}
QT_REPEAT_LIMIT = 20          # el mismo aviso no llena el registro (un binding roto se evalúa a cada cuadro)


def install() -> None:
    """Llamar una vez, tras configurar el registro y antes de crear la aplicación Qt."""
    global _crash_file
    try:
        _crash_file = open(paths.logs_dir() / "cierre.log", "a", encoding="utf-8")
        faulthandler.enable(_crash_file, all_threads=True)
    except Exception:            # sin carpeta de registros, al menos stderr
        if sys.stderr is not None:
            faulthandler.enable()

    def _hook(kind, value, tb):
        log.critical("Excepción sin capturar", exc_info=(kind, value, tb))

    sys.excepthook = _hook
    threading.excepthook = lambda a: log.critical("Excepción en el hilo %s", a.thread.name if a.thread else "?",
                                                  exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler

        levels = {QtMsgType.QtDebugMsg: logging.DEBUG, QtMsgType.QtInfoMsg: logging.INFO,
                  QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR,
                  QtMsgType.QtFatalMsg: logging.CRITICAL}
        qlog = logging.getLogger("allforone.qt")

        def _qt(mode, ctx, msg):
            n = _qt_counts.get(msg, 0) + 1
            _qt_counts[msg] = n
            if n <= QT_REPEAT_LIMIT:
                qlog.log(levels.get(mode, logging.WARNING), "%s%s", msg,
                         " (no se repetirá más)" if n == QT_REPEAT_LIMIT else "")

        qInstallMessageHandler(_qt)
    except Exception:
        log.exception("No se pudo instalar el receptor de mensajes de Qt")


def qt_messages() -> dict[str, int]:
    """Avisos de Qt/QML vistos en esta sesión (mensaje → veces); lo usan las pruebas."""
    return dict(_qt_counts)

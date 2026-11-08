"""Ventana principal: QWebEngineView con la plantilla original + QWebChannel + motor nativo."""
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
    # Contenedores Linux ejecutados como root: Chromium exige desactivar su sandbox.
    if sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0:
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--autoplay-policy=no-user-gesture-required")
    os.environ.setdefault("QT_DISABLE_SHADER_DISK_CACHE", "1")   # no escribir cachés de Qt fuera de la carpeta
    # Temporales de Python, del mezclador y de librerías dentro de la carpeta de datos
    tmp = paths.user_data_dir() / "temporales"
    tmp.mkdir(parents=True, exist_ok=True)
    for var in ("TEMP", "TMP", "TMPDIR"):
        os.environ[var] = str(tmp)
    import tempfile
    tempfile.tempdir = str(tmp)
    os.environ.setdefault("NUMBA_CACHE_DIR", str(paths.user_data_dir() / "cache" / "numba"))


def make_drop_filter(view, bridge):
    """Arrastrar archivos desde el Explorador: Qt conoce la ruta real (Chromium no la expone).

    Se entrega a JavaScript con la posición, que decide el destino (Mezcla IA o Pistas)."""
    from PySide6.QtCore import QEvent, QObject

    class DropFilter(QObject):
        def eventFilter(self, obj, ev):  # noqa: N802
            t = ev.type()
            if t in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                md = ev.mimeData()
                if md.hasUrls() and any(u.isLocalFile() for u in md.urls()):
                    ev.acceptProposedAction()
                    return True
            elif t == QEvent.Type.Drop:
                md = ev.mimeData()
                files = [u.toLocalFile() for u in md.urls() if u.isLocalFile()] if md.hasUrls() else []
                if files:
                    pos = ev.position() if hasattr(ev, "position") else ev.pos()
                    deliver_drop(view, files, pos.x(), pos.y())
                    ev.acceptProposedAction()
                    return True
            return False

    return DropFilter(view)


def deliver_drop(view, files, x, y):
    import json as _json
    view.page().runJavaScript(f"window.AFO_onDrop && AFO_onDrop({_json.dumps(files)}, {float(x)}, {float(y)})")


def install_drop_filter(view, flt):
    from PySide6.QtWidgets import QWidget
    view.setAcceptDrops(True)
    for w in [view, *view.findChildren(QWidget)]:
        if not getattr(w, "_afo_drop", False):
            w.setAcceptDrops(True)
            w.installEventFilter(flt)
            w._afo_drop = True


def build_window(host):
    """Crea la ventana con la interfaz. Devuelve (window, view, bridge)."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QIcon
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QMainWindow

    from .bridge import Bridge

    class Page(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
            logging.getLogger("allforone.js").info("%s:%s %s", source.rsplit("/", 1)[-1], line, message)

    profile = QWebEngineProfile("AllForOne")
    profile.setPersistentStoragePath(str(paths.web_profile_dir()))
    profile.setCachePath(str(paths.web_profile_dir() / "cache"))

    window = QMainWindow()
    window.setWindowTitle(f"AllForOne {__version__}")
    icon = paths.ui_dir() / "icon.ico"
    if icon.exists():
        window.setWindowIcon(QIcon(str(icon)))
    view = QWebEngineView(window)
    page = Page(profile, view)
    s = page.settings()
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
    s.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
    view.setPage(page)
    # Micrófono para el grabador de la plantilla (contenido local de la propia aplicación)
    if hasattr(page, "permissionRequested"):
        page.permissionRequested.connect(lambda perm: perm.grant())
    else:  # Qt < 6.8
        page.featurePermissionRequested.connect(
            lambda origin, feature: page.setFeaturePermission(
                origin, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser))

    bridge = Bridge(host, window)
    channel = QWebChannel(page)
    channel.registerObject("afo", bridge)
    page.setWebChannel(channel)

    drop_filter = make_drop_filter(view, bridge)
    # El widget interno de Chromium se crea al cargar: se instala el filtro entonces
    view.loadFinished.connect(lambda _ok: install_drop_filter(view, drop_filter))
    install_drop_filter(view, drop_filter)

    view.setUrl(QUrl.fromLocalFile(str(paths.ui_dir() / "index.html")))
    window.setCentralWidget(view)
    window.resize(1600, 900)
    # Mantener referencias vivas
    window._afo = (profile, page, channel, bridge, drop_filter)  # type: ignore[attr-defined]
    return window, view, bridge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="AllForOne")
    parser.add_argument("--selftest", action="store_true", help="Ejecuta la verificación integrada y sale")
    parser.add_argument("--report", help="Ruta del informe JSON de --selftest")
    parser.add_argument("--screenshot", help="Ruta de la captura de --selftest")
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

    window, _view, _bridge = build_window(host)
    window.show()
    rc = app.exec()
    if host.ok:
        host.engine.stop()
    del window
    host.engine = None  # destruir el motor antes que QApplication
    return rc

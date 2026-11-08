"""Interfaz nativa (Qt Quick / QML): sin HTML, sin Chromium.

Reproduce PLANTILLA_DAW.html, que pasa a ser la referencia visual, y habla con Python a través
del mismo `Bridge` que usa la versión web (sus métodos son slots de Qt, así que QML los llama
directamente). Se abre con `python -m allforone --nativo` mientras dura la migración.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, Slot

from . import __version__, paths

log = logging.getLogger("allforone.nativo")

LAYOUT_FILE = "diseno_nativo.json"


def qml_dir() -> Path:
    return paths.package_dir() / "qml"


class LayoutStore(QObject):
    """Posiciones, tamaños, conectores y curvas de cables del lienzo, en la carpeta de datos."""

    def __init__(self, path: Path | None = None):
        super().__init__()
        self.path = path or paths.user_data_dir() / LAYOUT_FILE

    @Slot(result=str)
    def load(self) -> str:
        try:
            return self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return "{}"
        except OSError as exc:
            log.warning("No se pudo leer el diseño: %s", exc)
            return "{}"

    @Slot(str)
    def save(self, data: str) -> None:
        try:
            json.loads(data)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(data, encoding="utf-8")
            tmp.replace(self.path)
        except (OSError, ValueError) as exc:
            log.warning("No se pudo guardar el diseño: %s", exc)


def load_fonts() -> list[str]:
    from PySide6.QtGui import QFontDatabase

    families = []
    for f in sorted((qml_dir() / "fonts").glob("*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(f))
        if fid < 0:
            log.warning("No se pudo cargar la fuente %s", f.name)
        else:
            families += QFontDatabase.applicationFontFamilies(fid)
    return families


def build_native_window(host):
    """Crea la ventana QML. Devuelve (engine, window, bridge)."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QIcon
    from PySide6.QtQml import QQmlApplicationEngine

    from .bridge import Bridge

    load_fonts()
    bridge = Bridge(host, None)
    store = LayoutStore()
    engine = QQmlApplicationEngine()
    errors: list[str] = []
    engine.warnings.connect(lambda ws: errors.extend(w.toString() for w in ws))
    ctx = engine.rootContext()
    ctx.setContextProperty("afo", bridge)
    ctx.setContextProperty("layoutStore", store)
    ctx.setContextProperty("appVersion", __version__)
    engine.load(QUrl.fromLocalFile(str(qml_dir() / "Main.qml")))
    roots = engine.rootObjects()
    if not roots:
        raise RuntimeError("No se pudo cargar la interfaz nativa:\n" + "\n".join(errors))
    window = roots[0]
    icon = paths.ui_dir() / "icon.ico"
    if icon.exists():
        window.setIcon(QIcon(str(icon)))
    engine._afo = (bridge, store, errors)  # type: ignore[attr-defined]  # mantener vivos
    return engine, window, bridge


def run_native_selftest(app, host, report_path: str | None, screenshot_path: str | None) -> int:
    """`AllForOne --nativo --selftest`: la interfaz QML con el motor real, comprobada de verdad."""
    from PySide6.QtCore import QMetaObject, Q_ARG
    from PySide6.QtQuick import QQuickWindow  # noqa: F401  (tipa la ventana raíz)

    from .selftest import Report, _finish, _wait

    def prop(name):
        v = window.property(name)
        return v.toVariant() if hasattr(v, "toVariant") else v

    rep = Report()
    if not rep.check("motor nativo iniciado", host.ok, host.error or ""):
        return _finish(rep, report_path)
    try:
        engine, window, bridge = build_native_window(host)
    except Exception as exc:
        rep.check("interfaz QML cargada", False, str(exc))
        return _finish(rep, report_path)
    window.setWidth(1600)
    window.setHeight(900)
    window.show()
    _wait(app, lambda: False, 1.0, host)
    errors = engine._afo[2]
    rep.check("interfaz QML cargada sin avisos", not errors, errors[:5])
    rep.check("fuente Space Grotesk 500/600/700 cargada", len(load_fonts()) >= 3)

    panels = prop("panelItems")
    rep.check("12 módulos en el lienzo", len(panels or {}) == 12, sorted(panels or {}))
    links = prop("cableLinks")
    rep.check("cables entre módulos", len(links or []) == 7, len(links or []))
    rep.check("motor conectado desde QML", bool(prop("engineOk")))
    rep.check("encuadre inicial aplicado", abs(float(prop("zoom")) - 1.0) > 1e-6, prop("zoom"))

    tone = json.loads(bridge.addTestTone())
    QMetaObject.invokeMethod(window, "addTrack", Q_ARG("QVariant", tone["track"]))
    tracks = prop("tracks") or []
    rep.check("Pistas muestra la pista del motor con su forma de onda",
              len(tracks) == 1 and len(tracks[0]["peaks"]) == 600, [t["name"] for t in tracks])

    dev = host.engine.device_info()
    if dev.get("open"):
        bridge.togglePlay()
        rep.check("transporte del motor visible en QML",
                  _wait(app, lambda: bool(prop("playing")) and int(prop("step")) > 0, 3.0, host),
                  {"step": prop("step")})
        bridge.stop()
    else:
        rep.add("transporte del motor visible en QML", "omitido", "sin dispositivo de salida abierto")

    QMetaObject.invokeMethod(window, "setDark", Q_ARG("QVariant", True))
    QMetaObject.invokeMethod(window, "saveLayout")
    saved = json.loads((paths.user_data_dir() / LAYOUT_FILE).read_text(encoding="utf-8"))
    rep.check("diseño y tema guardados en la carpeta de datos",
              saved.get("theme") == "dark" and len(saved.get("pos", {})) == 12)
    QMetaObject.invokeMethod(window, "setDark", Q_ARG("QVariant", False))

    shot = Path(screenshot_path) if screenshot_path else paths.logs_dir() / "selftest_nativo.png"
    _wait(app, lambda: False, 0.5, host)
    window.grabWindow().save(str(shot))
    rep.add("captura de la interfaz nativa", "info", str(shot))
    window.close()
    return _finish(rep, report_path)

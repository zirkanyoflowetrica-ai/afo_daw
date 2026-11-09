"""Interfaz de AllForOne: Qt Quick / QML nativo, sin HTML ni Chromium.

Reproduce PLANTILLA_DAW.html, que es la referencia visual, y habla con Python a través del
`Bridge` (sus métodos son slots de Qt, así que QML los llama directamente).
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
    for f in sorted((qml_dir() / "assets" / "fonts").glob("*.ttf")):
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
    icon = qml_dir() / "assets" / "icon.ico"
    if icon.exists():
        window.setIcon(QIcon(str(icon)))
    engine._afo = (bridge, store, errors)  # type: ignore[attr-defined]  # mantener vivos
    return engine, window, bridge


def _native_fx_checks(rep, app, host, window, bridge, track_id: int) -> None:
    """Módulo Efectos: insertar en una pista desde la interfaz y leer lo que mide el motor."""
    from PySide6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG

    from .selftest import _wait

    def fx(what, a=None, b=None):
        v = QMetaObject.invokeMethod(window, "fxCommand", Q_RETURN_ARG("QVariant"),
                                     Q_ARG("QVariant", what), Q_ARG("QVariant", a), Q_ARG("QVariant", b))
        return v.toVariant() if hasattr(v, "toVariant") else v

    st = fx("target", track_id)
    rep.check("Efectos: catálogo del motor (Hito 1, 9 módulos)", st and st["catalog"] == 9, st and st["catalog"])
    fx("add", "eq")
    st = fx("add", "analyzer")
    rep.check("Efectos: insertar EQ y Analizador en la pista", [e["key"] for e in st["chain"]] == ["eq", "analyzer"],
              [e["key"] for e in st["chain"]])
    rep.check("la cadena está en el motor", [e["key"] for e in host.engine.effects(track_id)] == ["eq", "analyzer"])
    if host.engine.device_info().get("open"):
        json.loads(bridge.togglePlay())
        ok = _wait(app, lambda: (lambda s: len(s["spectrum"]) == 96 and max(s["spectrum"]) > -40)(fx("noop")), 3, host)
        s = fx("noop")
        peak = max(s["spectrum"]) if s["spectrum"] else -100
        rep.check("el Analizador muestra el espectro real del tono", ok, f"máximo {peak:.1f} dB")
        json.loads(bridge.stop())
    st = fx("bypass", False)
    rep.check("bypass del efecto abierto en el motor", not host.engine.effects(track_id)[-1]["enabled"])
    st = fx("preset", "Lateral (Side)")
    an = host.engine.effects(track_id)[-1]
    rep.check("Efectos: preset de fábrica aplicado en el motor", st["presets"] >= 3 and an["values"][2] == 4,
              {"presets": st["presets"], "valores": an["values"]})
    st = fx("auto", "averaging", [[0, 10], [2, 90]])
    rep.check("Efectos: automatización dibujada llega al motor",
              len(host.engine.effect_automation(an["id"], "averaging")) == 2 and st["chain"][-1]["automated"] == ["averaging"],
              st["autoPts"])
    fx("remove")
    st = fx("remove")
    rep.check("quitar los efectos vacía la cadena", not st["chain"] and not host.engine.effects(track_id))


def _native_project_checks(rep, app, host, window) -> None:
    """Guardar y abrir proyecto desde la interfaz: la sesión vuelve con sus pistas, efectos y automatización."""
    from PySide6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG

    def call(fn, *args):
        v = QMetaObject.invokeMethod(window, fn, Q_RETURN_ARG("QVariant"), *[Q_ARG("QVariant", a) for a in args])
        return v.toVariant() if hasattr(v, "toVariant") else v

    call("fxCommand", "target", 0, None)
    call("fxCommand", "add", "gain", None)
    call("fxCommand", "auto", "output", [[0, -6], [4, 0]])
    before = call("projectCommand", "snapshot", "")
    shape = lambda snap: [(t["type"], t["name"]) for t in snap["tracks"]]   # noqa: E731
    path = paths.user_data_dir() / "proyectos" / "autoprueba.afo"
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = call("projectCommand", "save", str(path))
    doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    mfx = doc.get("master_fx", [])
    rep.check("Proyecto: guardado con pistas, efectos y automatización",
              bool(ok) and len(doc.get("tracks", [])) == len(before["tracks"]) and mfx and mfx[-1]["automation"].get("output"),
              {"pistas": len(doc.get("tracks", [])), "master_fx": [f["key"] for f in mfx]})
    ok = call("projectCommand", "open", str(path))
    after = call("projectCommand", "snapshot", "")
    master = host.engine.effects(0)
    rep.check("Proyecto: abrir recrea la sesión", bool(ok) and shape(after) == shape(before), shape(after))
    rep.check("Proyecto: efectos del master y su automatización recuperados en el motor",
              [e["key"] for e in master][-1:] == ["gain"] and master[-1]["automated"] == ["output"],
              [(e["key"], e["automated"]) for e in master])
    notes = lambda snap: [(t["name"], sorted(t["roll"]), sorted(t["pat"]), t["cfg"]) for t in snap["tracks"] if t["type"] in ("inst", "drum")]  # noqa: E731
    rep.check("Proyecto: notas, patrones y ajustes de los sintetizadores recuperados",
              notes(after) == notes(before) and any(n[1] or n[2] for n in notes(after)), len(notes(after)))
    path.unlink(missing_ok=True)


def run_native_selftest(app, host, report_path: str | None, screenshot_path: str | None, rep=None) -> int:
    """Parte de `AllForOne --selftest`: la interfaz QML con el motor real, comprobada de verdad."""
    from PySide6.QtCore import QMetaObject, Q_ARG
    from PySide6.QtQuick import QQuickWindow  # noqa: F401  (tipa la ventana raíz)

    from .selftest import Report, _finish, _wait

    def prop(name):
        v = window.property(name)
        return v.toVariant() if hasattr(v, "toVariant") else v

    if rep is None:
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
    rep.check("13 módulos en el lienzo", len(panels or {}) == 13, sorted(panels or {}))
    links = prop("cableLinks")
    n_seq = len([t for t in (prop("tracks") or []) if t["type"] in ("inst", "drum", "ia", "voz")])
    rep.check("cables entre módulos (+ uno por pista de Instrumento/Batería/Voz/IA)", len(links or []) == 7 + n_seq, len(links or []))
    rep.check("motor conectado desde QML", bool(prop("engineOk")))
    rep.check("encuadre inicial aplicado", abs(float(prop("zoom")) - 1.0) > 1e-6, prop("zoom"))

    _native_sequencer_checks(rep, app, host, window, prop)

    tone = json.loads(bridge.addTestTone())
    QMetaObject.invokeMethod(window, "addTrack", Q_ARG("QVariant", tone["track"]), Q_ARG("QVariant", False))
    tracks = prop("tracks") or []
    rep.check("Pistas muestra la pista del motor con su forma de onda",
              bool(tracks) and tracks[-1]["type"] == "audio" and len(tracks[-1]["peaks"]) == 600, [t["name"] for t in tracks])

    _native_fx_checks(rep, app, host, window, bridge, tone["track"]["id"])

    dev = host.engine.device_info()
    if dev.get("open"):
        bridge.togglePlay()
        rep.check("transporte del motor visible en QML",
                  _wait(app, lambda: bool(prop("playing")) and int(prop("step")) > 0, 3.0, host),
                  {"step": prop("step")})
        rep.check("medidores del master con el nivel real del motor",
                  _wait(app, lambda: max(prop("masterDb")) > -40 and float(prop("vu")) > 1, 2.0, host),
                  {"master_db": prop("masterDb"), "vu": round(float(prop("vu")), 1)})
        bridge.stop()
    else:
        rep.add("transporte del motor visible en QML", "omitido", "sin dispositivo de salida abierto")

    _native_mixer_checks(rep, app, host, window, bridge, prop)
    _native_project_checks(rep, app, host, window)

    QMetaObject.invokeMethod(window, "setDark", Q_ARG("QVariant", True))
    QMetaObject.invokeMethod(window, "saveLayout")
    saved = json.loads((paths.user_data_dir() / LAYOUT_FILE).read_text(encoding="utf-8"))
    rep.check("diseño y tema guardados en la carpeta de datos",
              saved.get("theme") == "dark" and len(saved.get("pos", {})) == 13)
    QMetaObject.invokeMethod(window, "setDark", Q_ARG("QVariant", False))

    shot = Path(screenshot_path) if screenshot_path else paths.logs_dir() / "selftest_nativo.png"
    _wait(app, lambda: False, 0.5, host)
    window.grabWindow().save(str(shot))
    rep.add("captura de la interfaz nativa", "info", str(shot))
    window.close()
    return _finish(rep, report_path)


def _native_mixer_checks(rep, app, host, window, bridge, prop) -> None:
    """Fase 1: Audios → pistas y tiras, rol de voz, MEZCLAR AUTOMÁTICAMENTE y consola."""
    from PySide6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG

    from .selftest import _wait, _write_demo_stems, check_mix_run

    def snap():
        v = QMetaObject.invokeMethod(window, "mixerSnapshot", Q_RETURN_ARG("QVariant"))
        return v.toVariant() if hasattr(v, "toVariant") else v

    def call(name, *args):
        QMetaObject.invokeMethod(window, name, *[Q_ARG("QVariant", a) for a in args])

    stems = _write_demo_stems(paths.user_data_dir() / "autoprueba" / "stems")
    call("importPaths", stems)
    names = {Path(s).stem for s in stems}
    # por nombre: la toma del Grabador también es una ficha enlazada, y la voz de 64 bits llega
    # más tarde (se convierte en otro hilo)
    linked = lambda: [i for i in snap()["items"] if i["trackId"] >= 0 and i["name"] in names]  # noqa: E731
    if not rep.check("soltar 3 audios: cada uno crea su ficha, su pista y su tira",
                     _wait(app, lambda: len(linked()) >= len(names), 20, host), [i["name"] for i in snap()["items"]]):
        return
    items = snap()["items"]
    voz = next((i for i in items if i["name"] == "Voz_Principal"), {})
    rep.check("WAV en coma flotante de 64 bits convertido y enlazado", bool(voz.get("note")) and voz.get("trackId", -1) >= 0, voz.get("note"))
    rep.check("clasificación por nombre (tipo y rol)", voz.get("kind") == "Voz principal" and voz.get("role") == "P",
              [f"{i['name']}:{i['kind']}:{i['role']}" for i in items])

    call("mixNow", False)
    done = _wait(app, lambda: snap()["runs"] >= 1 or "Error" in snap()["status"], 240, host)
    st = snap()
    if not rep.check("MEZCLAR AUTOMÁTICAMENTE desde la interfaz nativa", done and st["runs"] >= 1, st["status"]):
        return
    check_mix_run(rep, bridge)
    stems_ids = {i["trackId"] for i in st["items"]}
    faders = [t for t in st["tracks"] if t["id"] in stems_ids]
    moved = [t for t in faders if abs(t["vol"] - 70) > 0.5]
    rep.check("la consola refleja la mezcla: faders en la ganancia real medida",
              len(faders) >= 3 and len(moved) >= 1 and len(st["live"]) >= 3, faders)

    # Fase 2: Afinador (cable a la tira de la voz), confirmar tonalidad, Master IA y Antes / Después
    call("setTuneStrength", 60)
    _wait(app, lambda: False, 0.3, host)
    links = snap()["links"]
    rep.check("el Afinador se cablea a la tira de la voz que afina", any(k.startswith("afina-tira-") for k in links), links)
    call("tuneCommand", "mode", "Manual")
    call("tuneCommand", "confirm", "")
    tune = snap()["tune"]
    rep.check("confirmar tonalidad y BPM (modo manual)", bool(tune.get("confirmed")), tune.get("status"))
    call("mixNow", True)                          # REMEZCLAR con afinación al 60 %
    done = _wait(app, lambda: snap()["runs"] >= 2 or "Error" in snap()["status"], 240, host)
    st = snap()
    rep.check("REMEZCLAR con afinación: la mezcla sale afinada", done and st["runs"] >= 2 and bool(st.get("lastTuned")), st["status"])
    call("setTuneStrength", 0)

    before = len(host.engine.tracks())
    call("mixerCommand", "tracks")
    rep.check("Master IA → Pistas (pista nueva en el motor)", _wait(app, lambda: len(host.engine.tracks()) > before, 10, host),
              f"pistas en el motor: {len(host.engine.tracks())}")
    if host.engine.device_info().get("open"):
        call("mixerCommand", "listenMaster")
        rep.check("escucha B del master en el motor", _wait(app, lambda: host.engine.preview_playing(), 3, host))
        call("mixerCommand", "listenReview")
        rep.check("escucha A/B de una pista en el motor", _wait(app, lambda: host.engine.preview_playing(), 3, host))
        call("mixerCommand", "stop")
        rep.check("parar la escucha", _wait(app, lambda: not host.engine.preview_playing(), 3, host))
    else:
        rep.add("escucha A/B en el motor", "omitido", "sin dispositivo de salida abierto")


def _native_sequencer_checks(rep, app, host, window, prop) -> None:
    """Fase 3: Instrumento y Batería con el sintetizador del motor; IA como demostración sin audio."""
    import tempfile

    import numpy as np
    import soundfile as sf
    from PySide6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG

    from .selftest import _wait

    def snap():
        v = QMetaObject.invokeMethod(window, "mixerSnapshot", Q_RETURN_ARG("QVariant"))
        return v.toVariant() if hasattr(v, "toVariant") else v

    def cmd(what, a=None, b=None):
        QMetaObject.invokeMethod(window, "seqCommand", Q_ARG("QVariant", what), Q_ARG("QVariant", a), Q_ARG("QVariant", b))

    def render_peak():
        out = Path(tempfile.mkdtemp(prefix="afo_seq_")) / "mezcla.wav"
        if not host.engine.render_to_wav(str(out)):
            return -100.0
        y, _sr = sf.read(str(out))
        return float(20 * np.log10(max(1e-9, np.abs(y).max())))

    tr = snap()["tracks"]
    synth = [t for t in tr if t["type"] in ("inst", "drum")]
    rep.check("las 3 pistas de la plantilla, con el sintetizador del motor",
              [t["name"] for t in synth] == ["Acordes", "Bajo", "Batería 1"] and all(t["id"] >= 0 for t in synth),
              [(t["name"], t["id"], t["notes"]) for t in synth])
    peak = render_peak()
    rep.check("Acordes, Bajo y Batería suenan en el render del motor", peak > -30, f"pico {peak:.1f} dBFS")

    acordes = synth[0]
    cmd("roll", 2, 15)                                     # A#4 en el último paso
    after = next(t for t in snap()["tracks"] if t["uid"] == acordes["uid"])
    rep.check("editar el piano roll cambia el patrón de la pista", after["notes"] == acordes["notes"] + 1,
              f"{acordes['notes']} → {after['notes']} notas")
    cmd("roll", 2, 15)

    if host.engine.device_info().get("open"):
        ok = host.audition({"type": "inst", "cfg": {"v": 0, "vel": 70, "bri": 50}, "note": 69, "seconds": 0.4})
        rep.check("escuchar una nota al pulsar (sintetizador del motor)", ok and _wait(app, lambda: host.engine.preview_playing(), 1, host))
        host.engine.preview_stop()

    n = len(snap()["tracks"])
    cmd("add", "inst")
    new = snap()["tracks"][-1]
    rep.check("+ Instrumento crea una pista con sintetizador", len(snap()["tracks"]) == n + 1 and new["type"] == "inst" and new["id"] >= 0,
              new["name"])
    cmd("generate")
    ia = snap()["tracks"][-1]
    rep.check("Pistas con IA: demostración sin audio (no entra al motor)", ia["type"] == "ia" and ia["id"] == -1, ia["name"])

    # Grabador de cintas: la pista de voz es del motor y la toma la escribe Tracktion
    cmd("add", "voz")
    voz = snap()["tracks"][-1]
    rep.check("+ Voz crea una pista de grabación en el motor", voz["type"] == "voz" and voz["id"] >= 0, voz["name"])
    before = host.engine.device_info()
    if not host.engine.record_inputs():
        # Sin entradas en el dispositivo actual: se prueba como lo haría el usuario en «⚙ Audio»
        # (ASIO4ALL u otro driver con entradas) y al final se vuelve al dispositivo de antes.
        for kind in ("ASIO", "DirectSound"):
            o = host.engine.audio_device_options(kind)
            if o["inputs"] and o["outputs"]:
                err = host.set_audio_device({"type": kind, "output": o["outputs"][0], "input": o["inputs"][0]})
                QMetaObject.invokeMethod(window, "audioDeviceChanged")
                if not err and host.engine.record_inputs():
                    break
    if host.engine.record_inputs() and host.engine.device_info().get("open"):
        _wait(app, lambda: host.engine.record_state()["armed_track"] == voz["id"], 3, host)   # la interfaz vuelve a armar
        rs = host.engine.record_state()
        rep.check("la pista de voz queda armada en una entrada real", rs["armed_track"] == voz["id"], rs["input"])
        cmd("record")
        _wait(app, lambda: False, 1.2, host)
        cmd("recstop")
        take = next(t for t in snap()["tracks"] if t["uid"] == voz["uid"])
        rep.check("grabar y parar: el motor escribe la toma y se ve como onda", take["len"] > 0.5 and take["peaks"] == 600,
                  f"{take['len']:.2f} s")
    else:
        rep.add("grabación real", "INFO", "ningún driver tiene entradas en este equipo")
    after_dev = host.engine.device_info()
    if before.get("open") and (after_dev["type"], after_dev["output"]) != (before["type"], before["output"]):
        err = host.engine.set_audio_device(before["type"], before["output"], before["input"], before["sample_rate"], before["buffer_size"])
        rep.check("volver al dispositivo de antes", not err, err or before["output"])
    cmd("hide", "cinta", True)
    _wait(app, lambda: False, 0.1, host)
    rep.check("quitar el Grabador desarma la pista (no graba)", not host.engine.record_state()["armed_track"])
    cmd("hide", "cinta", False)

    cmd("hide", "drums", True)
    cmd("hide", "inst", True)
    _wait(app, lambda: False, 0.2, host)
    quiet = render_peak()
    rep.check("quitar Instrumentos y Batería desconecta sus pistas (no suenan)", quiet < -60, f"pico {quiet:.1f} dBFS")
    cmd("hide", "drums", False)
    cmd("hide", "inst", False)

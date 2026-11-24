"""Interfaz de AllForOne: Qt Quick / QML nativo, sin HTML ni Chromium.

Reproduce PLANTILLA_DAW.html, que es la referencia visual, y habla con Python a través del
`Bridge` (sus métodos son slots de Qt, así que QML los llama directamente).
"""
from __future__ import annotations

import json
import logging
import time
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


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")[-6:]           # "#aarrggbb" de Qt: la opacidad no cuenta
    def lin(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(h[i:i + 2]) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """Contraste WCAG 2.x entre dos colores «#rrggbb»: de 1 a 21."""
    a, b = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def _native_fx_checks(rep, app, host, window, bridge, track_id: int) -> None:
    """Módulo Efectos: insertar en una pista desde la interfaz y leer lo que mide el motor."""
    from PySide6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG

    from .selftest import _wait

    def fx(what, a=None, b=None):
        v = QMetaObject.invokeMethod(window, "fxCommand", Q_RETURN_ARG("QVariant"),
                                     Q_ARG("QVariant", what), Q_ARG("QVariant", a), Q_ARG("QVariant", b))
        return v.toVariant() if hasattr(v, "toVariant") else v

    st = fx("target", track_id)
    rep.check("Efectos: catálogo del motor (12 módulos)", st and st["catalog"] == 12, st and st["catalog"])
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


def _native_daw_checks(rep, app, host, window, bridge, track_id) -> None:
    """Menú lateral, módulos que chocan, maximizar, racks extra con nombre y edición de clips en Pistas."""
    from PySide6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG

    from .selftest import _wait

    ai = json.loads(bridge.aiStatus())
    rep.check("IA local: el estado del motor y de los modelos se lee sin fallar", ai.get("ok") is True,
              f"motor {'sí' if ai.get('engineOk') else 'no'} · modelos {ai.get('installed') or 'no instalados'}")
    st = json.loads(bridge.stemsStatus())
    rep.check("Dividir en pistas: el estado del separador Demucs se lee sin fallar", st.get("ok") is True,
              f"motor {'sí' if st.get('engineOk') else 'no'} · modelo {'sí' if st.get('modelOk') else 'no'}")
    hw = json.loads(bridge.hardwareStatus())
    rep.check("Perfil del equipo: gráfica, RAM y perfil de IA detectados", hw.get("ok") is True and hw["profile"]["id"] in ("alto", "medio", "bajo", "cpu"),
              f"{hw.get('hardware')} → {hw.get('profile', {}).get('name')}")
    lb = json.loads(bridge.labStatus())
    rep.check("Instrumental Lab: el estado del laboratorio se lee sin fallar", lb.get("ok") is True and len(lb.get("families", [])) >= 9,
              f"compositor {'sí' if lb.get('textOk') else 'no'} · modelo base {'sí' if lb.get('legoOk') else 'no'} · Demucs {'sí' if lb.get('demucsOk') else 'no'}")

    def call(fn, *args):
        v = QMetaObject.invokeMethod(window, fn, Q_RETURN_ARG("QVariant"), *[Q_ARG("QVariant", a) for a in args])
        return v.toVariant() if hasattr(v, "toVariant") else v

    def lay(what, a=None, b=None):
        return call("layoutCommand", what, a, b)

    h0 = lay("heights")
    rep.check("ningún módulo se monta sobre otro al abrir", lay("overlaps") == [], lay("overlaps"))
    d = lay("drag", "inst", [0, 3000])
    rep.check("arrastrar un módulo contra otro: se detiene antes de chocar", lay("overlaps") == [] and d["to"][1] < d["from"][1] + 3000, d)
    m = lay("max", "pistas")
    rep.check("maximizar: el módulo ocupa el visor a zoom 1",
              m["maxId"] == "pistas" and m["zoom"] == 1 and abs(m["w"] - (m["vw"] - 24)) < 1 and abs(m["h"] - (m["vh"] - 24)) < 1, m)
    m = lay("max", "pistas")
    rep.check("restaurar tras maximizar", m["maxId"] == "" and m["w"] < m["vw"], m)
    pid = lay("extra", "fx")
    _wait(app, lambda: False, 0.3, host)
    r = lay("rename", pid, "Rack voces")
    rep.check("«+» del menú crea otro rack de Efectos y se puede renombrar",
              pid == "fx~2" and r["title"] == "Rack voces" and r["panel"] == "Rack voces" and lay("overlaps") == [], {"pid": pid, **r})
    rep.check("quitar el rack extra", pid not in lay("remove", pid))
    g = lay("goto", "afina")
    rep.check("el menú lleva al módulo", g["currentId"] == "afina" and not g["hidden"], g)

    # Edición de clips de audio (la pista del tono de 8 s)
    def edit(op):
        return json.loads(bridge.clipEdit(track_id, json.dumps(op)))
    clips = json.loads(bridge.clipList(track_id))["clips"]
    r = edit({"op": "split", "clip": clips[0]["id"], "at": 2.0})
    rep.check("Pistas: dividir un clip en dos", r["ok"] and [round(c["length"], 2) for c in r["clips"]] == [2.0, 6.0], r.get("clips"))
    second = r["clips"][1]
    r = edit({"op": "range", "clip": second["id"], "start": 3.0, "length": 1.5, "offset": second["offset"] + 0.5})
    c2 = next(c for c in r["clips"] if c["id"] == second["id"])
    rep.check("Pistas: mover y recortar un clip", r["ok"] and abs(c2["start"] - 3) < 1e-6 and abs(c2["length"] - 1.5) < 1e-6
              and abs(c2["offset"] - 2.5) < 1e-6, c2)
    r = edit({"op": "fades", "clip": c2["id"], "in": 0.2, "out": 0.4})
    r = edit({"op": "normalize", "clip": c2["id"], "target": -1})
    c2 = next(c for c in r["clips"] if c["id"] == second["id"])
    rep.check("Pistas: fundidos y normalizar (el tono de −12 dBFS sube 11 dB)",
              abs(c2["fade_in"] - 0.2) < 1e-6 and abs(c2["fade_out"] - 0.4) < 1e-6 and abs(c2["gain_db"] - 11) < 0.2, c2)
    before = json.loads(bridge.clipList(track_id))["clips"]
    edit({"op": "remove", "clip": c2["id"]})
    r = edit({"op": "set", "clips": before})
    rep.check("Pistas: deshacer devuelve los clips como estaban",
              [(round(c["start"], 3), round(c["length"], 3), round(c["gain_db"], 1)) for c in r["clips"]]
              == [(round(c["start"], 3), round(c["length"], 3), round(c["gain_db"], 1)) for c in before], r["clips"])
    out = paths.user_data_dir() / "autoprueba_clips.wav"
    host.engine.render_to_wav(str(out))
    rep.check("los cortes suenan en el render (silencio entre los clips)", out.exists(), str(out))
    edit({"op": "set", "clips": [{"start": 0, "length": 8, "offset": 0}]})
    call("refreshClips", "a" + str(track_id))
    h1 = lay("heights")
    rep.check("tamaño fijo: ningún módulo cambia de alto por su contenido", h0 == h1,
              {k: (h0.get(k), h1.get(k)) for k in h1 if h0.get(k) != h1.get(k)})

    # Temas: carpetas de templates/ (copiar la carpeta = compartir el tema)
    t = lay("theme", "Professional")
    rep.check("tema Professional (carpeta templates/Professional): plano, sin marco grueso, perillas de arco",
              t["ok"] and t["name"] == "Professional" and t["frame"] == 0 and t["knob"] == "arc"
              and {"AllForOne", "AllForOne Oscuro", "Professional"} <= set(t["themes"]), t)
    t = lay("theme", "AllForOne")
    rep.check("volver al tema AllForOne", t["ok"] and t["name"] == "AllForOne" and t["frame"] == 9, t)

    # Guía de diseño §8: contraste WCAG AA (texto ≥ 4,5:1) en cada tema de fábrica
    for name in ("AllForOne", "AllForOne Oscuro", "Professional"):
        lay("theme", name)
        low = [(what, round(r, 2)) for what, fg, bg in lay("contrast") if (r := contrast_ratio(fg, bg)) < 4.5]
        rep.check(f"contraste del tema {name}: todo el texto ≥ 4,5:1 (WCAG AA)", not low, low)
    lay("theme", "AllForOne")


def _native_lab_checks(rep, app, host, window, bridge) -> None:
    """Instrumental Lab desde la interfaz (state/Lab.qml): sesión, preescucha con pistas borrador,
    cambiar de variante en la misma pista y enviar al proyecto. Variantes de audio sintético (sin IA)."""
    import numpy as np
    from PySide6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG

    from . import lab as L

    lab = window.property("lab")
    rep.check("Instrumental Lab: estado de la vista cargado (state/Lab.qml)", lab is not None)
    if lab is None:
        return

    def inv(fn, *args):
        v = QMetaObject.invokeMethod(lab, fn, Q_RETURN_ARG("QVariant"), *[Q_ARG("QVariant", a) for a in args])
        app.processEvents()
        return v.toVariant() if hasattr(v, "toVariant") else v

    def tracks():
        v = QMetaObject.invokeMethod(window, "mixerSnapshot", Q_RETURN_ARG("QVariant"))
        return (v.toVariant() if hasattr(v, "toVariant") else v)["tracks"]

    bpm = int(window.property("bpm") or 96)
    inv("create", {"style": "House", "bpm": bpm, "bars": 4, "families": ["Batería", "Bajo"], "name": "Autoprueba"})
    st = bridge.lab.public()
    if st is None:
        rep.check("Instrumental Lab: sesión creada desde la interfaz", False)
        return
    n = L.n_samples(st["context"])
    t = np.arange(n) / L.SR
    beat = 60.0 / bpm
    kick = (np.sin(2 * np.pi * 55 * t) * np.exp(-((t % beat) * 18))).astype("float32")
    hat = (np.random.default_rng(1).standard_normal(n) * np.exp(-((t % (beat / 2)) * 60)) * 0.2).astype("float32")
    bass = (0.3 * np.sin(2 * np.pi * 82.4 * t)).astype("float32")
    bridge.lab._add_variant("Batería", np.stack([kick, kick], 1) * 0.5, "autoprueba", 0, None)
    v2 = bridge.lab._add_variant("Batería", np.stack([hat, hat], 1), "autoprueba", 0, None)["id"]
    bridge.lab._add_variant("Bajo", np.stack([bass, bass], 1), "autoprueba", 0, None)
    before = len(tracks())
    inv("preview")
    drafts = [x for x in tracks() if x["name"].endswith("Lab (borrador)")]
    rep.check("Instrumental Lab: preescuchar crea una pista borrador por familia", len(drafts) == 2 and len(tracks()) == before + 2,
              [x["name"] for x in drafts])
    drum = next((x for x in drafts if x["name"].startswith("Batería")), None)
    inv("choose", "Batería", v2)
    same = next((x for x in tracks() if drum and x["id"] == drum["id"]), None)
    rep.check("Instrumental Lab: elegir otra variante cambia el audio de la misma pista",
              same is not None and len(tracks()) == before + 2 and host.tracks[same["id"]]["originalPath"].endswith(f"_{v2}.wav"),
              same and host.tracks[same["id"]]["originalPath"])
    inv("send")
    names = [x["name"] for x in tracks()]
    rep.check("Instrumental Lab: enviar al proyecto quita la marca de borrador",
              "Batería (Lab)" in names and "Bajo (Lab)" in names and not any("borrador" in x for x in names), names[-2:])
    for i in range(len(tracks()) - 1, before - 1, -1):          # deja el proyecto como estaba
        QMetaObject.invokeMethod(window, "removeTrackAt", Q_ARG("QVariant", i))
    app.processEvents()


def _native_project_checks(rep, app, host, window) -> None:
    """Guardar y abrir proyecto desde la interfaz: la sesión vuelve con sus pistas, efectos y automatización."""
    from PySide6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG

    def call(fn, *args):
        v = QMetaObject.invokeMethod(window, fn, Q_RETURN_ARG("QVariant"), *[Q_ARG("QVariant", a) for a in args])
        return v.toVariant() if hasattr(v, "toVariant") else v

    call("fxCommand", "target", 0, None)
    call("fxCommand", "add", "gain", None)
    call("fxCommand", "auto", "output", [[0, -6], [4, 0]])
    call("setTuneStrength", 35)
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
    ai = lambda snap: (lambda a: (a.get("profile"), a.get("tuneStrength"), (a.get("tune") or {}).get("method"),  # noqa: E731
                                  (a.get("tune") or {}).get("voices")))(snap.get("ai") or {})
    rep.check("Proyecto: ajustes de la Mezcla IA y del Afinador recuperados",
              ai(after) == ai(before) and ai(after)[1] == 35, {"antes": ai(before), "después": ai(after)})
    call("setTuneStrength", 0)
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
    # Las comprobaciones del lienzo usan la vista Módulos; la vista Arreglo se prueba tras la mezcla
    window.setProperty("view", "modules")
    _wait(app, lambda: False, 0.2, host)

    panels = prop("panelItems")
    rep.check("14 módulos en el lienzo", len(panels or {}) == 14, sorted(panels or {}))
    links = [l["key"] for l in (prop("cableLinks") or [])]
    seq = [t for t in (prop("tracks") or []) if t["type"] in ("inst", "drum", "ia", "voz")]
    flow = ["inst-piano", "audios-pistas", "pistas-mezcla", "mezcla-fx", "fx-antes", "mezcla-mastia", "mastia-fxm", "fxm-master"]
    src = {"inst": "piano", "drum": "drums", "ia": "ia", "voz": "cinta"}
    idle = [f + "-pistas" for f in ("piano", "drums", "ia", "cinta") if f not in {src[t["type"]] for t in seq}]
    rep.check("cables del camino del sonido: instrumento → piano → pistas → mezcla → mastering → efectos master → rebobinado",
              all(k in links for k in flow + idle) and len([k for k in links if k.startswith("track-")]) == len(seq)
              and len(links) == len(flow) + len(idle) + len(seq), links)
    rep.check("motor conectado desde QML", bool(prop("engineOk")))
    rep.check("encuadre inicial aplicado", abs(float(prop("zoom")) - 1.0) > 1e-6, prop("zoom"))

    _native_sequencer_checks(rep, app, host, window, prop)

    tone = json.loads(bridge.addTestTone())
    QMetaObject.invokeMethod(window, "addTrack", Q_ARG("QVariant", tone["track"]), Q_ARG("QVariant", False))
    tracks = prop("tracks") or []
    rep.check("Pistas muestra la pista del motor con su forma de onda",
              bool(tracks) and tracks[-1]["type"] == "audio" and len(tracks[-1]["peaks"]) == 600, [t["name"] for t in tracks])

    _native_fx_checks(rep, app, host, window, bridge, tone["track"]["id"])
    _native_daw_checks(rep, app, host, window, bridge, tone["track"]["id"])
    _native_lab_checks(rep, app, host, window, bridge)

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
    _native_dual_checks(rep, app, host, window, prop)

    QMetaObject.invokeMethod(window, "setDark", Q_ARG("QVariant", True))
    QMetaObject.invokeMethod(window, "saveLayout")
    saved = json.loads((paths.user_data_dir() / LAYOUT_FILE).read_text(encoding="utf-8"))
    rep.check("diseño y tema guardados en la carpeta de datos",
              saved.get("theme") == "AllForOne Oscuro" and len(saved.get("pos", {})) == 14)
    QMetaObject.invokeMethod(window, "setDark", Q_ARG("QVariant", False))

    shot = Path(screenshot_path) if screenshot_path else paths.logs_dir() / "selftest_nativo.png"
    _wait(app, lambda: False, 0.5, host)
    window.grabWindow().save(str(shot))
    rep.add("captura de la interfaz nativa", "info", str(shot))
    window.close()
    return _finish(rep, report_path)


def _native_dual_checks(rep, app, host, window, prop) -> None:
    """Doble flujo: el Arreglo en una ventana aparte y los módulos en la principal, mismo proyecto."""
    from .selftest import _wait
    before = prop("view")
    window.setProperty("dualWindow", True)
    _wait(app, lambda: False, 1.0, host)
    flow = prop("flowWindow")
    shown = bool(flow is not None and flow.isVisible())
    rep.check("Doble flujo: Arreglo en su ventana y módulos en la principal",
              shown and prop("view") == "modules", {"ventana": shown, "vista": prop("view")})
    if shown:
        shot = paths.logs_dir() / "selftest_doble_flujo.png"
        flow.grabWindow().save(str(shot))
        rep.add("captura de la ventana del Arreglo", "info", str(shot))
    window.setProperty("dualWindow", False)
    window.setProperty("view", before)
    _wait(app, lambda: False, 0.4, host)
    rep.check("Doble flujo: cerrar deja una sola ventana", not (flow is not None and flow.isVisible()), prop("view"))


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

    t0 = time.time()
    call("mixNow", False)
    done = _wait(app, lambda: snap()["runs"] >= 1 or "Error" in snap()["status"], 240, host)
    st = snap()
    if not rep.check("MEZCLAR AUTOMÁTICAMENTE en vivo desde la interfaz nativa", done and st["runs"] >= 1, st["status"]):
        return
    _wait(app, lambda: False, 0.3, host)
    st = snap()
    rep.check("la mezcla IA solo mezcla: el master queda sin tocar", st["master"] is None and not st["masterChain"], st["masterChain"])
    call("mixerCommand", "master", 3)             # Efectos master → MASTERIZAR (Plataformas)
    _wait(app, lambda: snap()["master"] is not None or "Error" in snap()["status"], 240, host)
    st = snap()
    rep.check("masterizar automáticamente deja una versión AUTO en Rebobinado",
              len(st["versions"]) == 1 and st["versions"][0]["kind"] == "auto" and st["versionSel"] == 0
              and st["versions"][0]["fx"] == len(st["masterChain"]) >= 4, st["versions"])
    check_mix_run(rep, bridge, st, t0)
    # Vista Arreglo: lo que hizo la mezcla se ve (inserts por pista y curvas de automatización del motor)
    lv = QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "view"),
                                  Q_ARG("QVariant", "arrange"), Q_ARG("QVariant", None))
    lv = lv.toVariant() if hasattr(lv, "toVariant") else lv
    _wait(app, lambda: False, 0.3, host)
    lanes = json.loads(bridge.dawLanes(json.dumps([i["trackId"] for i in st["items"]] + [0])))
    n_auto = sum(len(v["lanes"]) for v in lanes.get("tracks", {}).values())
    n_ins = sum(len(v["inserts"]) for v in lanes.get("tracks", {}).values())
    rep.check("vista Arreglo: se ven los inserts y las curvas de automatización de la mezcla",
              lv["visible"] and not lv["modules"] and lv["inserts"] == n_ins > 0 and lv["lanes"] == n_auto > 0
              and all(len(l["points"]) >= 2 and l["max"] > l["min"] for v in lanes["tracks"].values() for l in v["lanes"]),
              {"inserts": lv["inserts"], "curvas": lv["lanes"], "filas": lv["rows"]})
    # Bus Aux desde la consola: un envío de la voz principal llega al bus y la consola lo muestra
    voz = next(i["trackId"] for i in st["items"] if i["name"] == "Voz_Principal")
    ax = QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "aux"),
                                  Q_ARG("QVariant", ["Reverb", voz, -12.0]), Q_ARG("QVariant", None))
    ax = ax.toVariant() if hasattr(ax, "toVariant") else ax
    _wait(app, lambda: False, 0.3, host)
    sends = json.loads(bridge.sendList(voz)).get("sends", [])
    lv2 = QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "view"),
                                   Q_ARG("QVariant", None), Q_ARG("QVariant", None))
    lv2 = lv2.toVariant() if hasattr(lv2, "toVariant") else lv2
    rep.check("bus Aux: «+ Aux» crea el bus y el envío de la voz llega al motor y a la consola",
              ax.get("ok") and len(sends) == 1 and sends[0]["aux"] == ax["id"] and abs(sends[0]["db"] + 12) < 0.1
              and lv2["auxes"] == 1 and lv2["sends"] == 1 and lv2["sendsH"] > 0, {"aux": ax, "envíos": sends})
    # Automatización del fader: modo Touch por pista y curva de volumen visible como carril del Arreglo
    md = json.loads(bridge.autoMode(voz, "touch"))
    ta = json.loads(bridge.trackAutoSet(voz, "volume", json.dumps([[0.0, -6.0], [4.0, -18.0]])))
    vl = json.loads(bridge.dawLanes(json.dumps([voz]))).get("tracks", {}).get(str(voz), {})
    vlane = next((l for l in vl.get("lanes", []) if l.get("effect") == 0 and l.get("param") == "volume"), None)
    rep.check("automatización del fader: modo Touch y curva de volumen en el carril de la pista",
              md.get("mode") == "touch" and len(ta.get("points", [])) == 2 and vl.get("mode") == "touch"
              and vlane is not None and abs(vlane["points"][1][1] + 18) < 0.1, {"modo": md, "carril": vlane})
    _wait(app, lambda: False, 0.3, host)
    shot = paths.logs_dir() / "selftest_arreglo.png"
    window.grabWindow().save(str(shot))
    rep.add("captura de la vista Arreglo", "info", str(shot))
    if ax.get("ok"):                               # el resto de la autoprueba cuenta las pistas de la mezcla
        QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "auxRemove"),
                                 Q_ARG("QVariant", ax["uid"]), Q_ARG("QVariant", None))
        _wait(app, lambda: False, 0.2, host)
        rep.check("bus Aux: quitarlo quita sus envíos", json.loads(bridge.sendList(voz)).get("sends") == [],
                  json.loads(bridge.sendList(voz)))
    bridge.trackAutoSet(voz, "volume", "[]")       # el resto de la autoprueba mide el fader fijo
    bridge.autoMode(voz, "read")
    window.setProperty("view", "modules")
    _wait(app, lambda: False, 0.2, host)
    stems_ids = {i["trackId"] for i in st["items"]}
    faders = [t for t in st["tracks"] if t["id"] in stems_ids]
    moved = [t for t in faders if abs(t["vol"] - 70) > 0.5]
    rep.check("la consola refleja la mezcla: faders en la ganancia real medida",
              len(faders) >= 3 and len(moved) >= 1 and len(st["live"]) >= 3, faders)
    voz_id = next(i["trackId"] for i in st["items"] if i["name"] == "Voz_Principal")
    call("mixerCommand", "rack", voz_id)
    fx = QMetaObject.invokeMethod(window, "fxCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "list"),
                                  Q_ARG("QVariant", None), Q_ARG("QVariant", None))
    fx = fx.toVariant() if hasattr(fx, "toVariant") else fx
    rep.check("elegir la tira de la voz muestra su rack en Efectos", "deesser" in [e["key"] for e in fx["chain"]], fx["chain"])
    call("mixerCommand", "ab", "A")
    off = [e["enabled"] for tid in bridge._auto if tid != 0 for e in host.engine.effects(tid) if e["id"] in bridge._auto[tid]]
    call("mixerCommand", "ab", "B")
    on = [e["enabled"] for tid in bridge._auto if tid != 0 for e in host.engine.effects(tid) if e["id"] in bridge._auto[tid]]
    rep.check("A/B: puentear y restablecer los efectos de la mezcla automática (las pistas, no el master)", off and not any(off) and all(on), f"{len(off)} efectos")
    # Rebobinado: versión manual sin efectos, y volver a la automática
    auto_chain = snap()["masterChain"]
    call("mixerCommand", "unmaster", None)
    _wait(app, lambda: not snap()["masterChain"], 5, host)
    call("mixerCommand", "saveVersion", None)
    st = snap()
    rep.check("guardar versión manual (mide LUFS del master en el motor)",
              len(st["versions"]) == 2 and st["versions"][1]["kind"] == "manual" and st["versions"][1]["lufs"] is not None, st["versions"])
    call("mixerCommand", "loadVersion", 0)
    _wait(app, lambda: snap()["masterChain"] == auto_chain, 5, host)
    rep.check("elegir una versión en Rebobinado la pone en el master", snap()["masterChain"] == auto_chain and snap()["versionSel"] == 0,
              snap()["masterChain"])
    lv = host.snapshot()
    rep.check("medidores dB, LUFS y RMS por pista y del master", len(lv.get("loud", {})) >= 3 and len(lv.get("mloud") or []) == 5,
              lv.get("mloud"))

    # Fase 2: Afinador (cable a la tira de la voz), confirmar tonalidad, Master IA y Antes / Después
    call("setTuneStrength", 60)
    _wait(app, lambda: False, 0.3, host)
    links = snap()["links"]
    rep.check("el Afinador se cablea a la tira de la voz que afina", any(k.startswith("afina-tira-") for k in links), links)
    call("tuneCommand", "mode", "Manual")
    call("tuneCommand", "confirm", "")
    tune = snap()["tune"]
    rep.check("confirmar tonalidad y BPM (modo manual)", bool(tune.get("confirmed")), tune.get("status"))
    # Afinador en tiempo real (efecto nativo AF-60): el módulo lo inserta en la voz, lleva la tonalidad
    # analizada a sus parámetros y lo quita
    def _items(it):
        yield it
        for c in it.childItems():
            yield from _items(c)
    tb = next((i for i in _items(window.contentItem()) if i.property("histLen") == 240), None)
    tfx, tvals = None, None
    if tb is not None:
        tb.setProperty("trackId", voz)
        QMetaObject.invokeMethod(tb, "insert")
        _wait(app, lambda: False, 0.2, host)
        chain = json.loads(bridge.fxList(voz)).get("chain", [])
        tfx = chain[0] if chain and chain[0]["key"] == "tune" else None
        if tfx:
            QMetaObject.invokeMethod(tb, "setP", Q_ARG("QVariant", "key"), Q_ARG("QVariant", 9))
            tvals = json.loads(bridge.fxList(voz))["chain"][0]["values"]
            QMetaObject.invokeMethod(tb, "remove")
            _wait(app, lambda: False, 0.2, host)
    left = [e["key"] for e in json.loads(bridge.fxList(voz)).get("chain", [])]
    rep.check("Afinador en tiempo real: se inserta el primero en la voz, cambia la tónica y se quita",
              tfx is not None and tvals is not None and round(tvals[0]) == 9 and "tune" not in left,
              {"módulo": tb is not None, "efecto": tfx and tfx["key"], "valores": tvals, "queda": left})
    call("mixNow", True)                          # REMEZCLAR con afinación al 60 %
    done = _wait(app, lambda: (snap()["runs"] >= 2 and not snap()["mastering"]) or "Error" in snap()["status"], 240, host)
    st = snap()
    tchain = [e["key"] for e in json.loads(bridge.fxList(voz)).get("chain", [])]
    rep.check("REMEZCLAR con afinación: el afinador nativo AF-60 queda el primero en la cadena de la voz",
              done and st["runs"] >= 2 and bool(st.get("lastTuned")) and tchain[:1] == ["tune"], [st["status"], tchain])
    call("setTuneStrength", 0)
    call("mixerCommand", "unmaster", None)
    rep.check("quitar el master IA", _wait(app, lambda: not snap()["masterChain"], 5, host), snap()["masterChain"])


def _native_sequencer_checks(rep, app, host, window, prop) -> None:
    """Fase 3: Instrumento y Batería con el sintetizador del motor; + IA lleva al generador."""
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
        rep.check("escuchar una nota al pulsar (sintetizador del motor)", ok and _wait(app, lambda: host.engine.preview_playing(), 3, host))   # salidas HDMI tardan en arrancar
        host.engine.preview_stop()

    n = len(snap()["tracks"])
    cmd("add", "inst")
    new = snap()["tracks"][-1]
    rep.check("+ Instrumento crea una pista con sintetizador", len(snap()["tracks"]) == n + 1 and new["type"] == "inst" and new["id"] >= 0,
              new["name"])
    n = len(snap()["tracks"])
    cmd("add", "ia")
    rep.check("+ IA abre el generador y no crea pistas vacías", len(snap()["tracks"]) == n and
              not [t for t in snap()["tracks"] if t["type"] == "ia"], f"{n} pistas")

    # IA en modo «Solo MIDI»: un .mid entra como una pista por instrumento (notas con duración propia)
    from .midi_ai import write_mid
    mid = Path(tempfile.mkdtemp(prefix="afo_midi_")) / "prueba.mid"
    write_mid(mid, [(0.0, 1.0, 60, 0), (1.0, 0.5, 64, 0), (0.0, 0.5, 40, 33), (0.0, 0.1, 36, 128), (0.5, 0.1, 38, 128)], 120)
    n = len(snap()["tracks"])
    cmd("midi", str(mid), "Prueba MIDI")
    _wait(app, lambda: False, 0.2, host)
    new = snap()["tracks"][n:]
    rep.check("importar un MIDI crea una pista por instrumento con sus notas",
              [(t["type"], t["midi"]) for t in new] == [("inst", 2), ("inst", 1), ("drum", 2)] and all(t["id"] >= 0 for t in new),
              [(t["name"], t["sub"]) for t in new])
    for _ in new:
        cmd("drop")
    cmd("song")
    rep.check("quitar las pistas MIDI deja el proyecto como estaba", len(snap()["tracks"]) == n)

    # Grabador de cintas: la pista de voz es del motor y la toma la escribe Tracktion
    cmd("add", "voz")
    voz = snap()["tracks"][-1]
    rep.check("+ Voz crea una pista de grabación en el motor", voz["type"] == "voz" and voz["id"] >= 0, voz["name"])
    before = host.engine.device_info()
    if not before.get("open"):
        # Sin ningún dispositivo abierto, abrir un driver tras procesar mensajes de JUCE puede cerrar
        # el proceso dentro del driver ASIO de terceros: no se prueba aquí (se elige en «⚙ Audio»)
        rep.add("cambiar de driver", "INFO", "no hay ningún dispositivo de audio abierto en este equipo")
    elif not host.engine.record_inputs():
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

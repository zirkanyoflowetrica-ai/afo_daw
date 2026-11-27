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
    """Distribución guardada de la ventana (vista, pestañas de cada zona, alto del detalle, tema), en la carpeta de datos."""

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


def _f4_checks(rep, host, lay, call, track_id: int) -> None:
    """F4 (FLUJO_PROFESIONAL §3): la IA sobre el clip deja tomas o carpeta, sin botones fijos.
    Sin IA real: el resultado de la IA se simula con copias del audio de la pista."""
    import shutil
    import tempfile
    uid = "a" + str(track_id)
    orig = host.tracks[track_id]["originalPath"]
    tmp = Path(tempfile.mkdtemp(prefix="afo_f4_"))
    c1, c2 = tmp / "rehecha.wav", tmp / "otra.wav"
    shutil.copy(orig, c1)
    shutil.copy(orig, c2)

    def st():
        return lay("f4")

    def trk(s, u):
        return next((t for t in s["tracks"] if t["uid"] == u), {})

    s0 = st()
    rep.check("F4: la barra del Arreglo no tiene botones fijos de IA (Rehacer, Versión, Alinear, Separar)",
              not any(w in t for t in s0["tools"] for w in ("IA", "Alinear", "Separar", "Versión")), s0["tools"])
    boxes = {m: lay("aiBox", m, uid) for m in ("repaint", "cover", "align")}
    rep.check("F4: Rehacer, Versión y Alinear se abren en un cuadro junto al clip que dice dónde va el resultado",
              all(b["opened"] for b in boxes.values()) and "toma nueva" in boxes["repaint"]["where"]
              and "carpeta" in boxes["cover"]["where"] and "toma nueva" in boxes["align"]["where"]
              and boxes["repaint"]["can"] in (True, False), {m: b["opened"] for m, b in boxes.items()})

    # Rehacer → toma nueva en la misma pista; elegir la toma 1 vuelve al archivo; Ctrl+Z quita la toma
    lay("seqSet", "repaintUid", uid)
    lay("seq", "applyRepaint", [{"repaint": {"trackId": track_id, "start": 0.0, "end": 2.0}, "path": str(c1),
                                 "message": "Rehecho (simulado)"}])
    s1 = st()
    t1 = trk(s1, uid)
    src1 = host.tracks[track_id]["originalPath"]
    lay("seq", "useTake", [uid, 0])
    src_back = host.tracks[track_id]["originalPath"]
    lay("seq", "useTake", [uid, 1])
    snap = next((x for x in st()["snap"] if x["uid"] == uid), {})
    lay("arrUndo", uid)
    t_undo = trk(st(), uid)
    src_undo = host.tracks[track_id]["originalPath"]
    rep.check("F4: «Rehacer» entra como toma nueva (sin IA real: copia del audio); la toma 1 vuelve al original y Ctrl+Z quita la toma",
              t1.get("takes") == ["Toma 1", "Rehecha (IA) 1"] and t1.get("take") == 1 and Path(src1) == c1
              and Path(src_back) == Path(orig) and snap.get("takes") == 2 and snap.get("take") == 1
              and t_undo.get("takes") == [] and Path(src_undo) == Path(orig),
              {"tomas": t1.get("takes"), "guardado": snap, "tras Ctrl+Z": t_undo.get("takes")})

    # Separar → pistas en la carpeta de la original (silenciada); Versión → otra pista en la carpeta
    n0 = len(s0["tracks"])
    lay("seq", "onAiEvent", [{"type": "stems", "ok": True, "trackId": track_id, "name": "Tono", "message": "Separada (simulado)",
                              "stems": [{"path": str(c1), "label": "Voz"}, {"path": str(c2), "label": "Resto"}]}])
    lay("seqSet", "coverUid", uid)
    lay("seq", "applyCover", [{"path": str(c2), "title": "Versión", "cover": {"at": 1.0}, "message": "Versión (simulada)"}])
    s2 = st()
    ix = [t["uid"] for t in s2["tracks"]].index(uid)
    kids = s2["tracks"][ix + 1:ix + 4]
    lay("seq", "toggleFold", [uid])
    s3 = st()
    rep.check("F4: «Separar» y «Versión» dejan pistas en la carpeta de la original (silenciada al separar); plegarla las oculta sin silenciarlas",
              len(s2["tracks"]) == n0 + 3 and len(kids) == 3 and all(k["folder"] == uid for k in kids)
              and trk(s2, uid)["mute"] and not any(k["mute"] for k in kids)
              and not any(k["uid"] in s3["rows"] for k in kids) and uid in s3["rows"]
              and all(x["folder"] == uid for x in s2["snap"] if x["uid"] in [k["uid"] for k in kids]),
              {"carpeta": [k["name"] for k in kids], "filas plegada": len(s3["rows"])})
    # deja el proyecto como estaba para las comprobaciones siguientes
    lay("seq", "toggleFold", [uid])
    for k in kids:
        lay("dropTrack", k["uid"])
    lay("seq", "replace", [uid, {"mute": False}])
    call("syncTrackStates")
    shutil.rmtree(tmp, ignore_errors=True)


def _f5_checks(rep, host, lay, track_id: int) -> None:
    """F5: «Pista nueva» reúne la IA (fuera Navegador › IA y la vista Crear IA) y lo regenerado entra
    como toma. Sin IA real: la generación se simula con copias del audio de una pista."""
    import shutil
    import tempfile
    nb = lay("newTrack", "")
    lab = lay("newTrack", "lab")
    lay("newTrack", "close")
    rep.check("F5: un diálogo «Pista nueva» con Audio, Instrumento, Batería, Voz, Intérprete IA, Generar con IA y Por piezas; sin Navegador › IA ni vista Crear IA",
              nb["opened"] and nb["kinds"] == ["audio", "inst", "drum", "voz", "interp", "gen", "lab"]
              and "ia" not in nb["nav"] and lab["opened"] and lab["page"] == "lab" and lab["view"] != "lab",
              {"tipos": nb["kinds"], "navegador": nb["nav"], "por piezas": [lab["page"], lab["view"]]})
    orig = host.tracks[track_id]["originalPath"]
    tmp = Path(tempfile.mkdtemp(prefix="afo_f5_"))
    c1, c2 = tmp / "generada.wav", tmp / "regenerada.wav"
    shutil.copy(orig, c1)
    shutil.copy(orig, c2)
    n0 = len(lay("f4")["tracks"])
    lay("seqSet", "genUid", "")
    lay("seqSet", "genKind", "song")
    lay("seq", "onAiEvent", [{"type": "aiGenerate", "phase": "done", "ok": True, "path": str(c1), "title": "Prueba F5",
                              "message": "Generada (simulado)"}])
    s1 = lay("f4")
    new = s1["tracks"][-1] if len(s1["tracks"]) == n0 + 1 else {}
    uid = new.get("uid", "")
    lay("seqSet", "genUid", uid)
    lay("seq", "onAiEvent", [{"type": "aiGenerate", "phase": "done", "ok": True, "path": str(c2), "title": "Prueba F5",
                              "message": "Regenerada (simulado)"}])
    s2 = lay("f4")
    again = next((t for t in s2["tracks"] if t["uid"] == uid), {})
    src = host.tracks[new["id"]]["originalPath"] if new else ""
    snap = next((x for x in s2["snap"] if x["uid"] == uid), {})
    lay("arrUndo", uid)
    undone = next((t for t in lay("f4")["tracks"] if t["uid"] == uid), {})
    rep.check("F5: lo generado entra como pista que recuerda cómo se hizo y «Regenerar» pone otra versión como toma de esa pista (sin IA real: copias del audio)",
              bool(new) and new.get("gen") and len(s2["tracks"]) == n0 + 1 and again.get("takes") == ["Toma 1", "Generada 1"]
              and again.get("take") == 1 and Path(src) == c2 and snap.get("gen") and snap.get("takes") == 2
              and undone.get("takes") == [],
              {"pista": new.get("name"), "tomas": again.get("takes"), "tras Ctrl+Z": undone.get("takes")})
    if uid:
        lay("dropTrack", uid)
    shutil.rmtree(tmp, ignore_errors=True)


def _backdrop_images(folder) -> tuple[str, str]:
    """Imagen de peor caso (negro puro a blanco puro) y una carpeta de parallax de 3 capas."""
    import numpy as np
    from PySide6.QtGui import QImage
    folder.mkdir(parents=True, exist_ok=True)

    def save(a, p):
        a = np.ascontiguousarray(a, dtype=np.uint8)
        h, w = a.shape[:2]
        QImage(a.tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888).copy().save(str(p))
    w, h = 1600, 900
    g = np.zeros((h, w, 4), np.uint8)
    g[..., :3] = np.linspace(0, 255, w).astype(np.uint8)[None, :, None]
    g[:, :200, :3] = 0                                      # zonas planas: el desenfoque no las toca
    g[:, -200:, :3] = 255
    g[..., 3] = 255
    save(g, folder / "peor_caso.png")
    par = folder / "capas"
    par.mkdir(exist_ok=True)
    save(g, par / "1.png")
    for i, col in ((2, (40, 90, 160)), (3, (200, 120, 40))):
        c = np.zeros((h, w, 4), np.uint8)
        c[h - 120 * i:, :, :3] = col
        c[h - 120 * i:, :, 3] = 255
        save(c, par / f"{i}.png")
    return str(folder / "peor_caso.png"), str(par)


def _g1_checks(rep, host, lay) -> None:
    """G1: metrónomo (el clic de Tracktion), bucle desde la sección o arrastrando en la regla, saltos entre
    secciones; todo se guarda con el proyecto. Que el bucle y el clic suenan se mide en tests/test_transporte.py."""
    eng = host.engine
    t0 = lay("transport")
    rep.check("G1: de fábrica sin metrónomo ni bucle (ni en el motor)",
              not t0["clickOn"] and not t0["loop"]["on"] and not t0["band"]["visible"] and not eng.click_enabled()
              and not eng.loop()["on"], {"interfaz": [t0["clickOn"], t0["loop"]], "motor": [eng.click_enabled(), eng.loop()]})
    a = lay("run", "transport.metronome")
    on = eng.click_enabled()
    b = lay("run", "transport.metronome")
    rep.check("G1: «Metrónomo» (C) enciende y apaga el clic del motor; el menú lo marca",
              a["ok"] and a["checked"] and on and b["ok"] and not b["checked"] and not eng.click_enabled(), {"encendido": a, "apagado": b})
    old = t0["markers"]
    lay("transport", "markers", [{"start": 0, "end": 4, "label": "A"}, {"start": 4, "end": 12, "label": "B"},
                                 {"start": 12, "end": 20, "label": "A"}])
    lay("transport", "seek", 6.0)
    s = lay("run", "transport.loopSection")
    t1 = lay("transport")
    el = eng.loop()
    band = t1["band"]
    rep.check("G1: «Bucle en la sección del cursor» (Ctrl+L) repite la sección B (4–12 s) en el motor y se ve en la regla",
              s["ok"] and t1["loop"]["on"] and abs(t1["loop"]["start"] - 4) < 1e-3 and abs(t1["loop"]["end"] - 12) < 1e-3
              and el["on"] and abs(el["start"] - 4) < 1e-3 and abs(el["end"] - 12) < 1e-3
              and band["visible"] and band["on"] and abs(band["w"] - 8 * t1["pps"]) < 1.5,
              {"bucle": t1["loop"], "motor": el, "franja": band})
    lay("transport", "seek", 6.0)
    n = lay("run", "transport.nextMarker")
    pn = lay("transport")["posSec"]
    p = lay("run", "transport.prevMarker")
    pp = lay("transport")["posSec"]
    p0 = lay("run", "transport.prevMarker")
    rep.check("G1: «,» y «.» saltan al principio de la sección anterior y siguiente (y a 0)",
              n["ok"] and abs(pn - 12) < 1e-3 and p["ok"] and abs(pp - 4) < 1e-3 and p0["ok"] and lay("transport")["posSec"] == 0,
              {"siguiente": pn, "anterior": pp})
    lay("transport", "drag", [9.0, 2.0])
    t2 = lay("transport")
    lp = lay("run", "transport.loop")
    t3 = lay("transport")
    rep.check("G1: arrastrar en la regla marca el tramo (2–9 s) y lo enciende; «Bucle» (L) lo apaga y el tramo queda marcado",
              abs(t2["loop"]["start"] - 2) < 1e-3 and abs(t2["loop"]["end"] - 9) < 1e-3 and t2["loop"]["on"]
              and lp["ok"] and not lp["checked"] and not t3["loop"]["on"] and not eng.loop()["on"]
              and t3["band"]["visible"] and not t3["band"]["on"], {"arrastre": t2["loop"], "apagado": t3["loop"], "franja": t3["band"]})
    rep.check("G1: el proyecto guarda el metrónomo y el bucle",
              t3["project"]["loop"] == t3["loop"] and t3["project"]["click"] == {"on": False, "vol": t3["clickVol"]}, t3["project"])
    lay("transport", "markers", old)
    lay("transport", "seek", 0.0)


def _g2_checks(rep, window, host, lay) -> None:
    """G2: el teclado MIDI arma la pista de instrumento en el motor, sus teclas suenan por él y «Cuantizar» (Q)
    alinea las notas. Que lo tocado se graba de verdad se mide en tests/test_midi_teclado.py."""
    from PySide6.QtCore import QObject
    eng = host.engine
    m0 = lay("midi")
    acts = lay("actions")
    rep.check("G2: «Tocar con el teclado MIDI» (Pista) y «Cuantizar notas» (Clip, Q) en los menús, con su función",
              all(i in acts["ids"] and i not in acts["missing"] for i in ("track.midiKeys", "clip.quantize")) and m0["active"] and not m0["armed"],
              {"faltan": acts["missing"], "pista": m0["active"]})
    a = lay("run", "track.midiKeys")
    m1 = lay("midi")
    rs = eng.record_state()
    rep.check("G2: «Teclado MIDI» arma la pista de instrumento activa en el motor (entrada «MIDI»)",
              a["ok"] and a["checked"] and m1["armed"] == m1["active"] and eng.midi_armed() and rs["input"] == "MIDI",
              {"accion": a, "motor": rs})
    on, off = lay("midi", "key", [60, True]), lay("midi", "key", [60, False])
    rep.check("G2: las teclas (pantalla u ordenador) tocan la pista armada por el motor", on["ok"] and off["ok"], [on, off])
    old = m1["midi"]
    lay("midi", "grid", "1/8")
    lay("midi", "set", [[0.06, 0.4, 60, 90], [0.53, 0.2, 64, 90], [1.24, 0.3, 67, 90]])
    q = lay("run", "clip.quantize")
    m2 = lay("midi")
    rep.check("G2: «Cuantizar» (Q) lleva los inicios a la rejilla elegida (1/8) y conserva la duración",
              q["ok"] and [n[0] for n in m2["midi"] or []] == [0, 0.5, 1.0] and [n[1] for n in m2["midi"]] == [0.4, 0.2, 0.3],
              m2["midi"])
    lay("midi", "set", old)
    lay("midi", "grid", "1/16")
    b = lay("run", "track.midiKeys")
    rep.check("G2: volver a pulsar «Teclado MIDI» suelta la pista (el motor queda sin entrada MIDI)",
              b["ok"] and not b["checked"] and not eng.midi_armed() and not lay("midi")["armed"], b)
    small = [n for n in ("midiArmBtn", "midiRecBtn", "qGridSel", "qEndsBtn", "quantizeBtn")
             if (o := window.findChild(QObject, n)) is not None and o.property("height") < 24]
    rep.check("G2: los controles del teclado MIDI en el Piano roll miden ≥ 24 px",
              window.findChild(QObject, "midiBar") is not None and not small, small)


def _g5_checks(rep, window, host, lay) -> None:
    """G5: «Consolidar clips en un audio» y «Congelar pista» en el menú de la pista. Que el audio
    consolidado suena igual y que lo congelado lleva los efectos lo mide tests/test_congelar_consolidar.py."""
    import tempfile
    from pathlib import Path

    import numpy as np
    import soundfile as sf
    from PySide6.QtCore import QObject

    eng = host.engine
    a = lay("rec", "add")
    b = lay("rec", "add")
    tid, uid = b["id"], b["uid"]
    folder = Path(tempfile.mkdtemp(prefix="afo_consolidar_"))
    src, sr = folder / "voz.wav", 48000
    t = np.arange(int(3 * sr)) / sr
    sf.write(str(src), (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sr)
    eng.set_track_audio(tid, str(src), 0.0)
    host.tracks[tid] = dict(host.tracks.get(tid, {}), source_path=str(src), originalPath=str(src))
    prev = {"source": str(src), "clips": eng.clips(tid)}
    first = eng.split_clip(prev["clips"][0]["id"], 1.5)
    eng.set_clip_range(first[1]["id"], 2.0, first[1]["length"], first[1]["offset"])     # hueco de 0,5 s
    info = dict(next(x for x in eng.tracks() if x["id"] == tid))
    info.update(takes=[], clips=eng.clips(tid), previous=prev, peaks=[])
    lay("rec", "apply", info)
    lay("select", lay("rec", "index", uid)["index"])
    c = lay("run", "track.consolidate")
    st = lay("rec")
    now = eng.clips(tid)
    out = host.tracks[tid].get("originalPath", "")
    rep.check("G5: «Consolidar clips en un audio» deja un clip en un archivo nuevo y lo de antes como toma",
              c["ok"] and len(now) == 1 and out.endswith("voz_consolidado.wav") and Path(out).is_file()
              and st["active"]["takes"] == ["Antes de consolidar", "Consolidada"] and st["active"]["take"] == 1,
              {"clips": len(now), "archivo": Path(out).name, "tomas": st["active"]["takes"]})
    u = lay("rec", "take", [uid, 0])
    rep.check("G5: la toma «Antes de consolidar» devuelve los clips y el archivo de antes",
              u["ok"] and len(eng.clips(tid)) == 2 and host.tracks[tid].get("originalPath") == str(src))
    f = lay("run", "track.freeze")
    st = lay("rec", "index", uid)
    view = lay("run", "view.arrange")                     # la cabecera de la pista, en el Arreglo
    lay("zones")
    def walk(it):                                   # los delegados de un Repeater solo son hijos visuales
        for c in it.childItems():
            yield c
            yield from walk(c)
    every = [i for i in walk(window.contentItem()) if i.objectName() == "frozenBtn"]
    btns = [o for o in every if o.isVisible()]
    rep.check("G5: «Congelar pista» la congela en el motor, se ve «❄ congelada» en su cabecera y bloquea consolidar",
              f["ok"] and eng.track_frozen(tid) and bool(eng.frozen_file(tid)) and st["frozen"] and len(btns) == 1
              and not lay("run", "track.consolidate")["enabled"] and not f["enabled"],
              {"motor": eng.track_frozen(tid), "botones": len(btns), "todos": len(every), "fila": st, "arreglo": view})
    rep.check("G5: el botón «❄» de la cabecera mide ≥ 24 px", bool(btns) and btns[0].property("height") >= 24,
              btns[0].property("height") if btns else None)
    z = lay("run", "track.unfreeze")
    rep.check("G5: «Descongelar pista» vuelve a procesar en vivo (sin archivo congelado)",
              z["ok"] and not eng.track_frozen(tid) and eng.frozen_file(tid) == "" and not lay("rec", "index", uid)["frozen"])
    lay("rec", "remove", a["uid"])
    lay("rec", "remove", uid)


def _g7_checks(rep, window, host, lay) -> None:
    """G7: «Escribir notas con IA» (Clip y botón del Piano roll) escribe en la pista de instrumento, en la
    rejilla, y «Notas de antes» la deja como estaba. La composición con el modelo local y que las notas
    suenan en su sitio lo miden tests/test_midi_ia_rejilla.py; aquí llega su evento a la interfaz."""
    acts = lay("actions")
    rep.check("G7: «Escribir notas con IA» y «Volver a las notas de antes de la IA» en el menú Clip, con su función",
              all(i in acts["ids"] and i not in acts["missing"] and i in acts["clip"] for i in ("clip.aiNotes", "clip.aiNotesUndo")),
              {"faltan": acts["missing"]})

    def walk(it):
        for c in it.childItems():
            yield c
            yield from walk(c)
    btn = [i for i in walk(window.contentItem()) if i.objectName() == "aiNotesBtn"]
    rep.check("G7: botón «Escribir con IA» en el Piano roll (≥ 24 px)", len(btn) == 1 and btn[0].property("height") >= 24,
              btn[0].property("height") if btn else None)
    m0 = lay("midi")
    old = m0["midi"]
    lay("midi", "set", [[0.0, 4.0, 48, 100], [20.0, 1.0, 50, 100]])
    lay("midi", "grid", "1/8")
    ev = {"type": "aiMidi", "phase": "done", "ok": True, "message": "", "family": "Piano / teclados",
          "tracks": [{"type": "inst", "program": 0, "name": "Piano IA", "midi": [[0.04, 0.45, 60, 96], [0.55, 0.3, 64, 96],
                                                                              [1.1, 0.9, 67, 96], [7.7, 2.0, 72, 96]]}]}
    m1 = lay("midi", "aievent", {"span": [16, 24], "ev": ev})
    rep.check("G7: las notas de la IA entran en la pista que las pidió, en la rejilla (1/8), cortadas a su tramo y sustituyendo lo que había en él",
              m1["aiPrev"] and m1["fillUid"] == "" and m1["midi"] == [[0.0, 4.0, 48, 100], [16.0, 0.5, 60, 96], [16.5, 0.5, 64, 96],
                                                                       [17.0, 1.0, 67, 96], [23.5, 0.5, 72, 96]],
              m1["midi"])
    u = lay("run", "clip.aiNotesUndo")
    m2 = lay("midi")
    rep.check("G7: «Volver a las notas de antes» deja la pista como estaba",
              u["ok"] and m2["midi"] == [[0.0, 4.0, 48, 100], [20.0, 1.0, 50, 100]] and not m2["aiPrev"], m2["midi"])
    lay("midi", "set", old)
    lay("midi", "grid", "1/16")


def _g6_checks(rep, window, host, lay) -> None:
    """G6: grupos VCA en el Mezclador («+ VCA», una tira por grupo con sus pistas y su fader). Que el
    fader del grupo baja sus pistas y no las demás lo mide tests/test_vca.py en canciones completas."""
    eng = host.engine
    a = lay("rec", "add")
    b = lay("rec", "add")
    lay("run", "view.mixer")

    def walk(it):
        for c in it.childItems():
            yield c
            yield from walk(c)

    def named(n):
        return [i for i in walk(window.contentItem()) if i.objectName() == n and i.isVisible()]

    add = named("mixAddVca")
    v = lay("vca", "add", "Coros")
    gid = v["vcas"][-1]["id"] if v["vcas"] else -1
    lay("zones")
    rep.check("G6: «+ VCA» en la barra del Mezclador crea un grupo y su tira aparece junto al master",
              len(add) == 1 and v["ok"] and len(eng.vcas()) == 1 and len(named("vcaStrip")) == 1
              and add[0].property("height") >= 24, {"vcas": v["vcas"], "tiras": len(named("vcaStrip"))})
    m = lay("vca", "members", [gid, [a["id"], b["id"]]])
    lay("zones")
    rep.check("G6: meter dos pistas en el grupo (motor y tira: una «×» por pista)",
              m["ok"] and sorted(eng.vcas()[0]["members"]) == sorted([a["id"], b["id"]]) and len(named("vcaOut")) == 2,
              {"motor": eng.vcas(), "x": len(named("vcaOut"))})
    p = lay("vca", "pos", [gid, 35])
    rep.check("G6: el fader del grupo pone su ganancia en el motor (35 = −12 dB) y se guarda en el proyecto",
              abs(eng.vcas()[0]["db"] + 12.04) < 0.1 and p["project"][0]["pos"] == 35
              and sorted(p["project"][0]["members"]) == sorted([a["uid"], b["uid"]]),
              {"db": eng.vcas()[0]["db"], "proyecto": p["project"]})
    r = lay("vca", "remove", gid)
    lay("zones")
    rep.check("G6: quitar el grupo deja las pistas sueltas", r["ok"] and eng.vcas() == [] and eng.track_vca(a["id"]) == 0
              and not named("vcaStrip") and r["project"] == [])
    lay("rec", "remove", a["uid"])
    lay("rec", "remove", b["uid"])
    lay("run", "view.arrange")


def _g4_checks(rep, window, host, lay) -> None:
    """G4: «Escucha» en el editor del compresor y de la puerta: la cadena lateral a otra pista. Que de
    verdad suena (el bajo respira con el bombo, la puerta abre al golpe) lo mide tests/test_sidechain.py."""
    from PySide6.QtCore import QMetaObject, QObject, Q_ARG, Q_RETURN_ARG

    def fx(what, a=None, b=None):
        v = QMetaObject.invokeMethod(window, "fxCommand", Q_RETURN_ARG("QVariant"),
                                     Q_ARG("QVariant", what), Q_ARG("QVariant", a), Q_ARG("QVariant", b))
        v = v.toVariant() if hasattr(v, "toVariant") else v
        lay("zones")                                       # deja pintar
        return v

    eng = host.engine
    a = lay("rec", "add")
    b = lay("rec", "add")
    fx("target", a["id"])
    st = fx("add", "compressor")
    row, sel = window.findChild(QObject, "keyRow"), window.findChild(QObject, "keySel")
    srcs = [o[0] for o in st["keySources"]]
    rep.check("G4: el compresor ofrece «Escucha» con las demás pistas (no la suya ni el master)",
              st["canKey"] and row is not None and bool(row.property("visible")) and str(b["id"]) in srcs
              and str(a["id"]) not in srcs and "0" == srcs[0], {"fuentes": st["keySources"]})
    k = fx("key", b["id"])
    info = eng.effect_info(k["sel"])
    off = fx("key", 0)
    rep.check("G4: elegir una pista en «Escucha» conecta la cadena lateral en el motor y «Su propia señal» la quita",
              k["key"] == b["id"] and info["sidechain"] == b["id"] and off["key"] == 0
              and eng.effect_info(k["sel"])["sidechain"] == 0, {"escucha": k["key"], "motor": info["sidechain"]})
    rep.check("G4: el selector de «Escucha» mide ≥ 24 px", sel is not None and sel.property("height") >= 24,
              sel.property("height") if sel is not None else None)
    fx("add", "eq")
    rep.check("G4: un efecto sin cadena lateral (EQ) no muestra «Escucha»", row is not None and not row.property("visible"))
    lay("rec", "remove", a["uid"])
    lay("rec", "remove", b["uid"])


def _g3_checks(rep, window, host, lay) -> None:
    """G3: grabar en varias pistas a la vez, punch dentro del tramo del bucle y elegir la toma que suena.
    Que se graba de verdad (dos pistas, punch que conserva lo de fuera, una toma por vuelta) lo mide
    tests/test_grabacion_multipista.py con la entrada del dispositivo."""
    import tempfile
    from pathlib import Path

    import numpy as np
    import soundfile as sf
    from PySide6.QtCore import QObject

    eng = host.engine
    lay("transport", "drag", [2.0, 5.0])                   # tramo 2–5 s (el arrastre enciende el bucle)
    if lay("transport")["loop"]["on"]:
        lay("run", "transport.loop")                       # punch: con el bucle apagado
    p1 = lay("rec", "punch", True)
    on = eng.punch()
    p2 = lay("rec", "punch", False)
    rep.check("G3: «Punch» con el tramo marcado lo enciende en el motor y vuelve a apagarlo",
              p1["ok"] and p1["punch"] and on and p2["ok"] and not p2["punch"] and not eng.punch(), {"on": p1, "off": p2})
    a = lay("rec", "add")
    b = lay("rec", "add")
    page = lay("goto", "cinta")                            # el Grabador, en el Inspector
    row = window.findChild(QObject, "armRow")
    st = lay("rec")
    if st["inputs"]:
        x = lay("rec", "extra", [a["uid"], True])
        armed = sorted(eng.armed_tracks())
        y = lay("rec", "extra", [a["uid"], False])
        rep.check("G3: «Grabar en:» arma otra pista de voz para la misma pasada y la suelta",
                  x["ok"] and a["uid"] in x["extra"] and armed == sorted([a["id"], b["id"]])
                  and y["ok"] and a["uid"] not in y["extra"] and eng.armed_tracks() == [b["id"]],
                  {"armadas": armed, "extra": x["extra"]})
    else:
        rep.add("G3: sin entradas en este dispositivo: armar varias pistas se prueba en tests/test_grabacion_multipista.py", "info")
    if row is not None:
        voz = row.property("voz")
        voz = voz.toVariant() if hasattr(voz, "toVariant") else voz
        rep.check("G3: con dos pistas de voz se ve la fila «Grabar en:»", bool(row.property("visible")),
                  {"pistas de voz": len(voz or []), "página": page})
    folder = Path(tempfile.mkdtemp(prefix="afo_tomas_"))
    sr, files = 48000, []
    for i, f in enumerate((220.0, 330.0)):
        p = folder / f"toma_{i + 1}.wav"
        t = np.arange(int(1.5 * sr)) / sr
        sf.write(str(p), (0.2 * np.sin(2 * np.pi * f * t)).astype(np.float32), sr)
        files.append(str(p))
    tid = b["id"]
    eng.set_track_audio(tid, files[0], 1.0)                 # lo que había en la pista
    host.tracks[tid] = dict(host.tracks.get(tid, {}), source_path=files[0], originalPath=files[0])
    prev = {"source": files[0], "clips": eng.clips(tid)}
    info = dict(eng.set_track_audio(tid, files[1], 1.0))   # lo que deja una grabación (como finish_takes)
    host.tracks[tid].update(source_path=files[1], originalPath=files[1])
    info.update(takes=[files[1]], clips=eng.clips(tid), previous=prev, peaks=[])
    lay("rec", "apply", info)
    st = lay("rec", "takes")
    u = lay("rec", "take", [b["uid"], 0])
    clips = eng.clips(tid)
    rep.check("G3: lo grabado entra como toma de la pista (lo de antes queda como «Toma 1») y se puede volver a ella",
              st["active"]["takes"] == ["Toma 1", "Grabación 1"] and st["active"]["take"] == 1
              and u["ok"] and u["active"]["take"] == 0
              and host.tracks[tid]["originalPath"] == files[0] and any(abs(c["start"] - 1.0) < 0.01 for c in clips),
              {"tras grabar": st["active"], "al elegir": u["active"], "clips": clips})
    lay("rec", "remove", a["uid"])
    lay("rec", "remove", b["uid"])


def _f10_checks(rep, app, host, lay) -> None:
    """F10: fondo opcional (imagen o parallax), apagado de fábrica. Con el fondo puesto el texto de las
    zonas sigue ≥ 4,5:1 en los tres temas, medido con el píxel más oscuro y el más claro de la imagen
    (aquí negro y blanco puros, el peor caso, sin atenuar y con la transparencia de zonas al máximo)."""
    import tempfile
    from pathlib import Path
    from .selftest import _wait

    def blend(a, b, t):                     # a con un t de b (mezcla en sRGB, como el compositor de Qt)
        x, y = [int(a.lstrip("#")[-6:][i:i + 2], 16) for i in (0, 2, 4)], [int(b.lstrip("#")[-6:][i:i + 2], 16) for i in (0, 2, 4)]
        return "#%02x%02x%02x" % tuple(round(p + (q - p) * t) for p, q in zip(x, y))

    s0 = lay("backdrop")
    rep.check("F10: de fábrica no hay fondo (zonas opacas, nada detrás)",
              s0["state"]["mode"] == "none" and not s0["visible"] and s0["alpha"] == 1 and s0["zoneAlpha"] == 0
              and s0["zoneColorA"] == 1, {"estado": s0["state"]["mode"], "alfa": s0["alpha"]})
    img, par = _backdrop_images(Path(tempfile.mkdtemp(prefix="afo_fondo_")))
    lay("view", "arrange")
    lay("backdrop", "image", img)
    s1 = lay("backdrop", "set", {"zoneAlpha": 15, "atten": 0, "reduce": True})
    st = s1["state"]
    copied = all(Path(p).is_file() and Path(p).parent.parent.name == "fondos" for p in st["layers"])
    rep.check("F10: «Imagen» copia la imagen preparada a datos/fondos y se ve detrás (también bajo las pistas)",
              s1["on"] and s1["visible"] and copied and len(st["layers"]) == 1 and st["dark"] == "#000000" and st["light"] == "#ffffff"
              and s1["surfaceVisible"], {"capas": st["layers"], "extremos": [st["dark"], st["light"]], "hueco bajo las pistas": s1["emptyBelow"]})
    worst, alphas = [], {}
    for name in ("Oscuro", "Grafito", "Claro"):
        lay("theme", name)
        s = lay("backdrop")
        a = 1 - s["alpha"]
        alphas[name] = round(100 * a, 1)
        for what, surf, _ in s["surfaces"]:
            for px in (st["dark"], st["light"]):
                eff = blend(surf, blend(px, s["bg"], st["atten"] / 100), a)
                for ink in (s["ink"], s["inkDim"]):
                    worst.append((round(contrast_ratio(ink, eff), 2), name, what, px, ink, eff))
    worst.sort()
    rep.check("F10: con el fondo puesto el texto de las zonas sigue ≥ 4,5:1 en los tres temas (peor caso: negro y blanco puros)",
              worst and worst[0][0] >= 4.5 and all(0 <= v <= 15 for v in alphas.values()),
              {"peor": worst[0], "transparencia de zonas %": alphas})
    lay("theme", "Oscuro")
    # Parallax: 3 capas, la de delante se mueve más con el scroll del Arreglo; quieto con «Reducir movimiento»
    lay("backdrop", "parallax", par)
    lay("backdrop", "set", {"reduce": False, "intensity": 100, "atten": 50, "zoneAlpha": 8})
    p0 = lay("backdrop")
    moved = lay("arrangeScroll", 1.0)
    _wait(app, lambda: False, 0.5, host)
    p1 = lay("backdrop")
    xs0, xs1 = p0["layerX"], p1["layerX"]
    shift = [round(b - a, 1) for a, b in zip(xs0, xs1)]
    lay("arrangeScroll", 0.0)
    _wait(app, lambda: False, 0.4, host)
    lay("backdrop", "set", {"reduce": True})
    lay("arrangeScroll", 1.0)
    _wait(app, lambda: False, 0.4, host)
    p2 = lay("backdrop")
    lay("arrangeScroll", 0.0)
    # capturas con el fondo puesto (Arreglo e Inicio), para mirarlas
    from . import paths
    win = max((w for w in app.topLevelWindows() if w.isVisible()), key=lambda w: w.width() * w.height(), default=None)
    if win is not None:
        lay("backdrop", "set", {"atten": 35, "zoneAlpha": 15})
        for v in ("arrange", "home"):
            lay("view", v)
            _wait(app, lambda: False, 0.6, host)
            win.grabWindow().save(str(paths.logs_dir() / f"selftest_fondo_{v}.png"))
        lay("view", "arrange")
    rep.check("F10: «Parallax» con 3 capas: con el scroll del Arreglo la de delante se mueve más que la de atrás; con «Reducir movimiento» se quedan quietas",
              len(p1["state"]["layers"]) == 3 and moved is True and p1["progress"] > 0.9 and len(shift) == 3
              and shift[0] < 0 and shift[2] < shift[1] < shift[0] and p2["layerX"] == xs0,
              {"desplazamiento px": shift, "quieto": p2["layerX"], "scroll": p1["progress"]})
    lay("backdrop", "none")
    s3 = lay("backdrop")
    rep.check("F10: «Ninguno» quita el fondo y las zonas vuelven a ser opacas",
              s3["state"]["mode"] == "none" and not s3["visible"] and s3["alpha"] == 1, {"estado": s3["state"]["mode"]})


def _f8_checks(rep, app, host, lay) -> None:
    """F8: los scripts de scripts/ salen en el menú Scripts, corren en otro proceso sobre el proyecto y
    sus cambios quedan como un solo paso de Ctrl+Z. (Lo que hace cada script se mide en
    tests/test_scripts.py con proyectos completos.)"""
    from pathlib import Path
    from .selftest import _wait
    lay("menu", "close")
    m = lay("menu", "Scripts")
    lay("menu", "close")
    acts = lay("actions")
    sids = [i for i in acts["ids"] if i.startswith("script.")]
    rep.check("F8: el menú Scripts lista los scripts de la carpeta (y la paleta Ctrl+K los encuentra)",
              m["open"] and m["count"] >= 6 and {"script.normalizar_voces", "script.colorear_por_tipo", "script.exportar_stems",
                                                  "script.marcadores_por_seccion"} <= set(sids) and not acts["missing"],
              {"scripts": sids, "filas": m["count"]})
    lay("view", "arrange")
    before = lay("script")
    started = lay("script", "colorear_por_tipo.py")
    done = started is True and _wait(app, lambda: not lay("script")["busy"], 120, host)
    s = lay("script")
    changed = [t for t, b in zip(s["tracks"], before["tracks"]) if t["color"] != b["color"]]
    rep.check("F8: un script corre en otro proceso y aplica sus cambios (colorear por tipo)",
              done and s["last"] is not None and s["last"]["ok"] and len(changed) >= 2 and s["undo"] == before["undo"] + 1,
              {"cambian": [(t["name"], t["color"]) for t in changed][:8], "resultado": s["last"]})
    u = lay("script", "undo")
    rep.check("F8: un Ctrl+Z deshace todo lo que hizo el script",
              [t["color"] for t in u["tracks"]] == [t["color"] for t in before["tracks"]] and u["undo"] == before["undo"],
              {"colores": [t["color"] for t in u["tracks"]]})
    mutes = [t["mute"] for t in lay("script")["tracks"]]
    started = lay("script", "exportar_stems.py")
    done = started is True and _wait(app, lambda: not lay("script")["busy"], 240, host)
    s = lay("script")
    last = s["last"] or {}
    files = sorted(Path(last.get("exported") or ".").glob("*.wav")) if last.get("exported") else []
    rep.check("F8: «Exportar stems» escribe un WAV por pista y deja el Mute y el Solo como estaban",
              done and last.get("ok") and len(files) >= 2 and all(f.stat().st_size > 1000 for f in files)
              and [t["mute"] for t in s["tracks"]] == mutes,
              {"carpeta": last.get("exported"), "archivos": [f.name for f in files][:10], "resultado": last})


def _f7_checks(rep, app, host, lay) -> None:
    """F7: «Editar › Analizar el proyecto» corre en otro hilo con el audio que suena y deja la pista de
    acordes y las secciones en el Arreglo; se guarda con el proyecto y Ctrl+Z vuelve a lo de antes.
    (Que acierte se mide en tests/test_analisis_proyecto.py con 4 géneros.)"""
    from .selftest import _wait
    lay("view", "arrange")
    before = lay("song")
    started = lay("song", "run")
    done = started is True and _wait(app, lambda: not lay("song")["busy"], 120, host)
    s = lay("song")
    lane = s["lane"]
    rep.check("F7: el análisis del proyecto deja la pista de acordes y las secciones en el Arreglo (otro hilo, barra de estado)",
              done and len(s["chords"]) > 0 and len(s["markers"]) > 0 and lane["visible"] and lane["chords"] == len(s["chords"])
              and lane["markers"] == len(s["markers"]) and lane["flickTop"] == 0 and s["info"] is not None,
              {"acordes": [c[2] for c in s["chords"]][:8], "secciones": [m[2] for m in s["markers"]], "info": s["info"]})
    u = lay("song", "undo")
    rep.check("F7: Ctrl+Z deshace el análisis (acordes, secciones y tonalidad de antes)",
              u["chords"] == before["chords"] and u["markers"] == before["markers"] and u["key"] == before["key"]
              and not u["lane"]["visible"], {"acordes": len(u["chords"]), "tonalidad": u["key"]})


def _f6_checks(rep, app, host, window, call, snap) -> None:
    """F6: un solo mezclador. La mezcla automática es una orden del Mezclador (diálogo con sus ajustes,
    A/B en la barra, marca «IA» en los efectos, Ctrl+Z la deshace) y Master automático un dispositivo del
    master con su A/B en la tira MASTER; el Inspector ya no tiene Asistente IA. Mezcla real, en vivo."""
    from PySide6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG

    from .selftest import _wait

    def lay(a=None):
        v = QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "f6"),
                                     Q_ARG("QVariant", a), Q_ARG("QVariant", None))
        v = v.toVariant() if hasattr(v, "toVariant") else v
        _wait(app, lambda: False, 0.2, host)
        return v
    s0 = lay("mix.auto")
    box = window.findChild(QObject, "mixAutoBox")
    lay("close")
    rep.check("F6: «Mezcla automática…» y «A/B» en la barra del Mezclador abren la orden con sus ajustes; el Inspector sin Asistente IA",
              s0["box"] and s0["view"] == "mixer" and "Mezcla automática…" in s0["bar"] and "A/B: con mezcla auto" in s0["bar"]
              and s0["insp"] == ["pista", "master", "cinta"] and box is not None,
              {"barra": s0["bar"], "inspector": s0["insp"], "diálogo": s0["box"]})
    rep.check("F6: los efectos de la mezcla automática llevan la marca «IA» en las tiras y A/B los puentea y los vuelve a activar",
              s0["autoAll"] > 0 and s0["autoOn"] == s0["autoAll"]
              and (a := lay("mix.abA"))["autoOn"] == 0 and a["ab"] == "A"
              and (b := lay("mix.abB"))["autoOn"] == b["autoAll"] and b["ab"] == "B",
              {"efectos IA": s0["autoAll"], "en A": a["autoOn"], "en B": b["autoOn"]})
    QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "view"),
                             Q_ARG("QVariant", "mixer"), Q_ARG("QVariant", None))
    ma = lay()
    mA = lay("masterA")
    mB = lay("masterB")
    rep.check("F6: Master automático tiene su A/B en la tira MASTER (puentea su cadena y la vuelve a activar)",
              ma["masterAuto"] >= 4 and mA["masterOn"] == 0 and mA["masterAb"] == "A" and mB["masterOn"] == ma["masterAuto"],
              {"efectos": ma["masterAuto"], "A": mA["masterOn"], "B": mB["masterOn"]})
    want = {v["id"]: (round(v["vol"]), v["pan"]) for v in (ma["undo"] or [])}
    u = lay("edit.undo")
    got = {t["id"]: (round(t["vol"]), t["pan"]) for t in snap()["tracks"] if t["id"] in want}
    rep.check("F6: Ctrl+Z en el Mezclador deshace la mezcla automática (efectos IA fuera, faders y paneo de antes)",
              bool(want) and u["autoAll"] == 0 and u["undo"] is None and got == want and u["masterAuto"] == ma["masterAuto"],
              {"efectos IA": u["autoAll"], "tiras": len(want), "iguales": got == want})
    call("mixNow", False)                         # se vuelve a mezclar para lo que sigue
    _wait(app, lambda: snap()["runs"] >= 1 or "Error" in snap()["status"], 240, host)


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


def _hsl_sat(c: str) -> float:
    """Saturación HSL (0–1) de un color #rrggbb."""
    c = c.lstrip("#")[-6:]
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hi, lo = max(r, g, b), min(r, g, b)
    l = (hi + lo) / 2
    return 0.0 if hi == lo else (hi - lo) / (1 - abs(2 * l - 1))


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
    rep.check("Efectos: catálogo del motor (26 módulos y las 2 piezas del FX Lab)", st and st["catalog"] == 28, st and st["catalog"])
    fx("add", "eq")
    st = fx("add", "analyzer")
    rep.check("Efectos: insertar EQ y Analizador en la pista", [e["key"] for e in st["chain"]] == ["eq", "analyzer"],
              [e["key"] for e in st["chain"]])
    rep.check("la cadena está en el motor", [e["key"] for e in host.engine.effects(track_id)] == ["eq", "analyzer"])
    # Navegador (X16): los efectos del motor por categoría (DISENO_DAW §3); doble clic añade a la pista elegida
    def lay(what, a=None):
        v = QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"),
                                     Q_ARG("QVariant", what), Q_ARG("QVariant", a), Q_ARG("QVariant", None))
        return v.toVariant() if hasattr(v, "toVariant") else v
    br = lay("browser")
    secs = dict((s[0], s[1]) for s in br["sections"])
    rep.check("Navegador: efectos del motor por categoría (Dinámica, EQ y filtro, Tono y voz, Espacio, Utilidad, Ritmo, Granular y espectral, Racks y cadenas)",
              list(secs) == ["Dinámica", "EQ y filtro", "Tono y voz", "Espacio", "Utilidad", "Ritmo", "Granular y espectral", "Racks y cadenas"]
              and secs["Racks y cadenas"] == ["fxlab"] and secs["Tono y voz"][:4] == ["tune", "harmonizer", "doubler", "denoise"] and "dyneq" in secs["EQ y filtro"]
              and "glue" in secs["Dinámica"] and "transient" in secs["Dinámica"] and "multitap" in secs["Espacio"]
              and {"shimmer", "textureverb", "infinity"} <= set(secs["Espacio"])
              and secs["Ritmo"] == ["trancegate"] and secs["Granular y espectral"] == ["granular", "spectral"]
              and sum(len(v) for v in secs.values()) == 26, secs)
    lay("browser", "compressor")
    keys = [e["key"] for e in host.engine.effects(track_id)]
    rep.check("Navegador: doble clic en Compresor lo añade a la pista elegida", keys == ["eq", "analyzer", "compressor"], keys)
    fx("pick", "compressor")
    fx("remove")
    fx("pick", "analyzer")
    # Cadena de dispositivos (X15): arrastrar el Analizador al principio y A/B del EQ
    st = fx("drop", 0)
    rep.check("arrastrar un dispositivo al principio lo mueve en el motor",
              [e["key"] for e in st["chain"]] == ["analyzer", "eq"] and [e["key"] for e in host.engine.effects(track_id)] == ["analyzer", "eq"],
              [e["key"] for e in st["chain"]])
    fx("drop", 10000)
    fx("pick", "eq")
    a_val = host.engine.effects(track_id)[0]["values"][0]
    st = fx("ab")                                  # A guardado; ahora se edita B
    p0 = next(c for c in host.effect_catalog() if c["key"] == "eq")["params"][0]
    fx("param", 0, a_val + (p0["max"] - p0["min"]) * (0.25 if a_val < (p0["min"] + p0["max"]) / 2 else -0.25))
    b_val = host.engine.effects(track_id)[0]["values"][0]
    st2 = fx("ab")                                 # vuelve a A
    back_a = host.engine.effects(track_id)[0]["values"][0]
    st3 = fx("ab")                                 # otra vez B
    back_b = host.engine.effects(track_id)[0]["values"][0]
    rep.check("A/B de un dispositivo: alterna dos juegos de valores en el motor",
              st["ab"] == "B" and st2["ab"] == "A" and st3["ab"] == "B" and abs(back_a - a_val) < 1e-4 and abs(back_b - b_val) < 1e-4 and abs(b_val - a_val) > 1,
              {"A": a_val, "B": b_val, "vuelta A": back_a, "vuelta B": back_b, "lados": [st["ab"], st2["ab"], st3["ab"]]})
    fx("pick", "analyzer")
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
    # FX Lab (AF-62): llega con sus tres piezas, una macro se asigna desde su panel y se quita entero
    st = fx("add", "fxlab")
    rep.check("FX Lab: se añade con «Rama B» y «Fin», enlazado",
              [e["key"] for e in st["chain"]] == ["fxlab", "fxlab_b", "fxlab_end"] and st["lab"] is True, [e["key"] for e in st["chain"]])
    gain = fx("add", "gain")["sel"]
    fx("pick", "fxlab")
    st = fx("macro", 1, {"fx": gain, "param": "output", "amount": 0.5})
    lab_id = next(e["id"] for e in st["chain"] if e["key"] == "fxlab")
    rep.check("FX Lab: la macro 1 se asigna a un parámetro desde su panel",
              st["macros"] == 1 and [m["param"] for m in host.engine.effect_macros(lab_id)] == ["output"], st["macros"])
    fx("remove")
    st = fx("pick", "gain")
    rep.check("FX Lab: quitarlo quita sus tres piezas y deja los efectos", [e["key"] for e in st["chain"]] == ["gain"],
              [e["key"] for e in st["chain"]])
    st = fx("remove")


def _native_daw_checks(rep, app, host, window, bridge, track_id) -> None:
    """Estado de la IA local, separador, perfil del equipo, Instrumental Lab y edición de clips en Pistas."""
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

    # Ventana con zonas fijas (docs/DISENO_DAW.md §2): nada se solapa, cada zona se pliega y la vista
    # principal ocupa lo que dejan
    z0 = lay("zones")
    rep.check("zonas fijas: cabecera, navegador, vista principal, inspector, detalle y barra de estado sin solaparse",
              lay("overlaps") == [] and all(z0[k]["visible"] and z0[k]["w"] > 0 and z0[k]["h"] > 0 for k in z0), z0)
    zf = lay("fold", "nav", True)
    zi = lay("fold", "insp", True)
    zd = lay("fold", "detail", True)
    rep.check("plegar navegador, inspector y detalle agranda la vista principal",
              zi["principal"]["w"] > z0["principal"]["w"] + 600 and zd["principal"]["h"] > z0["principal"]["h"] + 100
              and zf["navegador"]["w"] < 40 and lay("overlaps") == [], {"antes": z0["principal"], "después": zd["principal"]})
    for k in ("nav", "insp", "detail"):
        lay("fold", k, False)
    g = lay("goto", "afina")
    rep.check("ir a un módulo abre su zona y su pestaña (Afinador → detalle)",
              g["currentId"] == "afina" and g["zone"] == "Detalle" and g["page"] == "afina" and not g["folded"], g)
    g = lay("goto", "mezcla")
    rep.check("Mezcla es la vista Mezclador (Tab)", g["view"] == "mixer", g)
    lay("view", "arrange")

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
    # Un solo panel de pistas: los clips se editan en el Arreglo (dividir, fundido y deshacer desde la vista)
    lay("view", "arrange")
    uid = "a" + str(track_id)
    c0 = json.loads(bridge.clipList(track_id))["clips"][0]
    sp = lay("arrClip", uid, {"op": "split", "clip": c0["id"], "at": 4.0})
    fd = lay("arrClip", uid, {"op": "fades", "clip": sp["clips"][-1]["id"], "in": 0.5, "out": 0.0}) if len(sp["clips"]) == 2 else {}
    un = lay("arrUndo", uid)
    un = lay("arrUndo", uid)
    eng_clips = json.loads(bridge.clipList(track_id))["clips"]
    tools = [window.findChild(QObject, n) for n in ("arrSplit", "arrCut", "arrToMixer", "aiClipBox", "coverMode", "alignGuide", "alignStrength")]
    rep.check("Arreglo: dividir, fundir y deshacer clips desde la vista (sin pestaña «Clips»)",
              len(sp["clips"]) == 2 and fd.get("ok") and abs(fd["clips"][-1]["fade_in"] - 0.5) < 1e-6
              and len(eng_clips) == 1 and un["redo"] == 2 and None not in tools,
              {"dividido": [round(c["length"], 2) for c in sp["clips"]], "deshecho": len(eng_clips),
               "herramientas": [t is not None for t in tools]})
    # F11: estirar y transponer un clip desde el Arreglo (SoundTouch en el motor) y deshacerlo
    c0 = json.loads(bridge.clipList(track_id))["clips"][0]
    st = lay("arrClip", uid, {"op": "stretch", "clip": c0["id"], "speed": 1.25, "semitones": 2})
    sc = st["clips"][0] if st.get("clips") else {}
    un = lay("arrUndo", uid)
    back = json.loads(bridge.clipList(track_id))["clips"][0]
    rep.check("tempo y tono de un clip: estirar ×1,25 y +2 semitonos, y Ctrl+Z lo devuelve",
              st.get("ok") and abs(sc.get("length", 0) - c0["length"] / 1.25) < 0.02 and sc.get("semitones") == 2
              and abs(back["length"] - c0["length"]) < 0.02 and back["speed"] == 1.0 and back["semitones"] == 0,
              {"estirado": sc, "deshecho": back})
    rep.check("tempo y tonalidad: tono del proyecto en la cabecera y panel del clic derecho",
              window.findChild(QObject, "songKey") is not None and window.findChild(QObject, "tempoKeyBox") is not None)
    _f4_checks(rep, host, lay, call, track_id)
    _f5_checks(rep, host, lay, track_id)
    _f7_checks(rep, app, host, lay)
    _f8_checks(rep, app, host, lay)
    _f10_checks(rep, app, host, lay)
    _g1_checks(rep, host, lay)
    _g2_checks(rep, window, host, lay)
    _g3_checks(rep, window, host, lay)
    _g4_checks(rep, window, host, lay)
    _g5_checks(rep, window, host, lay)
    _g6_checks(rep, window, host, lay)
    _g7_checks(rep, window, host, lay)
    z1 = lay("zones")
    rep.check("tamaño fijo: ninguna zona cambia de tamaño por su contenido", z0 == z1,
              {k: (z0.get(k), z1.get(k)) for k in z1 if z0.get(k) != z1.get(k)})
    # F12: a cualquier tamaño de pantalla las zonas cubren la ventana sin huecos, la cabecera no se
    # sale y la vista principal conserva sitio; en el Mezclador las tiras llenan el alto
    size0, view0, bad, seen = (window.width(), window.height()), window.property("view"), {}, []
    for w, h in ((1280, 720), (1600, 900), (1920, 1080), (2560, 1440)):
        window.resize(w, h)
        for v in ("arrange", "mixer"):
            window.setProperty("view", v)
            _wait(app, lambda: False, 0.35, host)
            f = lay("fit")
            W, H = int(f["w"]), int(f["h"])
            if v == "arrange":
                seen.append(f"{W}x{H}")
            body = H - f["zones"]["menus"]["h"] - f["zones"]["cabecera"]["h"] - f["zones"]["estado"]["h"]
            probs = [n for n, ok in (("huecos", f["covered"] == W * H),
                                     ("cabecera se sale", f["headerRight"] <= W),
                                     ("vista principal estrecha", f["mainW"] >= 0.45 * W),
                                     ("vista principal baja", f["mainH"] >= 0.45 * body),
                                     ("tiras no llenan el alto", v != "mixer" or f["mixGap"] >= 0),
                                     # desde 900 px de alto las tiras caben enteras (más bajo: se desplazan)
                                     ("tiras cortadas", v != "mixer" or H < 900 or f["mixGap"] <= 1)) if not ok]
            if probs:
                bad[f"{W}x{H} {v}"] = (probs, {k: f[k] for k in ("covered", "headerRight", "mainW", "mainH", "mixGap")})
            if v == "mixer" or w == 1280:
                window.grabWindow().save(str(paths.logs_dir() / f"selftest_ventana_{W}x{H}_{v}.png"))
    window.resize(*size0)
    window.setProperty("view", view0)
    _wait(app, lambda: False, 0.35, host)
    # la ventana no pasa del tamaño de la pantalla: se informa de los tamaños que se midieron de verdad
    rep.check("distribución sin huecos de 1280×720 hasta el tamaño de la pantalla (Arreglo y Mezclador)",
              not bad, bad or {"medidos": seen})
    # F13: la ayuda va en un «?» (zona y cada efecto), no en párrafos fijos
    helps = [o for o in window.findChildren(QObject) if o.objectName().startswith("zoneHelp_")]
    shown = [o for o in helps if o.property("visible")]
    opened = False
    if shown:
        QMetaObject.invokeMethod(shown[0], "show")
        _wait(app, lambda: False, 0.2, host)
        opened = bool(shown[0].property("opened")) and len(shown[0].property("text") or "") > 40
        QMetaObject.invokeMethod(shown[0], "hide")
    # F2: en el Inspector y el Navegador cada sección lleva su «?»; el detalle, el de su pestaña
    sx = lay("sections", "fxlist")
    side_help = [r["id"] for r in sx["nav"]["rows"] + sx["insp"]["rows"] if r["help"]]
    rep.check("ayuda «?»: cada zona explica su pestaña o sección y se abre al pulsar",
              len(shown) >= 1 and opened and sx["nav"]["opened"] and len(side_help) >= 6,
              {"detalle": [o.objectName() for o in shown], "secciones": side_help, "abre": [opened, sx["nav"]["opened"]]})
    # F2: Inspector a la izquierda, Navegador a la derecha y, en los lados, secciones plegables en vez
    # de pestañas: una fila por página, la abierta debajo de su título y las demás apiladas abajo
    zz = lay("zones")
    pages = lay("pages")
    rows = sx["nav"]["rows"] + sx["insp"]["rows"]
    stacked = all(r["y"] + r["h"] <= sx[z]["pageY"] or r["y"] >= sx[z]["pageY"] + sx[z]["pageH"]
                  for z in ("nav", "insp") for r in sx[z]["rows"])
    rep.check("Inspector a la izquierda y Navegador a la derecha, con secciones plegables (sin pestañas)",
              zz["inspector"]["x"] < zz["principal"]["x"] < zz["navegador"]["x"] and stacked
              and {r["id"] for r in rows} == set(pages) - {"piano", "inst", "drums", "fx", "tono", "afina"},
              {"x": {k: zz[k]["x"] for k in ("inspector", "principal", "navegador")},
               "secciones": [r["id"] for r in rows], "sin solaparse": stacked})
    tracks = call("mixerSnapshot")["tracks"]
    i_drum = next((i for i, t in enumerate(tracks) if t["type"] == "drum"), -1)
    i_tone = next((i for i, t in enumerate(tracks) if t["id"] == track_id), -1)
    lay("goto", "drums")
    s_tone = lay("select", i_tone)
    lay("goto", "piano")
    s_drum = lay("select", i_drum)
    rep.check("la selección manda: elegir una pista abre su editor en el detalle y su cadena en Efectos",
              s_tone["detail"] == "fx" and s_tone["rack"] == track_id and s_drum["detail"] == "drums",
              {"tono": s_tone, "batería": s_drum})
    # F3: el editor de abajo no tiene pestañas fijas: sus modos son los de lo elegido
    by_type = {}
    for t in tracks:
        by_type.setdefault(t["type"], t["id"])
    want = {"inst": ["piano", "inst", "fx"], "drum": ["drums", "fx"], "audio": ["fx", "tono", "afina"]}
    got = {k: lay("modes", by_type[k]) for k in want if k in by_type}
    got["master"] = lay("modes", 0)
    lay("goto", "piano")
    after = lay("modes", by_type.get("audio", track_id))
    rep.check("editor de abajo: sus modos siguen a lo elegido (instrumento, batería, audio con Tono, master)",
              len(got) == 4 and all(got[k]["modes"] == want[k] for k in want) and got["master"]["modes"] == ["fx"]
              and after["current"] == "fx" and after["pitchTrack"] == by_type.get("audio", track_id)
              and all(g["caption"].startswith("EDITOR · ") for g in got.values()),
              {k: (g["modes"], g["caption"]) for k, g in got.items()} | {"piano → audio": after["current"]})
    lay("modes", track_id)

    # Órdenes (F1, FLUJO_PROFESIONAL §4.2): un registro → barra de menús, clic derecho y paleta Ctrl+K
    ac = lay("actions")
    rep.check("órdenes: cada orden del registro hace algo en la interfaz y no hay órdenes fuera del registro",
              ac["ids"] and not ac["missing"] and not ac["extra"], {"sin hacer": ac["missing"], "fuera": ac["extra"]})
    rep.check("barra de menús Archivo · Editar · Transporte · Pista · Clip · Mezcla · Scripts · Ver",
              ac["menus"] == ["Archivo", "Editar", "Transporte", "Pista", "Clip", "Mezcla", "Scripts", "Ver"], ac["menus"])
    rep.check("clic derecho: la IA vive en el clip y en la pista (Rehacer, Versión, Alinear, Tono, Separar)",
              {"clip.repaint", "clip.cover", "clip.align", "clip.pitch", "clip.stems"} <= set(ac["clip"])
              and {"track.stems", "track.generate", "track.effects"} <= set(ac["track"]), {"clip": ac["clip"], "pista": ac["track"]})
    m = lay("menu", "Editar")
    pal = lay("menu", "palette", "separar")
    lay("menu", "close")
    s0 = lay("run", "edit.snap")
    s1 = lay("run", "edit.snap")
    rep.check("abrir un menú, buscar en la paleta y ejecutar una orden",
              m["open"] and m["count"] >= 8 and pal["open"] and {"clip.stems", "track.stems"} <= set(pal["hits"])
              and s0["ok"] and s1["ok"] and s0["checked"] != s1["checked"], {"menú": m, "paleta": pal, "rejilla": [s0, s1]})
    cx = lay("menu", "ctx", "clip")
    tx = lay("menu", "ctx", "track")
    lay("menu", "close")
    rep.check("menús de clic derecho con las órdenes del clip y de la pista",
              cx["open"] and cx["count"] == len(ac["clip"]) and tx["open"] and tx["count"] == len(ac["track"]), {"clip": cx, "pista": tx})

    # Temas: familia Oscuro / Grafito / Claro (FLUJO_PROFESIONAL §6): solo cambia la luz
    looks = {}
    for name in ("Oscuro", "Grafito", "Claro"):
        t = lay("theme", name)
        looks[name] = t
        low = [(what, fg, bg, round(r, 2)) for what, fg, bg in lay("contrast") if (r := contrast_ratio(fg, bg)) < 4.5]
        rep.check(f"contraste del tema {name}: todo el texto ≥ 4,5:1 (WCAG AA)", t["ok"] and not low, low)
    o, g, c = looks["Oscuro"], looks["Grafito"], looks["Claro"]
    same = {k for k in o["colors"] if k != "accent" and o["colors"][k] == g["colors"].get(k) == c["colors"].get(k)}
    rep.check("una familia: los tres temas tienen la misma forma y los mismos colores de zona",
              o["themes"][:3] == ["Oscuro", "Grafito", "Claro"] and o["frame"] == g["frame"] == c["frame"] == 0
              and o["knob"] == g["knob"] == c["knob"] == "arc" and same == set(o["colors"]) - {"accent"},
              {"lista": o["themes"], "distintos": sorted(set(o["colors"]) - same)})
    lay("theme", "Oscuro")


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
    tk = next((x for x in tracks() if drum and x["id"] == drum["id"]), {})
    rep.check("F5: las variantes de cada familia son las tomas de su pista borrador (la elegida suena)",
              [k["name"] for k in tk.get("takes") or []] == ["V1", "V2"] and tk.get("take") == 1,
              {"tomas": [k["name"] for k in tk.get("takes") or []], "suena": tk.get("take")})
    # Vista Crear IA (X18): discos dibujados de cada variante y arrastrar uno a una pista nueva
    from PySide6.QtQuick import QQuickItem
    QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "view"),
                             Q_ARG("QVariant", "lab"), Q_ARG("QVariant", None))
    from .selftest import _wait
    _wait(app, lambda: False, 0.4, host)
    lv = window.findChild(QQuickItem, "labView")
    def walk(it):                                  # los delegados de un Repeater solo son hijos visuales
        for c in it.childItems():
            yield c
            yield from walk(c)
    items = list(walk(lv)) if lv else []
    discs = [d for d in items if d.objectName() == "labDisc" and d.isVisible()]
    rows = [d for d in items if d.objectName() == "labFamily" and d.isVisible()]
    rep.check("Crear IA: una fila por familia y un disco por variante", lv is not None and lv.isVisible() and len(rows) == 2 and len(discs) == 3,
              {"filas": len(rows), "discos": len(discs)})
    shot = paths.logs_dir() / "selftest_lab.png"
    window.grabWindow().save(str(shot))
    rep.add("captura de Crear IA", "INFO", str(shot))
    bajo = next(f for f in bridge.lab.public()["families"] if f["name"] == "Bajo")["variants"][0]
    n0 = len(tracks())
    v = QMetaObject.invokeMethod(lv, "dropNew", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "Bajo"), Q_ARG("QVariant", bajo))
    added = tracks()[n0:] if len(tracks()) > n0 else []
    rep.check("Crear IA: soltar un disco en «Pista nueva» crea una pista con ese audio",
              len(added) == 1 and added[0]["type"] == "audio" and added[0]["name"] == "Bajo " + bajo["label"],
              [x["name"] for x in added])
    QMetaObject.invokeMethod(lv, "edit", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "Batería"))
    app.processEvents()
    drum_id = int(lab.property("drafts").toVariant()["Batería"]) if hasattr(lab.property("drafts"), "toVariant") else int(lab.property("drafts")["Batería"])
    rep.check("Crear IA: «Editar» elige la pista borrador y abre su cadena de efectos y el Inspector (X19)",
              window.property("rackTrack") == drum_id and window.findChild(QQuickItem, "inspector").property("tid") == drum_id,
              {"rack": window.property("rackTrack"), "borrador": drum_id})
    QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "view"),
                             Q_ARG("QVariant", "arrange"), Q_ARG("QVariant", None))
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
    rep.check("Proyecto: ajustes de la mezcla automática y del Afinador recuperados",
              ai(after) == ai(before) and ai(after)[1] == 35, {"antes": ai(before), "después": ai(after)})
    call("setTuneStrength", 0)
    notes = lambda snap: [(t["name"], sorted(t["roll"]), sorted(t["pat"]), t["cfg"]) for t in snap["tracks"] if t["type"] in ("inst", "drum")]  # noqa: E731
    rep.check("Proyecto: notas, patrones y ajustes de los sintetizadores recuperados",
              notes(after) == notes(before) and any(n[1] or n[2] for n in notes(after)), len(notes(after)))
    path.unlink(missing_ok=True)


def _native_home_checks(rep, app, host, window, bridge, startup: bool = False) -> None:
    """Inicio y Biblioteca (X10, X11): sale al arrancar; artista → álbum → canción, abrirla, guardar en su
    carpeta y verla con su .afo al volver a Inicio. Lo que crea se quita al final."""
    import shutil

    from PySide6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG

    from .selftest import _wait

    def call(fn, *args):
        v = QMetaObject.invokeMethod(window, fn, Q_RETURN_ARG("QVariant"), *[Q_ARG("QVariant", a) for a in args])
        return v.toVariant() if hasattr(v, "toVariant") else v

    if startup:
        st = call("homeCommand", "noop", None, None)
        rep.check("Inicio sale al arrancar sin proyecto abierto", st["view"] == "home" and st["visible"], st["view"])
        call("layoutCommand", "view", "arrange", None)
        return
    artist = "Autoprueba " + time.strftime("%H%M%S")
    a = call("homeCommand", "create", "artist", artist)
    r = call("homeCommand", "create", "release", "Primer Álbum")
    s = call("homeCommand", "create", "song", "Canción Uno")
    st = call("homeCommand", "open", None, None)
    _wait(app, lambda: False, 0.2, host)
    rep.check("Inicio: crear artista → álbum → canción y abrirla",
              bool(a and r and s) and st["view"] == "arrange" and st["songTarget"].endswith("Canción Uno.afo")
              and st["title"] == f"{artist} · Primer Álbum · Canción Uno", st)
    saved = call("projectCommand", "save", "")
    st = call("homeCommand", "show", None, None)
    _wait(app, lambda: False, 0.3, host)
    song = st.get("song") or {}
    rep.check("guardar la canción la deja en su carpeta y, al volver a Inicio, se ve con su .afo y en Recientes",
              bool(saved) and song.get("hasAfo") and Path(song.get("afo", "")).is_file() and song.get("afo") in st["recent"],
              {"guardado": saved, "canción": song, "recientes": st["recent"][:2]})
    shot = paths.logs_dir() / "selftest_inicio.png"
    window.grabWindow().save(str(shot))
    rep.add("captura del Inicio", "INFO", str(shot))
    gone = json.loads(bridge.libraryRemove(a)) if a else {}
    if gone.get("ok"):
        shutil.rmtree(gone["trash"], ignore_errors=True)     # lo creó la autoprueba: no se deja en la papelera
    call("projectCommand", "loose", "")
    call("layoutCommand", "view", "arrange", None)


def _native_inspector_checks(rep, app, host, window, track_id) -> None:
    """Inspector (X17): la página Pista sigue a la pista elegida y su volumen llega al motor. Sin
    Asistente IA (F6): Master automático es un dispositivo del master en Efectos."""
    from PySide6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG
    from PySide6.QtQuick import QQuickItem

    from .selftest import _wait

    def call(fn, *args):
        v = QMetaObject.invokeMethod(window, fn, Q_RETURN_ARG("QVariant"), *[Q_ARG("QVariant", a) for a in args])
        return v.toVariant() if hasattr(v, "toVariant") else v

    tracks = window.property("tracks").toVariant() if hasattr(window.property("tracks"), "toVariant") else window.property("tracks")
    idx = next(i for i, t in enumerate(tracks) if t["id"] == track_id)
    window.setProperty("selected", idx)
    g = call("layoutCommand", "goto", "pista", None)
    _wait(app, lambda: False, 0.2, host)
    insp = window.findChild(QQuickItem, "inspector")
    rep.check("Inspector › Pista muestra la pista elegida",
              insp is not None and insp.property("tid") == track_id and insp.isVisible() and g["page"] == "pista",
              {"tid": insp.property("tid") if insp else None, "page": g["page"]})
    uid = tracks[idx]["uid"]
    QMetaObject.invokeMethod(window, "setTrackMixUid", Q_ARG("QVariant", uid), Q_ARG("QVariant", 40), Q_ARG("QVariant", 50))
    _wait(app, lambda: False, 0.1, host)
    vol = insp.findChild(QQuickItem, "inspVol")
    rep.check("el fader del Inspector refleja el volumen de la pista", vol is not None and round(vol.property("value")) == 40,
              vol.property("value") if vol else None)
    QMetaObject.invokeMethod(window, "setTrackMixUid", Q_ARG("QVariant", uid), Q_ARG("QVariant", 70), Q_ARG("QVariant", 50))
    g = call("layoutCommand", "goto", "mastia", None)
    rep.check("Master automático abre el rack del master en Efectos (F6: sin Asistente IA en el Inspector)",
              g["page"] == "fx" and g["zone"] == "Detalle", g)


def run_native_selftest(app, host, report_path: str | None, screenshot_path: str | None, rep=None) -> int:
    """Parte de `AllForOne --selftest`: la interfaz QML con el motor real, comprobada de verdad."""
    from PySide6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG
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
    # La distribución fija se prueba aquí; la vista Arreglo, tras la mezcla
    _wait(app, lambda: False, 0.2, host)
    pv = QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "pages"),
                                  Q_ARG("QVariant", None), Q_ARG("QVariant", None))
    ids = sorted((pv.toVariant() if hasattr(pv, "toVariant") else pv) or [])
    rep.check("cada módulo tiene su sitio: páginas en las zonas y la consola como vista Mezclador",
              ids == sorted(["add", "fxlist", "audios", "recent", "pista", "master", "cinta", "piano",
                             "inst", "drums", "fx", "tono", "afina"]), ids)
    rep.check("motor conectado desde QML", bool(prop("engineOk")))
    _native_home_checks(rep, app, host, window, bridge, startup=True)   # lo demás de Inicio, al final: deja el proyecto vacío

    _native_sequencer_checks(rep, app, host, window, prop)

    tone = json.loads(bridge.addTestTone())
    QMetaObject.invokeMethod(window, "addTrack", Q_ARG("QVariant", tone["track"]), Q_ARG("QVariant", False))
    tracks = prop("tracks") or []
    rep.check("Pistas muestra la pista del motor con su forma de onda",
              bool(tracks) and tracks[-1]["type"] == "audio" and len(tracks[-1]["peaks"]) == 600, [t["name"] for t in tracks])

    _native_fx_checks(rep, app, host, window, bridge, tone["track"]["id"])
    _native_daw_checks(rep, app, host, window, bridge, tone["track"]["id"])
    _native_inspector_checks(rep, app, host, window, tone["track"]["id"])
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

    # F2: captura de la ventana en cada tema de la familia
    for name in ("Oscuro", "Grafito", "Claro"):
        QMetaObject.invokeMethod(window, "setTheme", Q_ARG("QVariant", name), Q_ARG("QVariant", True))
        _wait(app, lambda: False, 0.3, host)
        window.grabWindow().save(str(paths.logs_dir() / f"selftest_tema_{name}.png"))
    rep.add("capturas en los tres temas (Oscuro, Grafito, Claro)", "INFO", str(paths.logs_dir()))
    QMetaObject.invokeMethod(window, "setDark", Q_ARG("QVariant", True))
    QMetaObject.invokeMethod(window, "saveLayout")
    saved = json.loads((paths.user_data_dir() / LAYOUT_FILE).read_text(encoding="utf-8"))
    rep.check("diseño y tema guardados en la carpeta de datos",
              saved.get("theme") == "Oscuro" and saved.get("v") == 7 and set(saved.get("fold", {})) == {"nav", "insp", "detail"}, saved)
    QMetaObject.invokeMethod(window, "setDark", Q_ARG("QVariant", False))

    # F13: cada efecto de la cadena lleva su «?» con lo que hace (resumen del catálogo del motor)
    fv = QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "fxhelp"),
                                  Q_ARG("QVariant", None), Q_ARG("QVariant", None))
    fxh = (fv.toVariant() if hasattr(fv, "toVariant") else fv) or []
    rep.check("ayuda «?» en cada efecto de la cadena con su explicación",
              bool(fxh) and all(len(h[1] or "") > 20 for h in fxh), {h[0]: (h[1] or "")[:60] for h in fxh})
    shot = Path(screenshot_path) if screenshot_path else paths.logs_dir() / "selftest_nativo.png"
    _wait(app, lambda: False, 0.5, host)
    window.grabWindow().save(str(shot))
    rep.add("captura de la interfaz nativa", "info", str(shot))
    _native_home_checks(rep, app, host, window, bridge)
    window.close()
    return _finish(rep, report_path)


def _native_dual_checks(rep, app, host, window, prop) -> None:
    """Doble flujo: el Arreglo en una ventana aparte y el Mezclador en la principal, mismo proyecto."""
    from .selftest import _wait
    before = prop("view")
    window.setProperty("dualWindow", True)
    _wait(app, lambda: False, 1.0, host)
    flow = prop("flowWindow")
    shown = bool(flow is not None and flow.isVisible())
    rep.check("Doble flujo: Arreglo en su ventana y Mezclador en la principal",
              shown and prop("view") == "mixer", {"ventana": shown, "vista": prop("view")})
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
    rep.check("la mezcla automática solo mezcla: el master queda sin tocar", st["master"] is None and not st["masterChain"], st["masterChain"])
    call("mixerCommand", "master", 3)             # Efectos master → MASTERIZAR (Plataformas)
    _wait(app, lambda: snap()["master"] is not None or "Error" in snap()["status"], 240, host)
    st = snap()
    rep.check("masterizar automáticamente deja una versión AUTO en Rebobinado",
              len(st["versions"]) == 1 and st["versions"][0]["kind"] == "auto" and st["versionSel"] == 0
              and st["versions"][0]["fx"] == len(st["masterChain"]) >= 4, st["versions"])
    check_mix_run(rep, bridge, st, t0)
    _f6_checks(rep, app, host, window, call, snap)
    # Vista Arreglo: lo que hizo la mezcla se ve (inserts por pista y curvas de automatización del motor)
    lv = QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "view"),
                                  Q_ARG("QVariant", "arrange"), Q_ARG("QVariant", None))
    lv = lv.toVariant() if hasattr(lv, "toVariant") else lv
    _wait(app, lambda: False, 0.3, host)
    lanes = json.loads(bridge.dawLanes(json.dumps([i["trackId"] for i in st["items"]] + [0])))
    n_auto = sum(len(v["lanes"]) for v in lanes.get("tracks", {}).values())
    n_ins = sum(len(v["inserts"]) for v in lanes.get("tracks", {}).values())
    rep.check("vista Arreglo: se ven los inserts y las curvas de automatización de la mezcla; el Mezclador, los mismos inserts",
              lv["visible"] and not lv["modules"] and lv["inserts"] == n_ins > 0 and lv["lanes"] == n_auto > 0
              and lv["mixInserts"] == n_ins
              and all(len(l["points"]) >= 2 and l["max"] > l["min"] for v in lanes["tracks"].values() for l in v["lanes"]),
              {"inserts": lv["inserts"], "mezclador": lv["mixInserts"], "curvas": lv["lanes"], "filas": lv["rows"]})
    # Bus Aux desde el Mezclador: un envío de la voz principal llega al bus y su tira lo muestra
    voz = next(i["trackId"] for i in st["items"] if i["name"] == "Voz_Principal")
    ax = QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "aux"),
                                  Q_ARG("QVariant", ["Reverb", voz, -12.0]), Q_ARG("QVariant", None))
    ax = ax.toVariant() if hasattr(ax, "toVariant") else ax
    _wait(app, lambda: False, 0.3, host)
    sends = json.loads(bridge.sendList(voz)).get("sends", [])
    lv2 = QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "view"),
                                   Q_ARG("QVariant", None), Q_ARG("QVariant", None))
    lv2 = lv2.toVariant() if hasattr(lv2, "toVariant") else lv2
    rep.check("bus Aux: «+ AUX» del Mezclador crea el bus y el envío de la voz llega al motor y a su tira",
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
    window.setProperty("view", "mixer")
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

    # Fase 2: Afinador (cable a la tira de la voz), confirmar tonalidad, Master automático y Antes / Después
    call("setTuneStrength", 60)
    _wait(app, lambda: False, 0.3, host)
    tuned = snap()["tuned"]
    rep.check("el Afinador marca la voz que afina", len(tuned) >= 1, tuned)
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
    tb = next((i for i in _items(window.contentItem()) if i.property("histLen") == 240 and i.objectName() != "fxTune"), None)
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
    # Editor de tono (AF-64), modo «Tono» del editor de abajo (F3): analizar la voz, subir una nota,
    # aplicar y volver a la toma
    tb = next((i for i in _items(window.contentItem()) if i.objectName() == "pitchEditor"), None)
    pe_ok, pe_info = False, {"módulo": tb is not None}
    if tb is not None:
        tb.setProperty("trackId", voz)
        seq = tb.property("seq")
        ctrls = [window.findChild(QObject, n) for n in ("pitchAnalyze", "pitchApply", "pitchRoll", "pitchFlatten", "pitchToScale")]
        QMetaObject.invokeMethod(seq, "pitchAnalyze", Q_ARG("QVariant", voz))
        here = _wait(app, lambda: bool(tb.property("peHere")), 30, host)
        pe = tb.property("pe") or {}
        pe = pe.toVariant() if hasattr(pe, "toVariant") else pe
        nn = len(pe.get("notes", [])) if here else 0
        src0 = pe.get("source") if here else None          # el archivo que suena (convertido si hizo falta)
        edited, back = None, None
        if nn:
            tb.setProperty("sel", [0])
            QMetaObject.invokeMethod(tb, "peNudge", Q_ARG("QVariant", 1))
            QMetaObject.invokeMethod(seq, "pitchApply")
            _wait(app, lambda: "afinadas" in str(host.tracks.get(voz, {}).get("originalPath")) and not seq.property("pitchBusy"), 30, host)
            edited = host.tracks.get(voz, {}).get("originalPath")
            QMetaObject.invokeMethod(tb, "peReset")
            QMetaObject.invokeMethod(seq, "pitchApply")
            _wait(app, lambda: host.tracks.get(voz, {}).get("originalPath") == src0 and not seq.property("pitchBusy"), 30, host)
            back = host.tracks.get(voz, {}).get("originalPath")
        pe_ok = None not in ctrls and nn > 0 and edited not in (None, src0) and "afinadas" in str(edited) and back == src0
        pe_info = {"controles": [c is not None for c in ctrls], "notas": nn, "copia": edited and Path(edited).name,
                   "vuelve": back == src0}
    rep.check("Editor de tono: analiza la voz, aplica una nota subida como copia y vuelve a la toma", pe_ok, pe_info)
    # Panel de detalle de efectos (X15): elegir la voz y en su cadena el AF-60 → sale el editor del Afinador
    def fxc(what, a=None, b=None):
        v = QMetaObject.invokeMethod(window, "fxCommand", Q_RETURN_ARG("QVariant"),
                                     Q_ARG("QVariant", what), Q_ARG("QVariant", a), Q_ARG("QVariant", b))
        return v.toVariant() if hasattr(v, "toVariant") else v
    fxc("target", voz)
    fxc("add", "tune")
    st = fxc("pick", "tune")
    _wait(app, lambda: False, 0.2, host)
    st = fxc("noop")
    ed = next((i for i in _items(window.contentItem()) if i.objectName() == "fxTune"), None)
    rep.check("Efectos: elegir el AF-60 de la voz muestra el editor del Afinador",
              bool(st["tuneEditor"]) and ed is not None and ed.property("trackId") == voz and ed.isVisible(),
              {"editor": st["tuneEditor"], "pista": ed and ed.property("trackId"), "voz": voz})
    fxc("remove")
    call("mixNow", True)                          # REMEZCLAR con afinación al 60 %
    done = _wait(app, lambda: (snap()["runs"] >= 2 and not snap()["mastering"]) or "Error" in snap()["status"], 240, host)
    st = snap()
    tchain = [e["key"] for e in json.loads(bridge.fxList(voz)).get("chain", [])]
    rep.check("REMEZCLAR con afinación: el afinador nativo AF-60 queda el primero en la cadena de la voz",
              done and st["runs"] >= 2 and bool(st.get("lastTuned")) and tchain[:1] == ["tune"], [st["status"], tchain])
    call("setTuneStrength", 0)
    call("mixerCommand", "unmaster", None)
    rep.check("quitar el master automático", _wait(app, lambda: not snap()["masterChain"], 5, host), snap()["masterChain"])


def _native_sequencer_checks(rep, app, host, window, prop) -> None:
    """Fase 3: Instrumento y Batería con el sintetizador del motor; + IA lleva al generador."""
    import tempfile

    import numpy as np
    import soundfile as sf
    from PySide6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG

    from .engine_host import FIRST_DRUM_NOTE, afo_audio, step_pattern, synth_settings
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
    # X6: con un VST3 elegido, las perillas del sintetizador interno se ocultan y sale la nota. Se usa
    # un id que no existe (el motor lo rechaza y no carga nada): se mira solo el cambio de la interfaz.
    from PySide6.QtCore import QObject
    QMetaObject.invokeMethod(window, "layoutCommand", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", "goto"),
                             Q_ARG("QVariant", "inst"), Q_ARG("QVariant", None))          # la página a la vista
    _wait(app, lambda: False, 0.1, host)
    note, knobs = window.findChild(QObject, "instVstNote"), window.findChild(QObject, "instKnobs")
    if note is None or knobs is None:
        rep.check("X6: con un VST3, nota en lugar de las perillas del sintetizador interno", False, "falta la página Instrumentos")
    else:
        before = (bool(note.property("visible")), bool(knobs.property("visible")))
        cmd("cfg", "plugin", "afo-autoprueba-no-existe")
        _wait(app, lambda: False, 0.1, host)
        withvst = (bool(note.property("visible")), bool(knobs.property("visible")))
        cmd("cfg", "plugin", "")
        _wait(app, lambda: False, 0.1, host)
        after = (bool(note.property("visible")), bool(knobs.property("visible")))
        rep.check("X6: con un VST3, nota en lugar de las perillas del sintetizador interno",
                  before == (False, True) and withvst == (True, False) and after == (False, True),
                  f"sin VST3 {before} · con VST3 {withvst} · de vuelta {after} (nota, perillas)")

        # 808 Lab: Glide, Saturación y Golpe solo con el preset «Bajo 808», y el motor lo toca
        k808 = [window.findChild(QObject, n) for n in ("knob808Glide", "knob808Drive", "knob808Punch")]
        if None in k808:
            rep.check("808 Lab: perillas propias con el preset «Bajo 808»", False, "faltan las perillas del 808")
        else:
            vis = lambda: tuple(bool(k.property("visible")) for k in k808)
            off = vis()
            cmd("cfg", "v", 8)
            _wait(app, lambda: False, 0.1, host)
            on = vis()
            heard = host.audition({"type": "inst", "cfg": {"v": 8, "glide": 30, "drive": 40, "punch": 50}, "note": 33,
                                   "seconds": 0.4})
            cmd("cfg", "v", 0)
            _wait(app, lambda: False, 0.1, host)
            rep.check("808 Lab: perillas propias con el preset «Bajo 808»",
                      off == (False,) * 3 and on == (True,) * 3 and vis() == (False,) * 3 and bool(heard),
                      f"otro preset {off} · 808 {on} · se escucha {heard}")

        # Sinte analógico: sus 6 perillas solo con el preset «Sinte analógico», y el motor lo toca
        an = window.findChild(QObject, "instAnalog")
        if an is None:
            rep.check("Sinte analógico: perillas propias con su preset", False, "falta el bloque del sinte analógico")
        else:
            off = bool(an.property("visible"))
            cmd("cfg", "v", 9)
            _wait(app, lambda: False, 0.1, host)
            on = bool(an.property("visible"))
            heard = host.audition({"type": "inst", "cfg": {"v": 9, "anCut": 60, "anRes": 40}, "note": 57, "seconds": 0.4})
            peak_an = render_peak()
            host.engine.preview_stop()
            cmd("cfg", "v", 0)
            _wait(app, lambda: False, 0.1, host)
            rep.check("Sinte analógico: perillas propias con su preset",
                      not off and on and not bool(an.property("visible")) and bool(heard) and peak_an > -30,
                      f"otro preset {off} · analógico {on} · se escucha {heard} · render {peak_an:.1f} dBFS")

        # Sinte de tablas: tabla y perillas solo con su preset, y el motor lo toca
        wv = window.findChild(QObject, "instWave")
        if wv is None:
            rep.check("Sinte de tablas: tabla y perillas con su preset", False, "falta el bloque del sinte de tablas")
        else:
            off = bool(wv.property("visible"))
            cmd("cfg", "v", 10)
            _wait(app, lambda: False, 0.1, host)
            on = bool(wv.property("visible"))
            heard = host.audition({"type": "inst", "cfg": {"v": 10, "wtTab": 1, "wtPos": 60}, "note": 57, "seconds": 0.4})
            peak_wt = render_peak()
            host.engine.preview_stop()
            cmd("cfg", "v", 0)
            _wait(app, lambda: False, 0.1, host)
            rep.check("Sinte de tablas: tabla y perillas con su preset",
                      not off and on and not bool(wv.property("visible")) and bool(heard) and peak_wt > -30,
                      f"otro preset {off} · tablas {on} · se escucha {heard} · render {peak_wt:.1f} dBFS")

        # Sampler: sin sonido lo dice y no suena; con un sonido cargado, la pista lo toca afinado
        sm = window.findChild(QObject, "instSampler")
        if sm is None:
            rep.check("Sampler: carga un sonido y lo toca en cada nota", False, "falta el bloque del sampler")
        else:
            wav = Path(tempfile.mkdtemp(prefix="afo_smp_")) / "nota.wav"
            tt = np.arange(int(0.5 * 48000)) / 48000
            sf.write(str(wav), (0.5 * np.sin(2 * np.pi * 440 * tt) * np.exp(-tt * 3)).astype(np.float32), 48000)
            cmd("cfg", "v", 11)
            _wait(app, lambda: False, 0.1, host)
            on = bool(sm.property("visible"))
            name = window.findChild(QObject, "smpName")
            empty_text = str(name.property("text")) if name is not None else ""
            cmd("cfg", "smpFile", str(wav))
            _wait(app, lambda: False, 0.1, host)
            loaded_text = str(name.property("text")) if name is not None else ""
            inst_id = next((tid for tid, f in (getattr(host, "_inst_samples", None) or {}).items() if f == str(wav)), -1)
            heard = host.audition({"type": "inst", "id": inst_id, "cfg": {"v": 11, "smpFile": str(wav), "smRoot": 69},
                                   "note": 57, "seconds": 0.4})
            host.engine.preview_stop()
            cmd("cfg", "smpFile", "")
            cmd("cfg", "v", 0)
            _wait(app, lambda: False, 0.1, host)
            rep.check("Sampler: carga un sonido y lo toca en cada nota",
                      on and "Sin sonido" in empty_text and loaded_text == "nota.wav" and inst_id >= 0 and bool(heard)
                      and not bool(sm.property("visible")),
                      f"visible {on} · vacío «{empty_text[:30]}» · cargado «{loaded_text}» · pista {inst_id} · se escucha {heard}")

        # Step Sequencer: un clic en un paso con «probabilidad» lo pasa a 75 % y llega así al motor
        steps_ui = [window.findChild(QObject, n) for n in ("stepMode", "padLen")]
        def drum_now():
            v = QMetaObject.invokeMethod(window, "drumSnapshot", Q_RETURN_ARG("QVariant"))
            return v.toVariant() if hasattr(v, "toVariant") else v
        drum0 = drum_now()
        if None in steps_ui or drum0 is None or not drum0["pat"].get("0-0"):
            rep.check("Step Sequencer: fuerza, probabilidad, repeticiones y largo por pad", False,
                      f"controles {[c is not None for c in steps_ui]} · pista de batería con bombo en el paso 1: {drum0 is not None}")
        else:
            cmd("stepcycle", 0, [0, 1])
            _wait(app, lambda: False, 0.1, host)
            d1 = drum_now()
            got = list(d1["pat"].get("0-0") or [])
            sp = step_pattern(d1)
            expanded = afo_audio.expand_steps(**{k: v for k, v in sp.items()}) if afo_audio else []
            kicks = sum(1 for n in expanded if n[2] == FIRST_DRUM_NOTE and n[0] % 4 == 0)
            for _ in range(3):                                   # 75 → 50 → 25 → 100: como estaba
                cmd("stepcycle", 0, [0, 1])
            _wait(app, lambda: False, 0.1, host)
            back = drum_now()["pat"].get("0-0")
            rep.check("Step Sequencer: fuerza, probabilidad, repeticiones y largo por pad",
                      got == [100, 75, 1] and (0, 0, 100, 75, 1) in sp["steps"] and 0 < kicks < 16 and back == 1
                      and str(steps_ui[0].property("current")) == "on" and str(steps_ui[1].property("current")) == "16",
                      f"paso 1 del bombo {got} → al motor {[s for s in sp['steps'] if s[:2] == (0, 0)]} · "
                      f"suena en {kicks} de 16 compases · vuelve a {back}")

        # Drum Rack: paneo, grupo de corte y golpe propio del pad elegido; el motor recibe los 6 ajustes
        rack = [window.findChild(QObject, n) for n in ("drumLanePan", "padChoke", "padLoad")]
        if None in rack:
            rep.check("Drum Rack: paneo, corte y golpe propio en cada pad", False, "faltan controles del Drum Rack")
        else:
            pan0 = round(float(rack[0].property("value")))
            choke0 = str(rack[1].property("current"))
            panned = synth_settings({"type": "drum", "cfg": {"lanes": [[50, 50, 50, 50, 100, 1]]}})["lanes"][0]
            heard = host.audition({"type": "drum", "cfg": {"vol": 80, "tun": 50, "lanes": [[50, 50, 50, 50, 100, 1]]}, "lane": 0})
            host.engine.preview_stop()
            rep.check("Drum Rack: paneo, corte y golpe propio en cada pad",
                      pan0 == 50 and choke0 == "0" and panned[4:] == [100.0, 1.0] and bool(heard),
                      f"pad de fábrica paneo {pan0} · corte {choke0} · ajustes al motor {panned} · suena {heard}")

        # Drum Synth: perillas del pad elegido; un ajuste llega al motor y suena al pulsar el pad
        lane_knobs = [window.findChild(QObject, n) for n in ("drumLaneKnobs", "drumLaneTun", "drumLaneDec", "drumLaneTone", "drumLaneLvl")]
        if None in lane_knobs:
            rep.check("Drum Synth: perillas por pad en la Batería", False, "faltan las perillas del pad")
        else:
            heard = host.audition({"type": "drum", "cfg": {"vol": 80, "tun": 50, "lanes": [[30, 80, 60, 55]]}, "lane": 0})
            host.engine.preview_stop()
            vals = [round(float(k.property("value"))) for k in lane_knobs[1:]]
            rep.check("Drum Synth: perillas por pad en la Batería",
                      vals == [50, 50, 50, 50] and bool(heard),
                      f"pad de fábrica {vals} · el pad suena con sus ajustes {heard}")

        # Arpegiador: visible con el sintetizador del motor; ritmo, octavas y duración se activan
        # al elegir un patrón, y la canción sigue sonando con los acordes arpegiados
        arp = [window.findChild(QObject, n) for n in ("instArp", "arpMode", "arpRate", "arpOct", "arpGate")]
        if None in arp:
            rep.check("Arpegiador: controles en el Instrumento y el motor lo toca", False, "faltan controles del arpegiador")
        else:
            usable = lambda: bool(arp[0].property("visible")) and all(bool(a.property("enabled")) for a in arp[2:])
            before = usable()
            cmd("cfg", "arp", 1)
            _wait(app, lambda: False, 0.1, host)
            during = usable()
            peak_arp = render_peak()
            cmd("cfg", "arp", 0)
            _wait(app, lambda: False, 0.1, host)
            rep.check("Arpegiador: controles en el Instrumento y el motor lo toca",
                      not before and during and not usable() and peak_arp > -30,
                      f"apagado {before} · arriba {during} · render {peak_arp:.1f} dBFS")

    n = len(snap()["tracks"])
    cmd("add", "ia")
    box = window.findChild(QObject, "newTrackBox")
    shown = bool(box and box.property("opened")) and box.property("page") == "gen"
    if box:
        QMetaObject.invokeMethod(box, "close")
    rep.check("+ IA abre «Pista nueva › Generar con IA» y no crea pistas vacías", shown and len(snap()["tracks"]) == n and
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
        t0 = host.engine.position_seconds()          # con el equipo cargado el transporte arranca tarde:
        _wait(app, lambda: host.engine.position_seconds() - t0 >= 1.0, 8.0, host)   # se espera a 1 s grabado
        _wait(app, lambda: False, 0.2, host)
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

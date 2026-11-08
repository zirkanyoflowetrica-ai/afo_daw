"""Verificación integrada: `AllForOne --selftest` (también con el .exe empaquetado).

Comprueba de verdad cada eslabón y escribe un informe JSON. Nada se da por aprobado sin
ejecutarse; lo que depende de hardware se marca como "omitido" con su motivo.
"""
from __future__ import annotations

import json
import logging
import platform
import sys
import time
from pathlib import Path

from . import __version__, paths

log = logging.getLogger("allforone.selftest")


class Report:
    def __init__(self):
        self.results: list[dict] = []

    def add(self, name: str, status: str, detail="") -> None:
        self.results.append({"name": name, "status": status, "detail": detail})
        log.info("[%s] %s %s", status.upper(), name, detail)

    def check(self, name: str, cond: bool, detail="") -> bool:
        self.add(name, "ok" if cond else "fail", detail)
        return cond

    @property
    def failed(self) -> bool:
        return any(r["status"] == "fail" for r in self.results)


def _wait(app, cond, timeout: float, host=None) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if host is not None:
            host.pump()
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def run_selftest(app, host, report_path: str | None, screenshot_path: str | None) -> int:
    rep = Report()
    out_dir = paths.logs_dir()
    rep.add("entorno", "info", {"allforone": __version__, "python": sys.version.split()[0],
                                 "platform": platform.platform(), "frozen": bool(getattr(sys, "frozen", False) or "__compiled__" in globals())})

    # 1-2. Extensión nativa y motor
    from . import engine_host
    rep.check("python importa afo_audio", engine_host.afo_audio is not None, engine_host.NATIVE_ERROR or "")
    if not rep.check("motor nativo iniciado", host.ok, host.error or ""):
        return _finish(rep, report_path)
    info = host.info()
    rep.add("versiones", "info", {"afo_audio": info["version"], "juce": info["juce"]})
    dev = info["device"]
    rep.add("dispositivo de audio", "info", dev)

    # 3. Audio real: tono -> pista -> render offline -> medición
    afo = engine_host.afo_audio
    tr = host.add_test_tone()
    rep.check("pista de audio en el motor", tr["length_seconds"] > 7.9, f"{tr['name']} {tr['length_seconds']:.2f}s")
    rep.check("forma de onda real", max(tr["peaks"]) > 0.2, f"pico normalizado {max(tr['peaks']):.3f}")
    render = out_dir / "selftest_render.wav"
    rendered = host.engine.render_to_wav(str(render))
    m = afo.measure_file(str(render)) if rendered else {"peak_db": -100, "rms_db": -100}
    rep.check("render offline produce audio", rendered and m["peak_db"] > -30, m)
    try:
        import numpy as np
        import soundfile as sf
        data, sr = sf.read(str(render))
        mono = data.mean(axis=1) if data.ndim > 1 else data
        spec = np.abs(np.fft.rfft(mono[: sr * 2]))
        freq = np.fft.rfftfreq(len(mono[: sr * 2]), 1 / sr)[int(np.argmax(spec))]
        rep.check("frecuencia dominante del render = 440 Hz", abs(freq - 440) < 2, f"{freq:.1f} Hz (soundfile + numpy)")
    except Exception as exc:
        rep.add("verificación cruzada numpy/soundfile", "fail", str(exc))

    # 4-6. Interfaz original + QWebChannel
    from .main import build_window
    window, view, bridge = build_window(host)
    window.show()
    loaded = {"ok": None}
    view.loadFinished.connect(lambda ok: loaded.__setitem__("ok", ok))
    rep.check("Qt WebEngine carga la plantilla", _wait(app, lambda: loaded["ok"] is not None, 30, host) and loaded["ok"], str(view.url().toString()))
    rep.check("JavaScript llama a Python (QWebChannel)", _wait(app, lambda: bridge.js_hello_count > 0, 20, host), f"hello x{bridge.js_hello_count}")

    js_result = {}

    def run_js(code: str, key: str, timeout=10):
        js_result.pop(key, None)
        view.page().runJavaScript(code, 0, lambda r: js_result.__setitem__(key, r))
        _wait(app, lambda: key in js_result, timeout, host)
        return js_result.get(key)

    _wait(app, lambda: run_js("!!(window.AFO&&AFO.engineOk)", "eng", 2), 10, host)
    probe = run_js("""JSON.stringify({
        panels: document.querySelectorAll('.panel').length,
        ids: [...document.querySelectorAll('.panel')].map(p=>p.id),
        bg: getComputedStyle(document.body).backgroundColor,
        font: getComputedStyle(document.body).fontFamily,
        fontLoaded: document.fonts.check('500 14px "Space Grotesk"'),
        header: getComputedStyle(document.querySelector('.ph')).backgroundColor,
        engineOk: !!(window.AFO&&AFO.engineOk),
        audioBtn: !!document.querySelector('[data-add="audio"]'),
        meterRandom: /Math\\.random/.test(String(meters))
    })""", "probe")
    try:
        p = json.loads(probe or "{}")
    except Exception:
        p = {}
    original_ids = ["p-piano", "p-inst", "p-drums", "p-cinta", "p-ia", "p-pistas", "p-mezcla", "p-master"]
    ids = p.get("ids") or []
    rep.check("8 módulos originales de la plantilla presentes", all(i in ids for i in original_ids), ids[:8])
    rep.check("4 módulos del Mezclador V4.2 en el lienzo", all(i in ids for i in ["p-audios", "p-afina", "p-mastia", "p-antes"]), ids[8:])
    rep.check("fondo crema #fff1c9", p.get("bg") == "rgb(255, 241, 201)", p.get("bg"))
    rep.check("tipografía Space Grotesk local cargada", bool(p.get("fontLoaded")), p.get("font"))
    rep.check("cabeceras negras", p.get("header") == "rgb(0, 0, 0)", p.get("header"))
    rep.check("interfaz conectada al motor", bool(p.get("engineOk")))
    rep.check("medidores sin valores aleatorios", p.get("meterRandom") is False)

    # JS -> Python -> C++: añadir el tono desde la interfaz como lo haría el usuario
    before = len(host.engine.tracks())
    run_js("document.querySelector('[data-afo=\"tone\"]').click()", "click")
    rep.check("botón '+ Tono de prueba' crea pista en el motor (JS→Python→C++)",
              _wait(app, lambda: len(host.engine.tracks()) > before, 10, host), f"pistas en el motor: {len(host.engine.tracks())}")
    _wait(app, lambda: False, 0.5, host)
    shown = run_js("JSON.stringify(tracks.filter(t=>t.engineId).map(t=>({n:t.name,p:(t.peaks||[]).length})))", "shown")
    rep.check("pista del motor visible con forma de onda", bool(shown) and '"p":600' in shown, shown)

    # Mezclador V4.2 integrado en los paneles: arrastrar stems, mezclar, masters, A/B, enviar a Pistas
    run_mixer_checks(rep, app, host, view, bridge, run_js)

    # 7-8. Reproducción en tiempo real (requiere dispositivo)
    if dev.get("open"):
        host.engine.set_position_seconds(0)
        host.reset_peak()
        host.engine.play()

        tracks_peak = {"db": -100.0}

        def advancing():
            lv = host.read_levels()   # mismo lector único que usa la interfaz
            tracks_peak["db"] = max([tracks_peak["db"], *lv["tracks"].values()])
            return host.engine.position_seconds() > 1.5

        moved = _wait(app, advancing, 6, host)
        peak = {"db": host.peak_master_db}
        rep.check("transporte avanza en tiempo real", moved, f"{host.engine.position_seconds():.2f}s")
        rep.check("medidor master reacciona a audio real", peak["db"] > -40, f"pico master {peak['db']:.1f} dBFS; pico de pistas {tracks_peak['db']:.1f} dBFS")
        host.engine.stop()
    else:
        rep.add("reproducción en tiempo real", "skipped", "sin dispositivo de salida abierto en este equipo")

    shot = Path(screenshot_path) if screenshot_path else out_dir / "selftest_ui.png"
    _wait(app, lambda: False, 1.0, host)
    view.grab().save(str(shot))
    rep.add("captura de la interfaz", "info", str(shot))
    window.close()
    return _finish(rep, report_path)


def _finish(rep: Report, report_path: str | None) -> int:
    path = Path(report_path) if report_path else paths.logs_dir() / "selftest_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = {"passed": not rep.failed, "results": rep.results}
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(("SELFTEST OK" if not rep.failed else "SELFTEST FALLIDO") + f" -> {path}", flush=True)
    return 1 if rep.failed else 0


def _write_demo_stems(folder: Path) -> list[str]:
    """Stems SINTÉTICOS de prueba (voz con vibrato, 808, kick), 6 s a 44,1 kHz.

    La voz principal se escribe en **coma flotante de 64 bits**, igual que los stems reales
    que exportan muchos DAW: JUCE no los sabe leer y AllForOne debe convertirlos al importar.
    """
    import numpy as np
    import soundfile as sf
    folder.mkdir(parents=True, exist_ok=True)
    sr = 44100
    t = np.arange(sr * 6) / sr
    f = 220 * 2 ** (0.3 / 12 * np.sin(2 * np.pi * 5 * t))
    ph = 2 * np.pi * np.cumsum(f) / sr
    voz = 0.25 * sum(np.sin(k * ph) / k for k in range(1, 7)) * (0.6 + 0.4 * (np.sin(2 * np.pi * 1.5 * t) > 0))
    beat = t % 0.625
    stems = {"Voz_Principal": voz, "808": 0.5 * np.sin(2 * np.pi * 55 * t) * np.exp(-beat * 4),
             "Kick": 0.8 * np.sin(2 * np.pi * 60 * t * np.exp(-beat * 8)) * np.exp(-beat * 15)}
    out = []
    for name, x in stems.items():
        p = folder / f"{name}.wav"
        if name == "Voz_Principal":
            sf.write(str(p), x.astype("float64"), sr, subtype="DOUBLE")
        else:
            sf.write(str(p), x.astype("float32"), sr)
        out.append(str(p))
    return out


def run_mixer_checks(rep, app, host, view, bridge, run_js):
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    from PySide6.QtWidgets import QApplication

    info = bridge.mixsvc.info()
    if not rep.check("Mezclador V4.2 cargado (módulos originales)", info.get("ok", False), info.get("error", f"{len(info.get('profiles', []))} plantillas, {len(info.get('masters', []))} masters")):
        return
    stems = _write_demo_stems(paths.user_data_dir() / "autoprueba" / "stems")
    before_tracks = len(host.engine.tracks())

    # Soltar los archivos sobre el panel Audios con un evento de arrastre real de Qt
    run_js("fit(['audios']);", "fit")
    _wait(app, lambda: False, 0.6, host)
    box = json.loads(run_js("JSON.stringify((()=>{const r=document.querySelector('#p-audios .afo-drop').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})())", "box") or "{}")
    target = view.focusProxy() or view
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(p) for p in stems])
    pt = QPointF(box.get("x", 10), box.get("y", 10))
    enter = QDragEnterEvent(pt.toPoint(), Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(target, enter)   # como en un arrastre real: primero entra, luego suelta
    ev = QDropEvent(pt, Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(target, ev)
    got = {}

    def stems_loaded():
        got["n"] = run_js("AFO_MX.items.filter(i=>i.track).length", "n", 2)
        return (got.get("n") or 0) >= 3
    if not rep.check("soltar 3 audios sobre «Audios» (arrastre de Qt con ruta real)", _wait(app, stems_loaded, 15, host), f"audios con pista: {got.get('n')}"):
        return
    kinds = run_js("JSON.stringify(AFO_MX.items.map(s=>s.name+':'+s.kind+':'+s.role))", "kinds")
    rep.add("clasificación por nombre", "info", kinds)

    # El audio de voz es WAV float de 64 bits: JUCE no lo lee y hay que convertirlo al vuelo
    rep.check("cada audio crea su pista en el motor", len(host.engine.tracks()) >= before_tracks + 3,
              f"pistas en el motor: {len(host.engine.tracks())}")
    conv = run_js("JSON.stringify(AFO_MX.items.filter(i=>i.note).map(i=>i.name))", "conv")
    rep.check("WAV en coma flotante de 64 bits importado (conversión automática)", bool(conv) and "Voz_Principal" in conv, conv)
    strips = run_js("document.querySelectorAll('#b-mezcla .strip').length", "strips", 2)
    roles = run_js("document.querySelectorAll('#b-mezcla .afo-role').length", "roles", 2)
    rep.check("cada pista tiene su tira en la consola, con selector de rol", (strips or 0) >= 3 and (roles or 0) >= 3,
              f"{strips} tiras, {roles} selectores de rol")
    prow = run_js("document.querySelectorAll('#b-pistas .afo-role').length", "prow", 2)
    rep.check("rol de voz también editable en Pistas", (prow or 0) >= 3, f"{prow} selectores en Pistas")

    # Cables del Afinador a las tiras concretas de las voces que va a afinar
    wires = run_js("(()=>{KV.tnStr=60;AFO_MX.tune.voices={lead:true,l:false,r:false,b:false};"
                   "AFO_renderMixer();sync();const n=links().filter(l=>l.f==='afina'&&l.t==='mezcla').length;KV.tnStr=0;return n})()", "wires", 3)
    rep.check("el Afinador se cablea a la tira de la voz que afina", (wires or 0) >= 1, f"{wires} cable(s) afina→tira")

    # MEZCLAR AUTOMÁTICAMENTE (sin afinación: intensidad 0 %)
    run_js("document.querySelector('[data-mx=\"mix\"]').click()", "click")
    t0 = time.monotonic()
    done = _wait(app, lambda: (run_js("AFO_MX.runs.length", "runs", 2) or 0) >= 1 or "Error" in str(run_js("AFO_MX.status", "st", 2)), 240, host)
    status = run_js("AFO_MX.status", "st")
    ok = done and (run_js("AFO_MX.runs.length", "runs") or 0) >= 1
    rep.check("MEZCLAR AUTOMÁTICAMENTE produce una sesión", ok, f"{status} ({time.monotonic() - t0:.1f} s)")
    if not ok:
        return
    run = bridge.mixsvc.runs[-1]
    masters = run["masters"]
    rep.check("4 masters del V4.2 generados", len([k for k in masters if "LUFS" in k]) == 4,
              {k: round(v["lufs"], 1) for k, v in masters.items()})
    plat = masters.get("Plataformas (-14 LUFS, -2 dBTP)", {})
    rep.check("master plataformas cerca de -14 LUFS y bajo -1.5 dBTP", abs(plat.get("lufs", 0) + 14) < 1.5 and plat.get("true_peak", 0) < -1.5,
              f"{plat.get('lufs', 0):.1f} LUFS / {plat.get('true_peak', 0):.2f} dBTP")
    import soundfile as sf
    info_mix = sf.info(run["mix"])
    rep.check("mezcla sin master es audio real", info_mix.frames > info_mix.samplerate * 5, f"{info_mix.frames / info_mix.samplerate:.1f} s, {info_mix.channels} canales")
    rep.check("comparaciones A/B por pista", len(run["review"]) >= 3, f"{len(run['review'])} pistas")
    live = run_js("JSON.stringify(Object.entries(AFO_MX.live).map(([i,v])=>({i:+i,g:v.gain_db,pan:v.pan,fader:+(document.querySelector('#b-mezcla input[data-v=\"'+i+'\"]')||{}).value})))", "live")
    try:
        rows = json.loads(live or "[]")
    except Exception:
        rows = []
    moved = [r for r in rows if r.get("fader") and abs(r["fader"] - 70) > 0.5]
    rep.check("la consola refleja la mezcla: faders movidos a la ganancia real medida",
              len(rows) >= 3 and bool(moved), f"{len(rows)} tiras con datos, {len(moved)} con fader distinto de 0 dB: {rows}")
    # El ZIP ya no se crea en cada mezcla (para una canción entera son GB): se arma al pedirlo.
    rep.check("la mezcla NO deja un ZIP sin pedirlo", not Path(run["zip"]).exists(), run["zip"])
    zipped = bridge.mixsvc.make_zip(run)
    rep.check("ZIP de sesión bajo demanda", Path(zipped).stat().st_size > 10000, zipped)

    # Enviar el master a Pistas desde el panel Master IA
    before = len(host.engine.tracks())
    run_js("document.querySelector('[data-ms=\"tracks\"]').click()", "c2")
    rep.check("Master IA → Pistas (pista nueva en el motor)", _wait(app, lambda: len(host.engine.tracks()) > before, 10, host),
              f"pistas en el motor: {len(host.engine.tracks())}")

    # Escucha A/B (requiere dispositivo)
    if host.engine.device_info().get("open"):
        r = json.loads(bridge.mixer("listen", json.dumps({"what": "master", "sel": 3, "ab": "B", "run": run["id"]})))
        _wait(app, lambda: False, 0.5, host)
        rep.check("escucha A/B del master (previsualización nativa)", r.get("ok") and host.engine.preview_playing(), r)
        host.engine.preview_stop()
    else:
        rep.add("escucha A/B del master", "skipped", "sin dispositivo de salida abierto")

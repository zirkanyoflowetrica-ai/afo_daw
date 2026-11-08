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
    rep.check("8 módulos de la plantilla presentes", p.get("panels") == 8, p.get("ids"))
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

    # 7-8. Reproducción en tiempo real (requiere dispositivo)
    if dev.get("open"):
        host.engine.set_position_seconds(0)
        host.reset_peak()
        host.engine.play()

        def advancing():
            host.read_levels()   # mismo lector único que usa la interfaz
            return host.engine.position_seconds() > 1.0

        moved = _wait(app, advancing, 5, host)
        peak = {"db": host.peak_master_db}
        rep.check("transporte avanza en tiempo real", moved, f"{host.engine.position_seconds():.2f}s")
        rep.check("medidor master reacciona a audio real", peak["db"] > -40, f"pico {peak['db']:.1f} dBFS")
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

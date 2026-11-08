"""Verificación integrada: `AllForOne --selftest` (también con el .exe empaquetado).

Comprueba de verdad cada eslabón (extensión nativa, motor, render, interfaz QML y cada módulo)
y escribe un informe JSON. Nada se da por aprobado sin
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

    # La pista del tono solo servía para medir el render: fuera, para empezar la interfaz limpia
    host.engine.remove_track(tr["id"])
    host.tracks.pop(tr["id"], None)

    # 4-… Interfaz nativa (QML) con el motor real: cada módulo, como lo usaría el usuario
    from .native_ui import run_native_selftest
    return run_native_selftest(app, host, report_path, screenshot_path, rep)


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


def check_mix_run(rep, bridge) -> None:
    """Lo que produce MEZCLAR AUTOMÁTICAMENTE (Mezclador V4.2): masters, mezcla y ZIP bajo demanda."""
    run = bridge.mixsvc.runs[-1]
    masters = run["masters"]
    rep.check("4 masters del V4.2 generados", len([k for k in masters if "LUFS" in k]) == 4,
              {k: round(v["lufs"], 1) for k, v in masters.items()})
    plat = masters.get("Plataformas (-14 LUFS, -2 dBTP)", {})
    rep.check("master plataformas cerca de -14 LUFS y bajo -1.5 dBTP", abs(plat.get("lufs", 0) + 14) < 1.5 and plat.get("true_peak", 0) < -1.5,
              f"{plat.get('lufs', 0):.1f} LUFS / {plat.get('true_peak', 0):.2f} dBTP")
    import soundfile as sf
    info_mix = sf.info(run["mix"])
    rep.check("mezcla sin master es audio real", info_mix.frames > info_mix.samplerate * 5,
              f"{info_mix.frames / info_mix.samplerate:.1f} s, {info_mix.channels} canales")
    rep.check("comparaciones A/B por pista", len(run["review"]) >= 3, f"{len(run['review'])} pistas")
    # El ZIP no se crea en cada mezcla (para una canción entera son GB): se arma al pedirlo.
    rep.check("la mezcla NO deja un ZIP sin pedirlo", not Path(run["zip"]).exists(), run["zip"])
    zipped = bridge.mixsvc.make_zip(run)
    rep.check("ZIP de sesión bajo demanda", Path(zipped).stat().st_size > 10000, zipped)

"""Adaptador del Mezclador Automático V4.2 para los paneles de AllForOne.

Los algoritmos (mixer_engine, scale_tuner, vocal_dsp, vocal_space, mastering_tools,
mix_templates, music_analysis…) se usan SIN modificar desde allforone/mixer_v42.
Este módulo solo sustituye la interfaz Gradio original (app.py): reproduce su
orquestación de `process()` / `preview_hybrid()` / `confirm_hybrid()` y la expone a
los paneles Mezcla IA, Afinador, Master IA y Antes/Después.

Reglas:
  * El trabajo pesado corre en un hilo aparte: nunca en el hilo de la interfaz ni en el de audio.
  * Los originales del usuario no se modifican.
  * La mezcla y el master son EN VIVO (live_mix.py): el V4.2 decide y sus decisiones se aplican
    como fader, paneo y cadenas de efectos reales del motor. No se renderizan WAVs.
"""
from __future__ import annotations

import logging
import math
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from . import paths

log = logging.getLogger("allforone.mixer")

MIXER_DIR = Path(__file__).resolve().parent / "mixer_v42"
VERSION = "4.2"
REF_LABEL = "Según referencia"
AUDIO_EXT = {".wav", ".aif", ".aiff", ".flac", ".ogg", ".mp3"}

_loaded = None
_load_error = None


def load():
    """Importa los módulos del mezclador (una vez). Devuelve un namespace o lanza el error."""
    global _loaded, _load_error
    if _loaded is not None:
        return _loaded
    data = paths.user_data_dir() / "mezclador"
    data.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MEZCLADOR_DATA_DIR", str(data))
    if str(MIXER_DIR) not in sys.path:
        sys.path.insert(0, str(MIXER_DIR))
    try:
        import numpy as np
        import pyloudnorm as pyln
        import mixer_engine as eng
        import mix_templates as tpl
        import scale_tuner
        import track_tools
        import music_confirmation
        _loaded = type("Mixer", (), dict(np=np, pyln=pyln, eng=eng, tpl=tpl, tuner=scale_tuner,
                                         tracks=track_tools, confirm=music_confirmation))
        return _loaded
    except Exception as exc:  # dependencias que falten se informan, no se simulan
        _load_error = f"{type(exc).__name__}: {exc}"
        log.exception("No se pudo cargar el Mezclador V4.2")
        raise


def safe_name(name):
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", Path(name).stem)[:55].strip("_") or "pista"


# ----------------------------------------------------------------------------------------
# Clasificación (lo mismo que hace el mezclador con el nombre) y correcciones del usuario
# ----------------------------------------------------------------------------------------
def predicted_role(m, filename: str, kind: str) -> str:
    eng = m.eng
    if eng.is_backing_voice(filename):
        pos = eng.backing_position(filename)
        return "B_L" if "Izq" in pos else "B_R" if "Der" in pos else "B"
    pan = eng.pan_from_filename(filename)
    if kind in eng.VOCALS or kind == "Voz lateral (_L/_R)":
        return "L" if pan == "Izquierda" else "R" if pan == "Derecha" else "P"
    return "—"


def describe(m, path: str) -> dict:
    eng = m.eng
    p = Path(path)
    kind = eng.guess_type(p.name)
    if eng.is_lateral_voice(p.name, kind) and kind != "Voz de apoyo (_B)":
        kind = "Voz lateral (_L/_R)"
    return {"path": str(p), "name": p.stem, "kind": kind, "role": predicted_role(m, p.name, kind),
            "auto_kind": kind, "auto_role": predicted_role(m, p.name, kind)}


# ----------------------------------------------------------------------------------------
class MixerService:
    """Una instancia por aplicación. `emit(dict)` envía eventos al panel (hilo cualquiera)."""

    def __init__(self, emit):
        self.emit = emit
        self.analysis: dict | None = None
        self.analysis_signature: str | None = None
        self.approval: dict | None = None
        self.busy = False
        self._lock = threading.Lock()

    # --- información para los paneles -----------------------------------------------
    def info(self) -> dict:
        try:
            m = load()
        except Exception:
            return {"ok": False, "error": f"Mezclador V4.2 no disponible: {_load_error}"}
        return {"ok": True, "version": VERSION,
                "profiles": [[k, v["name"], v.get("tag", "")] for k, v in m.tpl.PROFILES.items()],
                "modes": list(m.tpl.GUIDE_MODES), "keys": list(m.tuner.KEYS), "scales": list(m.tuner.SCALES),
                "masters": list(m.eng.MASTERS), "types": list(m.eng.TYPES), "max_tracks": m.eng.MAX_TRACKS,
                "step_default": m.eng.BACKING_STEP_DEFAULT_DB}

    def describe_paths(self, files: list[str]) -> list[dict]:
        m = load()
        return [describe(m, f) for f in files if Path(f).suffix.lower() in AUDIO_EXT and Path(f).is_file()]

    # --- análisis musical (Afinador) -------------------------------------------------
    def _music_paths(self, payload):
        return [s["path"] for s in payload.get("stems", [])]

    def analyze_async(self, payload: dict) -> dict:
        if not payload.get("stems"):
            return {"ok": False, "error": "Carga stems instrumentales en Mezcla IA antes de analizar."}
        return self._start("analysis", self._analyze, payload)

    def _analyze(self, payload):
        m = load()
        from music_analysis import analyze_music
        paths_ = self._music_paths(payload)
        flags = {"essentia": False, "beat_this": True}
        self.emit({"type": "progress", "panel": "afina", "p": 20, "desc": "Analizando instrumentos (las voces no participan)…"})
        result = analyze_music(paths_, use_essentia=False, use_beat_this=True)
        data = result.as_dict()
        data["source_signature"] = m.confirm.signature(paths_, None, flags)
        self.analysis = data
        self.approval = None
        self.emit({"type": "analysis", "summary": result.summary(), "key": data.get("key"), "scale": data.get("scale"),
                   "bpm": data.get("bpm"), "key_confidence": data.get("key_confidence"), "bpm_confidence": data.get("bpm_confidence")})

    def confirm(self, payload: dict) -> dict:
        """Igual que confirm_hybrid() del original: autoriza una combinación concreta."""
        m = load()
        t = payload.get("tune", {})
        mode = t.get("mode", "Automático")
        paths_ = self._music_paths(payload)
        try:
            if mode != "Manual":
                expected = m.confirm.signature(paths_, None, {"essentia": False, "beat_this": True})
                if not self.analysis or self.analysis.get("source_signature") != expected:
                    raise ValueError("Primero pulsa «Analizar música» con estos stems.")
            choice = m.confirm.resolve_choice(self.analysis or {}, mode, t.get("key", "F"), t.get("scale", "Menor natural"),
                                              float(t.get("bpm", 91)), bool(t.get("prefer", True)))
            choice["signature"] = m.confirm.signature(paths_, None, {"mode": mode, "key": t.get("key"), "scale": t.get("scale"),
                                                                     "bpm": float(t.get("bpm", 91))})
            choice["confirmed"] = True
            self.approval = choice
            msg = (f'CONFIRMADO: {choice["key"]} {choice["scale"]}, {choice["bpm"]:.1f} BPM. '
                   f'{choice["source"]}. Afinación permitida por canales separados.')
            return {"ok": True, "confirmed": {"key": choice["key"], "scale": choice["scale"], "bpm": choice["bpm"]}, "status": msg}
        except (ValueError, OSError) as exc:
            self.approval = None
            return {"ok": False, "error": f"Sin confirmar: {exc}"}

    # --- mezcla en vivo ------------------------------------------------------------------
    def mix_async(self, payload: dict) -> dict:
        stems = [s for s in payload.get("stems", []) if int(s.get("trackId", -1)) >= 0]
        if not stems:
            return {"ok": False, "error": "Carga audios en el módulo «Audios»: la mezcla en vivo trabaja sobre sus pistas."}
        strength = float(payload.get("tune", {}).get("strength", 0))
        if strength > 0 and not self.approval:
            return {"ok": False, "error": "Para afinar, confirma la tonalidad y el BPM en el panel Afinador (o deja la intensidad en 0 %)."}
        return self._start("mix", self._live, dict(payload, stems=stems))

    def _start(self, kind, fn, payload):
        with self._lock:
            if self.busy:
                return {"ok": False, "error": "El mezclador ya está trabajando; espera a que termine."}
            self.busy = True

        def run():
            try:
                fn(payload)
            except MemoryError:
                self.emit({"type": "error", "panel": kind, "error": "Falta memoria: prueba menos stems o una sección más corta."})
            except Exception as exc:
                log.exception("Fallo en %s", kind)
                self.emit({"type": "error", "panel": kind, "error": f"{exc}", "trace": traceback.format_exc()[-1500:]})
            finally:
                self.busy = False
                self.emit({"type": "idle"})

        threading.Thread(target=run, name=f"afo-mixer-{kind}", daemon=True).start()
        return {"ok": True, "started": kind}

    def _live(self, payload):
        """Decide la mezcla (V4.2) en este hilo; el puente la aplica en el motor desde el hilo principal.

        No se renderiza nada: solo se escribe audio si se pidió afinación (PSOLA no es un efecto
        en tiempo real), una copia afinada por voz elegida.
        """
        from . import live_mix
        m = load()
        eng, tpl = m.eng, m.tpl
        t0 = time.monotonic()
        stems = payload["stems"][: eng.MAX_TRACKS]
        tune = payload.get("tune", {})
        strength = float(tune.get("strength", 0))
        bpm = float(self.approval["bpm"]) if self.approval else 0.0
        opts = {"profile": payload.get("profile") or tpl.DEFAULT_TEMPLATE, "template_mode": payload.get("mode") or tpl.GUIDE_ONLY,
                "step_db": float(payload.get("step_db", eng.BACKING_STEP_DEFAULT_DB)), "space": float(payload.get("space", 45.0)),
                "bpm": bpm}

        def progress(i, n, stem):
            self.emit({"type": "progress", "panel": "mezcla", "p": round(5 + 80 * i / max(1, n), 1),
                       "desc": f"Decidiendo {Path(stem['path']).name}…"})
            self.emit({"type": "strip", "i": stems.index(stem), "phase": "work"})

        result = live_mix.plan(m, stems, opts, progress)
        for stem, t in zip(stems, result["tracks"]):
            t["trackId"] = int(stem["trackId"])
        if strength > 0 and self.approval:
            voices = tune.get("voices", {})
            tuning = dict(key=self.approval["key"], scale=self.approval["scale"], strength=strength,
                          tune_lead=bool(voices.get("lead", True)), tune_left=bool(voices.get("l", False)),
                          tune_right=bool(voices.get("r", False)), tune_center_backings=bool(voices.get("b", False)))
            dest = paths.user_data_dir() / "afinadas"
            for t in result["tracks"]:
                if t.get("skip") or not eng._should_tune_vocal(tuning, t["kind"], t["kind"] == "Voz lateral (_L/_R)", t["position"]):
                    continue
                self.emit({"type": "progress", "panel": "mezcla", "p": 88, "desc": f"Afinando {t['name']}…"})
                from scale_tuner import tune_to_scale
                x, note = tune_to_scale(eng.load_stem(t["path"]), eng.SR, tuning["key"], tuning["scale"], strength)
                dest.mkdir(parents=True, exist_ok=True)
                t["tuned_path"] = eng.save_wav(dest / f"{safe_name(t['path'])}_afinada_{datetime.now():%H%M%S}.wav", x, subtype="FLOAT")
                t["notes"].append(f"afinada en {tuning['key']} {tuning['scale']} al {strength:.0f} %: {note}")
        reference = (payload.get("reference") or {}).get("path")
        if reference:
            x = eng.load_stem(reference)
            lufs = eng._lufs(eng.stereo(x, "Original / centro"), m.pyln.Meter(eng.SR))
            result["reference_lufs"] = lufs if math.isfinite(lufs) else None
        result["seconds"] = round(time.monotonic() - t0, 2)
        result["profile_name"] = tpl.PROFILES[opts["profile"]]["name"]
        result["master"] = payload.get("master")
        for t in result["tracks"]:
            for k in ("power", "bands"):
                t.pop(k, None)
        self.emit({"type": "_plan", "plan": result})


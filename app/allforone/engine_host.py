"""Capa Python sobre el motor nativo afo_audio.

Si la extensión no se puede importar, la aplicación arranca igualmente y lo informa:
no se simula audio ni medidores.
"""
from __future__ import annotations

import json
import logging
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import audio_import, paths

log = logging.getLogger("allforone.engine")

try:  # extensión compilada por CMake en allforone/_native
    from ._native import afo_audio  # type: ignore
    NATIVE_ERROR = None
except Exception as exc:  # pragma: no cover - depende del entorno
    afo_audio = None
    NATIVE_ERROR = f"{type(exc).__name__}: {exc}"

UNITY_POS = 70.0  # posición de fader de la plantilla que equivale a 0 dB


def fader_to_db(pos: float) -> float:
    """Ley del fader 0..100 de la plantilla: 70 = 0 dB, 100 = +6.2 dB, 0 = silencio."""
    pos = max(0.0, min(100.0, float(pos)))
    if pos <= 0.0:
        return -100.0
    return max(-100.0, 40.0 * math.log10(pos / UNITY_POS))


# Secuenciador de la plantilla: 16 compases de 16 semicorcheas en el carril de Pistas
STEPS = 256
FIRST_DRUM_NOTE = 36                       # carril i de la Batería = nota MIDI 36 + i
ROLL_TOP_NOTE = 72                         # fila 0 del piano roll = C5; fila 12 = C4


def in_clip(clips, bar: int) -> bool:
    return any(bar * 6.25 >= c[0] - 0.01 and bar * 6.25 < c[0] + c[1] - 0.01 for c in clips)


def pattern_notes(track: dict) -> list[tuple[float, int]]:
    """(negra, nota MIDI) de cada nota que tocaba el reloj de la plantilla (tick) en los 16 compases.

    Instrumento: cada nota del piano roll se repite en cada compás que cae dentro de un clip.
    Batería: cada paso activo del patrón, igual.
    """
    out = []
    roll = [tuple(map(int, k.split("-"))) for k in (track.get("roll") or {})]
    pat = [tuple(map(int, k.split("-"))) for k, on in (track.get("pat") or {}).items() if on]
    swing = max(0.0, min(100.0, float((track.get("cfg") or {}).get("sw", 0)))) / 100
    # Octava del Piano roll (X2): la rejilla es C4..C5 en la octava 4; cada octava más sube 12 semitonos
    shift = 12 * (max(1, min(7, int((track.get("cfg") or {}).get("oct", 4)))) - 4)
    for st in range(STEPS):
        bar, s = st >> 4, st % 16
        if not in_clip(track.get("clips", []), bar):
            continue
        beat = st / 4
        if track["type"] == "inst":
            out += [(beat, ROLL_TOP_NOTE - r + shift) for r, c in roll if c == s]
        elif track["type"] == "drum":
            # Swing: las semicorcheas pares se retrasan hasta media semicorchea (perilla al 100 %)
            if s % 2:
                beat += swing * 0.125
            out += [(beat, FIRST_DRUM_NOTE + lane) for lane, c in pat if c == s]
    return out


# Step Sequencer: un paso encendido es 1 (de fábrica) o [fuerza 1..127, probabilidad %, repeticiones 1..4]
STEP_DEFAULT = (100, 100, 1)


def step_pattern(track: dict) -> dict:
    """Patrón de la Batería para el Step Sequencer del motor (Engine.set_step_pattern / expand_steps):
    pasos con fuerza, probabilidad y repeticiones, largo de cada pad (cfg.len), compases dentro de un
    clip, swing (cfg.sw) y semilla de la probabilidad (cfg.seed)."""
    cfg = track.get("cfg") or {}
    steps = []
    for k, v in (track.get("pat") or {}).items():
        if not v:
            continue
        lane, s = map(int, k.split("-"))
        vals = (list(v) if isinstance(v, (list, tuple)) else []) + [None] * 3
        steps.append((lane, s, *(d if x is None else int(round(float(x))) for x, d in zip(vals[:3], STEP_DEFAULT))))
    lens = [16 if not x else max(1, min(16, int(x))) for x in (list(cfg.get("len") or []) + [16] * 8)[:8]]
    return {"steps": sorted(steps), "lengths": lens,
            "bars": [in_clip(track.get("clips", []), b) for b in range(STEPS // 16)],
            "swing": max(0.0, min(100.0, float(cfg.get("sw", 0)))) / 100,
            "seed": max(0, int(cfg.get("seed", 0))), "total_steps": STEPS}


# Sinte analógico (preset 9): clave en cfg y valor de fábrica, en el orden que espera el motor
ANALOG_KNOBS = (("anDet", 30), ("anCut", 55), ("anRes", 30), ("anEnv", 50), ("anAtk", 5), ("anRel", 30))
# Sinte de tablas (preset 10): tabla (0 Básica, 1 Vocal, 2 Metálica, 3 Digital), posición, barrido, movimiento, ataque, liberación
WAVE_KNOBS = (("wtTab", 0), ("wtPos", 40), ("wtEnv", 30), ("wtLfo", 0), ("wtAtk", 5), ("wtRel", 30))
# Sampler (preset 11): nota raíz, inicio %, bucle (0/1), inicio del bucle %, ataque, liberación; el sonido va en cfg.smpFile
SAMPLER = 11
SAMPLER_KNOBS = (("smRoot", 60), ("smStart", 0), ("smLoop", 0), ("smLoopAt", 50), ("smAtk", 2), ("smRel", 25))


# Drum Synth / Drum Rack: por pad [afinación, caída, tono, nivel, paneo, grupo de corte] y sus valores de fábrica
LANE_DEFAULTS = (50.0, 50.0, 50.0, 50.0, 50.0, 0.0)


def synth_settings(track: dict) -> dict:
    cfg = track.get("cfg", {})
    if track["type"] == "drum":
        lanes = [[d if x is None else float(x) for x, d in zip((list(l or []) + [None] * 6)[:6], LANE_DEFAULTS)]
                 for l in (cfg.get("lanes") or [])[:8]]
        return {"mode": 1, "vol": float(cfg.get("vol", 80)), "tun": float(cfg.get("tun", 50)), "lanes": lanes}
    return {"mode": 0, "wave": int(cfg.get("v", 0)), "vel": float(cfg.get("vel", 70)),
            "bri": float(cfg.get("bri", 50)), "sus": bool(track.get("sus")), "rev": float(cfg.get("rev", 0)),
            "glide": float(cfg.get("glide", 30)), "drive": float(cfg.get("drive", 30)), "punch": float(cfg.get("punch", 50)),
            "arp": int(cfg.get("arp", 0)), "arp_rate": int(cfg.get("arpRate", 2)), "arp_oct": int(cfg.get("arpOct", 1)),
            "arp_gate": float(cfg.get("arpGate", 50)),
            "analog": [float(cfg.get(k, d)) for k, d in ANALOG_KNOBS],
            "wavetable": [float(cfg.get(k, d)) for k, d in WAVE_KNOBS],
            "sampler": [float(cfg.get(k, d)) for k, d in SAMPLER_KNOBS]}


def _loud(d: dict) -> list[float]:
    return [round(d[k], 1) for k in ("peak_db", "rms_db", "lufs_m", "lufs_s", "lufs_i")]


@dataclass
class EngineHost:
    engine: object | None = None
    error: str | None = None
    tracks: dict[int, dict] = field(default_factory=dict)
    # Los medidores nativos son "leer y borrar": este es el ÚNICO lector (ver read_levels)
    last_levels: dict = field(default_factory=lambda: {"master_l_db": -100.0, "master_r_db": -100.0, "tracks": {}})
    peak_master_db: float = -100.0

    @classmethod
    def create(cls) -> "EngineHost":
        if afo_audio is None:
            log.error("Extensión afo_audio no disponible: %s", NATIVE_ERROR)
            return cls(error=f"afo_audio no disponible ({NATIVE_ERROR})")
        try:
            eng = afo_audio.Engine("AllForOne", str(paths.user_data_dir() / "motor"))
        except Exception as exc:
            log.exception("No se pudo iniciar el motor")
            return cls(error=f"No se pudo iniciar el motor: {exc}")
        host = cls(engine=eng)
        host.apply_pending_device()
        log.info("Motor nativo %s (JUCE %s) | dispositivo %s", afo_audio.version(), afo_audio.juce_version(), eng.device_info())
        return host

    # Sin ningún dispositivo abierto, cambiar de driver con el programa en marcha puede cerrar el
    # proceso dentro del driver (visto con ASIO). Al arrancar, antes de procesar mensajes, funciona:
    # la elección se guarda y se aplica al volver a abrir AllForOne.
    @staticmethod
    def pending_device_file() -> Path:
        return paths.user_data_dir() / "motor" / "dispositivo_pendiente.json"

    def save_pending_device(self, d: dict) -> None:
        f = self.pending_device_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def apply_pending_device(self) -> None:
        f = self.pending_device_file()
        if not f.is_file():
            return
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            f.unlink()
            err = self.set_audio_device(d)
            log.info("Dispositivo elegido antes de reiniciar: %s%s", d, f" ({err})" if err else "")
        except Exception:
            log.exception("No se pudo aplicar el dispositivo pendiente")

    @property
    def ok(self) -> bool:
        return self.engine is not None

    @staticmethod
    def needs_message_pump() -> bool:
        # En Windows el bucle de eventos de Qt ya despacha los mensajes Win32 de JUCE.
        return sys.platform != "win32"

    def pump(self) -> None:
        if afo_audio is not None and self.needs_message_pump():
            afo_audio.pump_messages(0)

    # --- información -------------------------------------------------------
    def info(self) -> dict:
        if not self.ok:
            return {"engine": False, "error": self.error}
        return {
            "engine": True,
            "version": afo_audio.version(),
            "juce": afo_audio.juce_version(),
            "device": self.engine.device_info(),
            "api": afo_audio.API_VERSION,
        }

    # --- pistas -------------------------------------------------------------
    def add_audio(self, path: str, name: str = "", buckets: int = 600, convert: bool = True) -> dict:
        """Importa un archivo como pista.

        Si el motor no sabe leer el formato (p. ej. WAV en coma flotante de 64 bits,
        que JUCE rechaza) y `convert`, se carga una copia convertida y se avisa; el
        original no se toca. Con `convert=False` se propaga el error: así quien llama
        puede convertir en otro hilo sin bloquear la ventana (ver bridge.importPaths).
        """
        original = str(path)
        try:
            return self.add_prepared(original, original, "", name, buckets)
        except Exception as exc:
            if not convert:
                raise
            try:
                readable, note = audio_import.to_engine_wav(original)
            except Exception as conv:
                raise RuntimeError(f"{exc} [{conv}]") from exc
            return self.add_prepared(original, str(readable), note, name, buckets)

    def add_prepared(self, original: str, readable: str, note: str = "", name: str = "", buckets: int = 600) -> dict:
        """Crea la pista a partir de un archivo que el motor ya sabe leer (hilo principal)."""
        info = dict(self.engine.add_audio_track(readable, name or (Path(original).stem if note else "")))
        info["peaks"] = [round(v, 4) for v in self.engine.track_peaks(info["id"], buckets)]
        info["originalPath"] = original
        info["note"] = note
        self.tracks[info["id"]] = info
        return info

    # --- Instrumento y Batería (sintetizador del motor) ---------------------------------
    def add_synth(self, name: str, mode: int) -> dict:
        info = dict(self.engine.add_synth_track(name, mode))
        info.update(peaks=[], originalPath="", note="")
        self.tracks[info["id"]] = info
        return info

    def drum_samples(self, track_id: int, track: dict) -> list[str]:
        """Sampler de la batería: `cfg.smp` = una ruta por carril ("" = sonido sintetizado). Solo se
        recarga si cambió; un archivo que ya no existe vuelve al sonido sintetizado (y se dice)."""
        want = [str(x or "") for x in ((track.get("cfg") or {}).get("smp") or [])][:8]
        want += [""] * (8 - len(want))
        ok = [p if p and Path(p).is_file() else "" for p in want]
        if getattr(self, "_drum_samples", None) is None:
            self._drum_samples = {}
        if self._drum_samples.get(track_id) != ok:
            self.engine.set_drum_samples(track_id, ok)
            self._drum_samples[track_id] = ok
        return [p for p, k in zip(want, ok) if p and not k]

    def inst_sample(self, track_id: int, track: dict) -> str:
        """Sampler del Instrumento: `cfg.smpFile` = el sonido de la pista. Solo se recarga si cambió.
        Devuelve la ruta si ya no existe (la pista se queda sin sonido y se dice), si no ""."""
        want = str((track.get("cfg") or {}).get("smpFile") or "")
        ok = want if want and Path(want).is_file() else ""
        if getattr(self, "_inst_samples", None) is None:
            self._inst_samples = {}
        if self._inst_samples.get(track_id) != ok:
            self.engine.set_instrument_sample(track_id, ok)
            self._inst_samples[track_id] = ok
        return want if want and not ok else ""

    def update_synth(self, track_id: int, track: dict) -> float:
        """Parámetros y patrón; el clip MIDI se rehace entero. Devuelve su duración en segundos."""
        self.engine.set_synth_settings(track_id, **synth_settings(track))
        if track["type"] == "drum":
            self.drum_samples(track_id, track)
        else:
            self.inst_sample(track_id, track)
        if track.get("settingsOnly"):            # perillas: no hace falta rehacer el clip
            return -1.0
        if track.get("midi"):                    # MIDI importado o compuesto por la IA: notas con duración
            notes = [(float(n[0]), float(n[1]), int(n[2]), int(n[3])) for n in track["midi"]]
            return self.engine.set_synth_midi(track_id, notes, 0.0)
        if track["type"] == "drum":              # Step Sequencer del motor
            return self.engine.set_step_pattern(track_id, **step_pattern(track))
        return self.engine.set_synth_notes(track_id, pattern_notes(track), float(STEPS) / 4)

    def audition(self, data: dict) -> bool:
        s = synth_settings(data)
        if data["type"] == "drum":
            tid = int(data.get("id", -1))
            if tid >= 0 and tid in self.tracks:
                self.drum_samples(tid, data)
            return self.engine.audition_synth(FIRST_DRUM_NOTE + int(data["lane"]), 0.0, **s,
                                              track_id=tid if tid in self.tracks else -1)
        tid = int(data.get("id", -1))
        if tid in self.tracks and int((data.get("cfg") or {}).get("v", 0)) == SAMPLER:
            self.inst_sample(tid, data)
        else:
            tid = -1
        return self.engine.audition_synth(int(data["note"]), float(data.get("seconds", 0.4)), **s, track_id=tid)

    # --- dispositivo de audio --------------------------------------------------
    def audio_options(self, type_name: str = "") -> dict:
        info = self.engine.device_info()
        opts = self.engine.audio_device_options(type_name or "")
        return {"device": info, "types": info["available_types"], "options": opts}

    def set_audio_device(self, d: dict) -> str:
        """Devuelve "" si se abrió el dispositivo, o el mensaje de error del driver."""
        return self.engine.set_audio_device(str(d.get("type", "")), str(d.get("output", "")), str(d.get("input", "")),
                                            float(d.get("sampleRate", 0) or 0), int(d.get("bufferSize", 0) or 0))

    # --- grabación (Tracktion escribe el WAV desde su hilo; aquí solo se manda) ------------
    def add_record_track(self, name: str) -> dict:
        info = dict(self.engine.add_record_track(name))
        info.update(peaks=[], originalPath="", note="")
        self.tracks[info["id"]] = info
        return info

    # --- buses Aux y envíos -------------------------------------------------------------
    def add_aux(self, name: str) -> dict:
        info = dict(self.engine.add_aux_track(name))
        info.update(peaks=[], originalPath="", note="")
        self.tracks[info["id"]] = info
        return info

    def finish_take(self, discard: bool = False, buckets: int = 600) -> dict:
        info = dict(self.engine.stop_recording(discard))
        info["peaks"] = [round(v, 4) for v in self.engine.track_peaks(info["id"], buckets)] if info["source_path"] else []
        info.update(originalPath=info["source_path"], note="")
        self.tracks[info["id"]] = info
        return info

    # --- efectos nativos -------------------------------------------------------------
    @staticmethod
    def effect_catalog() -> list[dict]:
        return afo_audio.effect_catalog() if afo_audio is not None else []

    def add_test_tone(self) -> dict:
        path = paths.media_dir() / "tono_prueba_440Hz.wav"
        if not path.exists():
            if not afo_audio.write_test_tone(str(path), 440.0, 8.0, 48000.0, -12.0):
                raise RuntimeError("No se pudo escribir el tono de prueba")
        return self.add_audio(str(path), "Tono de prueba 440 Hz (sintético)")

    def remove(self, track_id: int) -> bool:
        self.tracks.pop(track_id, None)
        return self.engine.remove_track(track_id)

    # --- medición ----------------------------------------------------------------
    def read_levels(self) -> dict:
        """Lee (y vacía) los picos del motor. Todo consumidor debe pasar por aquí."""
        lv = self.engine.read_levels()
        self.last_levels = lv
        self.peak_master_db = max(self.peak_master_db, lv["master_l_db"], lv["master_r_db"])
        return lv

    def reset_peak(self) -> None:
        self.peak_master_db = -100.0

    # --- estado para la interfaz ---------------------------------------------
    def snapshot(self) -> dict:
        lv = self.read_levels()
        return {
            "playing": self.engine.is_playing(),
            "position": round(self.engine.position_seconds(), 4),
            "length": round(self.engine.length_seconds(), 3),
            "master": [round(lv["master_l_db"], 1), round(lv["master_r_db"], 1)],
            "vu": round(lv["master_vu_db"], 1),
            "tracks": {str(k): round(v, 1) for k, v in lv["tracks"].items()},
            # Sonoridad tras el fader de cada pista y tras el master: [pico, RMS, LUFS M, LUFS S, LUFS I]
            "loud": {str(k): _loud(v) for k, v in lv.get("loud", {}).items()},
            "mloud": _loud(lv["master_loud"]) if "master_loud" in lv else None,
            "rec": self._rec_state(),
            "preview": self.engine.preview_playing(),
        }

    def _rec_state(self) -> dict | None:
        r = self.engine.record_state()
        if not r["armed_track"]:
            return None
        return {"track": r["armed_track"], "recording": r["recording"], "seconds": round(r["seconds"], 2),
                "input": r["input"], "db": round(r["input_db"], 1), "monitor": r["monitor"]}

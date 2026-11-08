"""Capa Python sobre el motor nativo afo_audio.

Si la extensión no se puede importar, la aplicación arranca igualmente y lo informa:
no se simula audio ni medidores.
"""
from __future__ import annotations

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
    for st in range(STEPS):
        bar, s = st >> 4, st % 16
        if not in_clip(track.get("clips", []), bar):
            continue
        beat = st / 4
        if track["type"] == "inst":
            out += [(beat, ROLL_TOP_NOTE - r) for r, c in roll if c == s]
        elif track["type"] == "drum":
            # Swing: las semicorcheas pares se retrasan hasta media semicorchea (perilla al 100 %)
            if s % 2:
                beat += swing * 0.125
            out += [(beat, FIRST_DRUM_NOTE + lane) for lane, c in pat if c == s]
    return out


def synth_settings(track: dict) -> dict:
    cfg = track.get("cfg", {})
    if track["type"] == "drum":
        return {"mode": 1, "vol": float(cfg.get("vol", 80)), "tun": float(cfg.get("tun", 50))}
    return {"mode": 0, "wave": int(cfg.get("v", 0)), "vel": float(cfg.get("vel", 70)),
            "bri": float(cfg.get("bri", 50)), "sus": bool(track.get("sus")), "rev": float(cfg.get("rev", 0))}


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
        log.info("Motor nativo %s (JUCE %s) | dispositivo %s", afo_audio.version(), afo_audio.juce_version(), eng.device_info())
        return host

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

    def update_synth(self, track_id: int, track: dict) -> float:
        """Parámetros y patrón; el clip MIDI se rehace entero. Devuelve su duración en segundos."""
        self.engine.set_synth_settings(track_id, **synth_settings(track))
        if track.get("settingsOnly"):            # perillas: no hace falta rehacer el clip
            return -1.0
        return self.engine.set_synth_notes(track_id, pattern_notes(track), float(STEPS) / 4)

    def audition(self, data: dict) -> bool:
        s = synth_settings(data)
        if data["type"] == "drum":
            return self.engine.audition_synth(FIRST_DRUM_NOTE + int(data["lane"]), 0.0, **s)
        return self.engine.audition_synth(int(data["note"]), float(data.get("seconds", 0.4)), **s)

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
        }

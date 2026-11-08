"""Capa Python sobre el motor nativo afo_audio.

Si la extensión no se puede importar, la aplicación arranca igualmente y lo informa:
no se simula audio ni medidores.
"""
from __future__ import annotations

import logging
import math
import sys
from dataclasses import dataclass, field

from . import paths

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
            eng = afo_audio.Engine("AllForOne")
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
    def add_audio(self, path: str, name: str = "", buckets: int = 600) -> dict:
        info = dict(self.engine.add_audio_track(path, name))
        info["peaks"] = [round(v, 4) for v in self.engine.track_peaks(info["id"], buckets)]
        self.tracks[info["id"]] = info
        return info

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
            "tracks": {str(k): round(v, 1) for k, v in lv["tracks"].items()},
        }

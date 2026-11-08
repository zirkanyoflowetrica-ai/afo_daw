"""Objeto expuesto a JavaScript mediante QWebChannel (nombre: "afo").

JavaScript dibuja; Python coordina; C++ procesa el audio. Por el canal solo viajan comandos,
estados y datos visuales compactos (picos de forma de onda), nunca bloques de audio.
Todas las respuestas son JSON: {"ok": bool, ...}.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QWidget

from .engine_host import EngineHost, fader_to_db

log = logging.getLogger("allforone.bridge")
AUDIO_FILTER = "Audio (*.wav *.aif *.aiff *.flac *.ogg *.mp3);;Todos (*.*)"


def _ok(**kw) -> str:
    return json.dumps({"ok": True, **kw})


def _err(msg: str, **kw) -> str:
    log.warning(msg)
    return json.dumps({"ok": False, "error": msg, **kw})


class Bridge(QObject):
    stateChanged = Signal(str)

    def __init__(self, host: EngineHost, parent_widget: QWidget | None = None):
        super().__init__()
        self.host = host
        self.parent_widget = parent_widget
        self.js_hello_count = 0
        self.last_error: str | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 Hz para cursor y medidores
        self._timer.timeout.connect(self._tick)
        if host.ok:
            self._timer.start()

    def _tick(self) -> None:
        try:
            self.host.pump()
            self.stateChanged.emit(json.dumps(self.host.snapshot()))
        except Exception as exc:  # no detener la interfaz por un fallo de lectura
            self.last_error = str(exc)
            log.exception("Error leyendo el estado del motor")

    def _guard(self):
        if not self.host.ok:
            return _err(self.host.error or "Motor nativo no disponible")
        return None

    # --- conexión -------------------------------------------------------------
    @Slot(result=str)
    def hello(self) -> str:
        self.js_hello_count += 1
        return json.dumps(self.host.info())

    @Slot(str)
    def log(self, message: str) -> None:
        log.info("[JS] %s", message)

    # --- transporte -------------------------------------------------------------
    @Slot(result=str)
    def togglePlay(self) -> str:
        if (g := self._guard()):
            return g
        eng = self.host.engine
        if eng.is_playing():
            eng.pause()
            return _ok(playing=False)
        dev = eng.device_info()
        if not dev.get("open"):
            return _err("No hay dispositivo de salida de audio abierto: el motor no puede reproducir. Revisa tu interfaz de audio.")
        eng.play()
        return _ok(playing=True)

    @Slot(result=str)
    def stop(self) -> str:
        if (g := self._guard()):
            return g
        self.host.engine.stop()
        return _ok()

    @Slot(float, result=str)
    def setTempo(self, bpm: float) -> str:
        if (g := self._guard()):
            return g
        self.host.engine.set_tempo(float(bpm))
        return _ok(bpm=self.host.engine.tempo())

    # --- mezcla ------------------------------------------------------------------
    @Slot(float, result=str)
    def setMasterVolume(self, pos: float) -> str:
        if (g := self._guard()):
            return g
        db = fader_to_db(pos)
        self.host.engine.set_master_gain_db(db)
        return _ok(db=db)

    @Slot(int, float, result=str)
    def setTrackVolume(self, track_id: int, pos: float) -> str:
        if (g := self._guard()):
            return g
        db = fader_to_db(pos)
        self.host.engine.set_track_gain_db(int(track_id), db)
        return _ok(db=db)

    @Slot(int, float, result=str)
    def setTrackPan(self, track_id: int, pan: float) -> str:
        if (g := self._guard()):
            return g
        self.host.engine.set_track_pan(int(track_id), float(pan))
        return _ok()

    @Slot(str, result=str)
    def setTrackStates(self, payload: str) -> str:
        if (g := self._guard()):
            return g
        for tid, mute, solo in json.loads(payload):
            self.host.engine.set_track_mute(int(tid), bool(mute))
            self.host.engine.set_track_solo(int(tid), bool(solo))
        return _ok()

    # --- pistas -------------------------------------------------------------------
    @Slot(result=str)
    def importAudio(self) -> str:
        if (g := self._guard()):
            return g
        files, _ = QFileDialog.getOpenFileNames(self.parent_widget, "Importar audio", str(Path.home()), AUDIO_FILTER)
        if not files:
            return json.dumps({"ok": False, "cancelled": True})
        return self.import_paths(files)

    def import_paths(self, files: list[str]) -> str:
        added, errors = [], []
        for f in files:
            try:
                added.append(self.host.add_audio(f))
            except Exception as exc:
                errors.append(f"{Path(f).name}: {exc}")
        if not added:
            return _err("; ".join(errors) or "Ningún archivo importado")
        return _ok(tracks=added, errors=errors)

    @Slot(result=str)
    def addTestTone(self) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(track=self.host.add_test_tone())
        except Exception as exc:
            return _err(f"Tono de prueba: {exc}")

    @Slot(int, result=str)
    def removeTrack(self, track_id: int) -> str:
        if (g := self._guard()):
            return g
        return _ok(removed=self.host.remove(int(track_id)))

    # --- exportación ------------------------------------------------------------------
    @Slot(result=str)
    def exportMix(self) -> str:
        if (g := self._guard()):
            return g
        if self.host.engine.length_seconds() <= 0:
            return _err("No hay audio en el motor para exportar (importa audio o añade el tono de prueba).")
        default = Path.home() / f"AllForOne_mezcla_{datetime.now():%Y%m%d_%H%M%S}.wav"
        path, _ = QFileDialog.getSaveFileName(self.parent_widget, "Exportar mezcla", str(default), "WAV (*.wav)")
        if not path:
            return json.dumps({"ok": False, "cancelled": True})
        return self.export_to(path)

    def export_to(self, path: str) -> str:
        if not path.lower().endswith(".wav"):
            path += ".wav"
        if not self.host.engine.render_to_wav(path):
            return _err("No se exportó nada: no hay pistas audibles en el motor (revisa mute/solo).")
        from ._native import afo_audio
        return _ok(path=path, measure=afo_audio.measure_file(path))

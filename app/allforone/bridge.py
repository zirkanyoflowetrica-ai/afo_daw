"""Objeto que la interfaz nativa (QML) ve como `afo`: sus métodos son slots de Qt.

QML dibuja; Python coordina; C++ procesa el audio. Por aquí solo viajan comandos, estados y
datos visuales compactos (picos de forma de onda, medidores), nunca bloques de audio.
Todas las respuestas son JSON: {"ok": bool, ...}.
"""
from __future__ import annotations

import functools
import json
import logging
import math
import queue
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QWidget

from . import audio_import, fx_presets, library, paths, project, themes
from .engine_host import EngineHost, fader_to_db
from .mixer_service import AUDIO_EXT, REF_LABEL, MixerService

log = logging.getLogger("allforone.bridge")
AUDIO_FILTER = "Audio (*.wav *.aif *.aiff *.flac *.ogg *.mp3);;Todos (*.*)"


def _clean(v):
    """JSON válido para JavaScript: sin NaN/Infinito ni tipos de NumPy."""
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            v = v.item()
        except Exception:
            return str(v)
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _json(obj) -> str:
    return json.dumps(_clean(obj), ensure_ascii=False)


def _ok(**kw) -> str:
    return _json({"ok": True, **kw})


def _err(msg: str, **kw) -> str:
    log.warning(msg)
    return _json({"ok": False, "error": msg, **kw})


def _safe(fn):
    """Un error de Python dentro de un slot vuelve a QML como {"ok": false} (con su traza en el
    registro) en vez de `undefined`, que rompía la interfaz al leer `r.ok`."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as exc:
            log.exception("Error en %s", fn.__name__)
            return _json({"ok": False, "error": f"Error interno en {fn.__name__}: {exc}"})
    return wrapper


def audio_files(items) -> list[str]:
    """Archivos de audio de una lista de rutas (las carpetas se exploran)."""
    out = []
    for it in items:
        p = Path(it)
        if p.is_dir():
            out += sorted(str(f) for f in p.rglob("*") if f.suffix.lower() in AUDIO_EXT)
        elif p.suffix.lower() in AUDIO_EXT and p.is_file():
            out.append(str(p))
    return out


class Bridge(QObject):
    stateChanged = Signal(str)
    pluginScanEvent = Signal(str)   # búsqueda de VST3 en otro proceso: avance y resultado
    mixerEvent = Signal(str)   # progreso y resultados del Mezclador V4.2 (desde su hilo de trabajo)
    aiEvent = Signal(str)      # IA local: avance de descargas de modelos y de generaciones

    def __init__(self, host: EngineHost, parent_widget: QWidget | None = None):
        super().__init__()
        self.host = host
        self.parent_widget = parent_widget
        self.hello_count = 0
        self.last_error: str | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 Hz para cursor y medidores
        self._timer.timeout.connect(self._tick)
        if host.ok:
            self._timer.start()
        # El mezclador trabaja en otro hilo: sus eventos se encolan y se emiten desde el hilo
        # principal (las señales que ve QML deben salir de su hilo).
        self._scanner = None
        self._mixer_events: queue.SimpleQueue = queue.SimpleQueue()
        self.mixsvc = MixerService(self._mixer_events.put)
        from .ai_music import AiMusic
        self.ai = AiMusic(self._mixer_events.put)
        from .stems import StemSeparator
        self.stems = StemSeparator(self._mixer_events.put)
        from .lab import Lab
        self.lab = Lab(self._mixer_events.put, lambda: self.ai.generating or self.stems.busy or self._midi_busy())
        self._lab_tracks: dict[str, dict] = {}     # familia → pista borrador del laboratorio {tid, vid, folder}
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.ai.shutdown)   # no dejar procesos del motor de IA huérfanos
            app.aboutToQuit.connect(self.stems.shutdown)
            app.aboutToQuit.connect(self.lab.shutdown)
            app.aboutToQuit.connect(self._midi_shutdown)
        self._midi = None
        self._mixer_timer = QTimer(self)
        self._mixer_timer.setInterval(50)
        self._mixer_timer.timeout.connect(self._drain_mixer_events)
        self._mixer_timer.start()
        self._auto: dict[int, list[int]] = {}   # pista (0 = master) -> efectos que puso la mezcla automática
        self._fx_labels: dict[int, str] = {}     # efecto -> nombre que le dio la mezcla automática
        self._live_plan: dict | None = None      # última decisión de la mezcla en vivo (bandas para el master)
        self._to_convert: list[str] = []    # audios que el motor no lee y hay que convertir
        self._converting: str | None = None
        from .automation_write import AutoWriter
        self._writer = AutoWriter(host.engine) if host.ok else None   # Read / Touch / Latch / Write

    def _drain_mixer_events(self) -> None:
        for _ in range(200):
            try:
                ev = self._mixer_events.get_nowait()
            except queue.Empty:
                return
            if ev.get("type") == "_converted":      # interno: la conversión terminó en su hilo
                self._finish_import(ev)
                continue
            if str(ev.get("type", "")).startswith(("ai", "stems", "lab")):   # IA local (ai_music.py, stems.py, lab.py)
                self.aiEvent.emit(_json(ev))
                continue
            if ev.get("type") == "_plan":           # interno: la mezcla decidida se aplica en el motor aquí
                self._apply_plan(ev["plan"])
                continue
            self.mixerEvent.emit(_json(ev))

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
    @_safe
    def hello(self) -> str:
        self.hello_count += 1
        return json.dumps(self.host.info())

    @Slot(str)
    def log(self, message: str) -> None:
        log.info("[JS] %s", message)

    # --- transporte -------------------------------------------------------------
    @Slot(result=str)
    @_safe
    def togglePlay(self) -> str:
        if (g := self._guard()):
            return g
        eng = self.host.engine
        if eng.is_playing():
            if self._writer:
                self._writer.finish(eng.position_seconds())   # cierra las pasadas de Latch / Write aquí
            eng.pause()
            return _ok(playing=False)
        dev = eng.device_info()
        if not dev.get("open"):
            return _err("No hay dispositivo de salida de audio abierto: el motor no puede reproducir. Revisa tu interfaz de audio.")
        eng.play()
        return _ok(playing=True)

    @Slot(result=str)
    @_safe
    def stop(self) -> str:
        if (g := self._guard()):
            return g
        eng = self.host.engine
        if self._writer and eng.is_playing():
            self._writer.finish(eng.position_seconds())       # antes de parar: stop lleva el cursor a 0
        eng.stop()
        return _ok()

    @Slot(float, result=str)
    @_safe
    def seek(self, seconds: float) -> str:
        """Lleva el cursor de reproducción a ese segundo (clic en la regla o en un carril de Pistas)."""
        if (g := self._guard()):
            return g
        self.host.engine.set_position_seconds(max(0.0, float(seconds)))
        return _ok()

    @Slot(float, result=str)
    @_safe
    def setTempo(self, bpm: float) -> str:
        if (g := self._guard()):
            return g
        self.host.engine.set_tempo(float(bpm))
        return _ok(bpm=self.host.engine.tempo())

    # --- mezcla ------------------------------------------------------------------
    @Slot(float, result=str)
    @_safe
    def setMasterVolume(self, pos: float) -> str:
        if (g := self._guard()):
            return g
        db = fader_to_db(pos)
        self.host.engine.set_master_gain_db(db)
        return _ok(db=db)

    @Slot(float, float, bool, result=str)
    @_safe
    def setMasterProcessing(self, drive: float, tone: float, limiter: bool) -> str:
        """Saturación, Tono y Limitador de «Mezcla final» (sección master del motor)."""
        if (g := self._guard()):
            return g
        self.host.engine.set_master_processing(float(drive), float(tone), bool(limiter))
        return _ok()

    @Slot(int, float, result=str)
    @_safe
    def setTrackVolume(self, track_id: int, pos: float) -> str:
        if (g := self._guard()):
            return g
        db = fader_to_db(pos)
        self.host.engine.set_track_gain_db(int(track_id), db)
        return _ok(db=db)

    @Slot(int, float, result=str)
    @_safe
    def setTrackPan(self, track_id: int, pan: float) -> str:
        if (g := self._guard()):
            return g
        self.host.engine.set_track_pan(int(track_id), float(pan))
        return _ok()

    @Slot(str, result=str)
    @_safe
    def setTrackStates(self, payload: str) -> str:
        if (g := self._guard()):
            return g
        for tid, mute, solo in json.loads(payload):
            self.host.engine.set_track_mute(int(tid), bool(mute))
            self.host.engine.set_track_solo(int(tid), bool(solo))
        return _ok()

    # --- tomas del grabador --------------------------------------------------------
    # --- configuración de audio (driver, dispositivo, frecuencia, búfer) ---------------------
    @Slot(str, result=str)
    @_safe
    def audioOptions(self, type_name: str) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(**self.host.audio_options(type_name))
        except Exception as exc:
            return _err(f"No se pudo leer el dispositivo: {exc}")

    @Slot(str, result=str)
    @_safe
    def setAudioDevice(self, payload: str) -> str:
        if (g := self._guard()):
            return g
        want = json.loads(payload)
        info = self.host.engine.device_info()
        if not info.get("open"):
            self.host.save_pending_device(want)
            log.info("Sin dispositivo abierto: %s queda para el próximo arranque", want)
            return _ok(pending=True, device=info)
        try:
            err = self.host.set_audio_device(want)
        except Exception as exc:
            return _err(f"No se pudo cambiar el dispositivo: {exc}")
        info = self.host.engine.device_info()
        log.info("Dispositivo de audio: %s", info)
        if err:
            return _err(err, device=info)
        return _ok(device=info)

    @Slot(result=str)
    @_safe
    def deviceStatus(self) -> str:
        """Lo que muestra la barra de estado: dispositivo y latencia de salida."""
        if not self.host.ok:
            return _err("Motor nativo no disponible")
        info = self.host.engine.device_info()
        lat = 0.0
        if info.get("open"):
            o = self.host.audio_options("")
            lat = float(o.get("output_latency_ms") or 0) + 1000.0 * info["buffer_size"] / max(1.0, info["sample_rate"])
        return _ok(device=info, latency_ms=lat)

    @Slot(result=str)
    @_safe
    def restartApp(self) -> str:
        """Cierra y vuelve a abrir AllForOne (para aplicar un dispositivo de audio pendiente)."""
        import sys
        from PySide6.QtCore import QCoreApplication, QProcess
        args = sys.argv[1:] if paths.is_frozen() else ["-m", "allforone", *sys.argv[1:]]
        if not QProcess.startDetached(sys.executable, args, str(Path.cwd())):
            return _err("No se pudo volver a abrir AllForOne: ábrelo tú")
        QTimer.singleShot(200, QCoreApplication.quit)
        return _ok()

    @Slot(result=str)
    @_safe
    def audioControlPanel(self) -> str:
        if (g := self._guard()):
            return g
        if not self.host.engine.show_audio_control_panel():
            return _err("Este driver no tiene panel propio (solo los ASIO, como ASIO4ALL)")
        return _ok(device=self.host.engine.device_info())

    # --- grabador de cintas: graba el motor (Tracktion), no la interfaz ---------------------
    @Slot(result=str)
    @_safe
    def recInputs(self) -> str:
        if (g := self._guard()):
            return g
        return _ok(inputs=self.host.engine.record_inputs())

    @Slot(str, result=str)
    @_safe
    def recCreate(self, name: str) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(track=self.host.add_record_track(name or "Voz"))
        except Exception as exc:
            return _err(f"No se pudo crear la pista de voz: {exc}")

    # --- buses Aux y envíos (como en una consola: una reverb compartida por envío) -------------
    @Slot(str, result=str)
    @_safe
    def auxCreate(self, name: str) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(track=self.host.add_aux(name or "Aux"))
        except Exception as exc:
            return _err(f"No se pudo crear el bus Aux: {exc}")

    @Slot(int, int, float, bool, result=str)
    @_safe
    def sendSet(self, track_id: int, aux_id: int, db: float, pre: bool) -> str:
        """Nivel del envío de una pista a un bus Aux (db <= -100 lo quita); pre = antes del fader."""
        if (g := self._guard()):
            return g
        self.host.engine.set_send(int(track_id), int(aux_id), float(db), bool(pre))
        return _ok(sends=self.host.engine.sends(int(track_id)))

    @Slot(int, result=str)
    @_safe
    def sendList(self, track_id: int) -> str:
        if (g := self._guard()):
            return g
        return _ok(sends=self.host.engine.sends(int(track_id)))

    @Slot(int, str, bool, result=str)
    @_safe
    def recArm(self, track_id: int, input_name: str, monitor: bool) -> str:
        if (g := self._guard()):
            return g
        if track_id < 0:
            self.host.engine.disarm()
            return _ok()
        err = self.host.engine.arm_track(track_id, input_name, monitor)
        return _err(err) if err else _ok(state=self.host._rec_state())

    @Slot(result=str)
    @_safe
    def recStart(self) -> str:
        if (g := self._guard()):
            return g
        err = self.host.engine.start_recording()
        return _err(err) if err else _ok()

    @Slot(bool, result=str)
    @_safe
    def recStop(self, discard: bool) -> str:
        if (g := self._guard()):
            return g
        try:
            info = self.host.finish_take(discard)
        except Exception as exc:
            return _err(f"No se pudo cerrar la toma: {exc}")
        if info["source_path"]:
            log.info("Toma grabada por el motor: %s (%.1f s)", info["source_path"], info["length_seconds"])
        return _ok(track=info)

    @Slot(int, result=str)
    @_safe
    def recListen(self, track_id: int) -> str:
        """Escuchar la toma de una pista de voz (o pararla si ya suena)."""
        if (g := self._guard()):
            return g
        eng = self.host.engine
        path = (self.host.tracks.get(track_id) or {}).get("source_path", "")
        if eng.preview_playing() and eng.preview_path() == path:
            eng.preview_stop()
            return _ok(playing=False)
        if not path:
            return _err("Esta pista no tiene audio grabado")
        if not eng.preview_play(path, 0.0):
            return _err("No se pudo abrir la toma")
        return _ok(playing=True)

    # --- efectos nativos (biblioteca AFO, Hito 1) -----------------------------------------
    @Slot(result=str)
    @_safe
    def fxCatalog(self) -> str:
        return _ok(catalog=self.host.effect_catalog())

    @Slot(int, str, int, result=str)
    @_safe
    def fxAdd(self, track_id: int, key: str, index: int) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(effect=self.host.engine.add_effect(track_id, key, index), chain=self._chain(track_id))
        except Exception as exc:
            return _err(f"No se pudo insertar el efecto: {exc}")

    def _chain(self, track_id: int) -> list[dict]:
        auto = set(self._auto.get(track_id, []))
        out = []
        for e in self.host.engine.effects(track_id):
            e = dict(e)
            e["label"] = self._fx_labels.get(e["id"], "") or e.get("name", "")
            e["auto"] = e["id"] in auto
            out.append(e)
        return out

    @Slot(int, result=str)
    @_safe
    def fxList(self, track_id: int) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(chain=self._chain(track_id))
        except Exception as exc:
            return _err(str(exc))

    @Slot(int, int, result=str)
    @_safe
    def fxRemove(self, effect_id: int, track_id: int) -> str:
        if (g := self._guard()):
            return g
        self.host.engine.remove_effect(effect_id)
        self._fx_labels.pop(effect_id, None)
        return _ok(chain=self._chain(track_id))

    @Slot(int, int, int, result=str)
    @_safe
    def fxMove(self, effect_id: int, index: int, track_id: int) -> str:
        if (g := self._guard()):
            return g
        self.host.engine.move_effect(effect_id, index)
        return _ok(chain=self._chain(track_id))

    @Slot(int, str, float, result=str)
    @_safe
    def fxParam(self, effect_id: int, param: str, value: float) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok() if self.host.engine.set_effect_param(effect_id, param, value) else _err(f"Parámetro desconocido: {param}")
        except Exception as exc:
            return _err(str(exc))

    @Slot(int, bool, result=str)
    @_safe
    def fxEnable(self, effect_id: int, enabled: bool) -> str:
        if (g := self._guard()):
            return g
        self.host.engine.set_effect_enabled(effect_id, enabled)
        return _ok()

    @Slot(int, result=str)
    @_safe
    def fxMeters(self, effect_id: int) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(m=[round(v, 1) for v in self.host.engine.effect_meters(effect_id)])
        except Exception as exc:
            return _err(str(exc))

    @Slot(float, result=str)
    @_safe
    def setMasterCeiling(self, db: float) -> str:
        """Techo del limitador del master (−6..0 dBFS); Master IA lo fija según el preset."""
        if (g := self._guard()):
            return g
        self.host.engine.set_master_ceiling(db)
        return _ok(ceiling=self.host.engine.master_ceiling())

    @Slot(int, int, result=str)
    @_safe
    def chainScope(self, track_id: int, bands: int) -> str:
        """Antes / después de la cadena de una pista (0 = master): espectro y nivel a la entrada del
        primer efecto activo y a la salida del último. Sin archivos: tomas del audio en curso."""
        if (g := self._guard()):
            return g
        try:
            d = dict(self.host.engine.chain_scope(track_id, max(8, min(256, bands))))
            d["pre"] = [round(v, 1) for v in d["pre"]]
            d["post"] = [round(v, 1) for v in d["post"]]
            return _ok(**d)
        except Exception as exc:
            return _err(str(exc))

    @Slot(int, int, result=str)
    @_safe
    def fxSpectrum(self, effect_id: int, bands: int) -> str:
        """Espectro del Analizador (AF-76): dB por banda logarítmica de 20 Hz a 20 kHz."""
        if (g := self._guard()):
            return g
        try:
            return _ok(bands=[round(v, 1) for v in self.host.engine.effect_spectrum(effect_id, max(8, min(256, bands)))])
        except Exception as exc:
            return _err(str(exc))

    # --- presets y automatización de efectos --------------------------------------
    def _fx_desc(self, key: str) -> dict:
        for d in self.host.effect_catalog():
            if d["key"] == key:
                return d
        raise KeyError(f"Efecto desconocido: {key}")

    @Slot(str, result=str)
    @_safe
    def fxPresets(self, key: str) -> str:
        try:
            return _ok(presets=fx_presets.listing(key))
        except Exception as exc:
            return _err(str(exc))

    @Slot(int, str, result=str)
    @_safe
    def fxApplyPreset(self, effect_id: int, name: str) -> str:
        """Pone todos los parámetros del efecto con los valores del preset (los que no nombra, por defecto)."""
        if (g := self._guard()):
            return g
        try:
            eng = self.host.engine
            key = eng.effect_info(effect_id)["key"]
            for pid, v in fx_presets.resolve(key, name, self._fx_desc(key)).items():
                eng.set_effect_param(effect_id, pid, v)
            return _ok(effect=eng.effect_info(effect_id))
        except Exception as exc:
            return _err(f"No se pudo aplicar el preset: {exc}")

    @Slot(int, str, result=str)
    @_safe
    def fxSavePreset(self, effect_id: int, name: str) -> str:
        if (g := self._guard()):
            return g
        try:
            info = self.host.engine.effect_info(effect_id)
            desc = self._fx_desc(info["key"])
            fx_presets.save(info["key"], name, {p["id"]: v for p, v in zip(desc["params"], info["values"])})
            return _ok(presets=fx_presets.listing(info["key"]))
        except Exception as exc:
            return _err(str(exc))

    @Slot(str, str, result=str)
    @_safe
    def fxDeletePreset(self, key: str, name: str) -> str:
        try:
            if not fx_presets.delete(key, name):
                return _err(f"«{name}» no es un preset del usuario")
            return _ok(presets=fx_presets.listing(key))
        except Exception as exc:
            return _err(str(exc))

    @Slot(int, str, result=str)
    @_safe
    def fxAutomation(self, effect_id: int, param: str) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(points=[[round(t, 4), v] for t, v in self.host.engine.effect_automation(effect_id, param)])
        except Exception as exc:
            return _err(str(exc))

    @Slot(int, str, str, result=str)
    @_safe
    def fxSetAutomation(self, effect_id: int, param: str, points_json: str) -> str:
        """Puntos [[segundos, valor], …] de la automatización de un parámetro; [] la quita."""
        if (g := self._guard()):
            return g
        try:
            pts = sorted((max(0.0, float(t)), float(v)) for t, v in json.loads(points_json or "[]"))
            if not self.host.engine.set_effect_automation(effect_id, param, pts):
                return _err(f"Parámetro desconocido: {param}")
            return _ok(effect=self.host.engine.effect_info(effect_id))
        except Exception as exc:
            return _err(f"No se pudo guardar la automatización: {exc}")

    # --- escritura de automatización en vivo (automation_write.py) -------------------------
    @Slot(int, str, result=str)
    @_safe
    def autoMode(self, track_id: int, mode: str) -> str:
        """Modo de automatización de la pista: read | touch | latch | write."""
        if (g := self._guard()):
            return g
        try:
            return _ok(mode=self._writer.set_mode(int(track_id), mode))
        except ValueError as exc:
            return _err(str(exc))

    @Slot(result=str)
    @_safe
    def autoModes(self) -> str:
        if (g := self._guard()):
            return g
        return _ok(modes={str(k): v for k, v in self._writer.modes.items()})

    @Slot(str, int, str, float, str, result=str)
    @_safe
    def autoTouch(self, kind: str, target_id: int, param: str, value: float, phase: str) -> str:
        """Un control se mueve (phase start | move | end). kind "fx" (perilla de un efecto) o "track"
        (param volume en dB, pan -1..1). writing=False: la interfaz aplica el valor fijo como siempre."""
        if (g := self._guard()):
            return g
        if kind not in ("fx", "track"):
            return _err(f"Destino desconocido: {kind}")
        return _ok(writing=self._writer.touch((kind, int(target_id), param), float(value), phase))

    @Slot(int, str, str, result=str)
    @_safe
    def trackAutoSet(self, track_id: int, param: str, points_json: str) -> str:
        """Curva del fader ("volume", dB) o del paneo ("pan") de una pista; [] la quita."""
        if (g := self._guard()):
            return g
        pts = sorted((max(0.0, float(t)), float(v)) for t, v in json.loads(points_json or "[]"))
        if not self.host.engine.set_track_automation(int(track_id), param, pts):
            return _err(f"Parámetro de pista desconocido: {param}")
        return _ok(points=[[round(t, 4), v] for t, v in self.host.engine.track_automation(int(track_id), param)])

    @Slot(int, result=str)
    @_safe
    def fxInfo(self, effect_id: int) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(effect=self.host.engine.effect_info(effect_id))
        except Exception as exc:
            return _err(str(exc))

    @Slot(str, result=str)
    @_safe
    def dawLanes(self, ids_json: str) -> str:
        """Vista Arreglo: por pista (0 = master) su cadena de inserts y las curvas de automatización
        de cada parámetro automatizado, con nombre, unidad y rango del catálogo. Una llamada por refresco."""
        if (g := self._guard()):
            return g
        eng = self.host.engine
        cat = {c["key"]: c for c in self.host.effect_catalog()}
        out = {}
        for tid in [int(i) for i in json.loads(ids_json or "[]")]:
            try:
                chain = self._chain(tid)
            except Exception:
                continue
            inserts, lanes = [], []
            for e in chain:
                desc = cat.get(e["key"], {})
                params = desc.get("params", [])
                autom = list(e.get("automated", []))
                label = e["label"] or desc.get("name") or e["key"]          # añadido a mano: nombre del catálogo
                inserts.append({"id": e["id"], "key": e["key"], "label": label, "enabled": bool(e["enabled"]),
                                "auto": e["auto"], "automated": len(autom)})
                for pid in autom:
                    pts = eng.effect_automation(e["id"], pid)
                    if not pts:
                        continue
                    p = next((q for q in params if q["id"] == pid), {})
                    lanes.append({"effect": e["id"], "fx": label, "param": pid, "name": p.get("name", pid),
                                  "unit": p.get("unit", ""), "min": p.get("min", 0.0), "max": p.get("max", 1.0), "centre": p.get("centre"),
                                  "points": [[round(t, 3), round(v, 4)] for t, v in pts]})
            try:
                sends = eng.sends(tid) if tid > 0 else []
            except Exception:
                sends = []
            mode = self._writer.mode(tid) if self._writer and tid > 0 else "read"
            if tid > 0:
                for pid, nm, unit, lo, hi, ctr in (("pan", "Paneo", "", -1.0, 1.0, 0.0), ("volume", "Volumen", "dB", -60.0, 12.0, None)):
                    try:
                        pts = eng.track_automation(tid, pid)
                    except Exception:
                        pts = []
                    if pts or (pid == "volume" and mode != "read"):     # fuera de Read: carril de volumen listo
                        lanes.insert(0, {"effect": 0, "track": tid, "fx": "Pista", "param": pid, "name": nm, "unit": unit,
                                         "min": lo, "max": hi, "centre": ctr,
                                         "points": [[round(t, 3), round(v, 4)] for t, v in pts]})
            out[str(tid)] = {"inserts": inserts, "lanes": lanes, "sends": sends, "mode": mode}
        return _ok(tracks=out)

    @Slot(int, str, result=str)
    @_safe
    def fxRestore(self, track_id: int, chain_json: str) -> str:
        """Sustituye la cadena de efectos de una pista por una guardada (al abrir un proyecto)."""
        if (g := self._guard()):
            return g
        try:
            for old in self._auto.pop(track_id, []):
                self._fx_labels.pop(old, None)

            def added(eid, fx):
                if fx.get("label"):
                    self._fx_labels[eid] = fx["label"]
                if fx.get("auto"):
                    self._auto.setdefault(track_id, []).append(eid)
            warn = project.restore_chain(self.host.engine, self.host.effect_catalog(), track_id, json.loads(chain_json or "[]"), added)
            return _ok(chain=self._chain(track_id), warnings=warn)
        except Exception as exc:
            return _err(f"No se pudo recuperar la cadena de efectos: {exc}")

    # --- temas (carpeta templates/ del programa) ----------------------------------------
    @Slot(result=str)
    @_safe
    def themeList(self) -> str:
        """Temas: cada carpeta de templates/ con un theme.json (copiar la carpeta = compartir el tema)."""
        return _ok(themes=themes.list_themes(), folder=str(themes.folder()))

    @Slot(str, result=str)
    @_safe
    def themeLoad(self, name: str) -> str:
        try:
            return _ok(theme=themes.load(name))
        except Exception as exc:
            return _err(f"No se pudo cargar el tema «{name}»: {exc}")

    @Slot(result=str)
    @_safe
    def themeFolder(self) -> str:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(themes.folder())))
        return _ok(folder=str(themes.folder()))

    # --- versiones de master (Rebobinado) ----------------------------------------------
    @Slot(bool, result=str)
    @_safe
    def masterSnapshot(self, measure: bool) -> str:
        """Cadena del master tal como suena ahora (valores, plugins, automatización) y su techo; con
        `measure`, también su sonoridad procesando la sesión en memoria."""
        if (g := self._guard()):
            return g
        try:
            eng = self.host.engine
            chain = project.chain_of(eng, self.host.effect_catalog(), project.MASTER, self._fx_labels, self._auto.get(project.MASTER, ()))
            out = {"chain": chain, "ceiling": round(eng.master_ceiling(), 2)}
            if measure:
                if eng.is_playing():
                    eng.pause()
                m = eng.measure_mix()
                if m["ok"]:
                    out["lufs"] = round(m["master"]["lufs_i"], 1)
                    out["peak"] = round(m["master"]["max_peak_db"], 1)
            return _ok(**out)
        except Exception as exc:
            return _err(f"No se pudo leer el master: {exc}")

    @Slot(str, result=str)
    @_safe
    def masterLoad(self, version_json: str) -> str:
        """Pone en el master una versión guardada (su cadena y su techo)."""
        if (g := self._guard()):
            return g
        try:
            v = json.loads(version_json)
            r = json.loads(self.fxRestore(project.MASTER, json.dumps(v.get("chain") or [])))
            if r.get("ok") and v.get("ceiling") is not None:
                self.host.engine.set_master_ceiling(float(v["ceiling"]))
            return json.dumps(r)
        except Exception as exc:
            return _err(f"No se pudo cargar la versión: {exc}")

    # --- proyecto -----------------------------------------------------------------
    def _project_dir(self) -> str:
        p = paths.user_data_dir() / "proyectos"
        p.mkdir(parents=True, exist_ok=True)
        return str(p)

    # --- edición de clips de audio (Pistas) -------------------------------------------
    @Slot(int, result=str)
    @_safe
    def clipList(self, track_id: int) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(clips=self.host.engine.clips(int(track_id)))
        except Exception as exc:
            return _err(f"No se pudieron leer los clips: {exc}")

    @Slot(int, str, result=str)
    @_safe
    def aiRepaint(self, track_id: int, payload: str) -> str:
        """Rehace con IA una zona de una pista de audio: {start, end} en segundos DEL ARCHIVO (la
        interfaz los saca del clip elegido), prompt y estilo opcionales. Llega por `aiEvent`."""
        if (g := self._guard()):
            return g
        t = self.host.tracks.get(int(track_id)) or {}
        src = t.get("originalPath") or t.get("source_path") or ""
        if not src or not Path(src).is_file():
            return _err("Elige un clip de una pista de audio")
        if self.lab.busy or self.stems.busy or self._midi_busy():
            return _err("Otro trabajo de IA está en marcha: espera a que termine.")
        opts = {**json.loads(payload or "{}"), "trackId": int(track_id)}
        try:
            import soundfile as sf
            return _ok(**self.ai.repaint(opts, Path(src), float(sf.info(src).duration)))
        except Exception as exc:
            return _err(str(exc))

    @Slot(int, str, result=str)
    @_safe
    def aiCover(self, track_id: int, payload: str) -> str:
        """Otra versión con IA (C13) de un trozo de una pista de audio: {start, end} en segundos DEL
        ARCHIVO, `at` (segundo del proyecto donde poner el resultado), mode Parecida / Libre,
        likeness 0–1, estilo y prompt opcionales. Llega por `aiEvent` con `cover` y va a una pista nueva."""
        if (g := self._guard()):
            return g
        t = self.host.tracks.get(int(track_id)) or {}
        src = t.get("originalPath") or t.get("source_path") or ""
        if not src or not Path(src).is_file():
            return _err("Elige un clip de una pista de audio")
        if self.lab.busy or self.stems.busy or self._midi_busy():
            return _err("Otro trabajo de IA está en marcha: espera a que termine.")
        opts = {**json.loads(payload or "{}"), "trackId": int(track_id)}
        try:
            return _ok(**self.ai.cover(opts, Path(src), float(opts.get("start", 0)), float(opts.get("end", 0))))
        except Exception as exc:
            return _err(str(exc))

    def _set_source(self, track_id: int, path: str) -> dict:
        """Cambia el archivo de una pista conservando sus clips (posición, recorte, ganancia, fundidos)."""
        eng = self.host.engine
        clips = eng.clips(track_id)
        info = dict(eng.set_track_audio(track_id, path, 0.0))
        eng.set_clips(track_id, clips)
        info = next((x for x in eng.tracks() if x["id"] == track_id), info)
        info = dict(info)
        info["peaks"] = [round(v, 4) for v in eng.track_peaks(track_id, 600)]
        self.host.tracks[track_id] = {**self.host.tracks.get(track_id, {}), **info, "originalPath": path}
        return info

    @Slot(int, str, result=str)
    @_safe
    def trackSetSource(self, track_id: int, path: str) -> str:
        """Pone otro archivo en la pista sin tocar sus clips (rehacer con IA y su deshacer)."""
        if (g := self._guard()):
            return g
        if not Path(path).is_file():
            return _err(f"No se encuentra {Path(path).name}")
        prev = (self.host.tracks.get(int(track_id)) or {}).get("originalPath", "")
        try:
            info = self._set_source(int(track_id), path)
        except Exception as exc:
            return _err(f"No se pudo cambiar el audio de la pista: {exc}")
        return _ok(track=info, clips=self.host.engine.clips(int(track_id)), previous=prev)

    @Slot(int, str, result=str)
    @_safe
    def clipEdit(self, track_id: int, op_json: str) -> str:
        """Una edición de clip: range (mover/recortar), split, dup, remove, gain, fades, normalize o set
        (sustituir todos: deshacer y abrir proyecto). Devuelve los clips de la pista y su duración."""
        if (g := self._guard()):
            return g
        eng = self.host.engine
        try:
            op = json.loads(op_json)
            kind = op.get("op")
            cid = int(op.get("clip", 0))
            if kind == "range":
                eng.set_clip_range(cid, float(op["start"]), float(op["length"]), float(op["offset"]))
            elif kind == "split":
                eng.split_clip(cid, float(op["at"]))
            elif kind == "dup":
                eng.duplicate_clip(cid)
            elif kind == "remove":
                eng.remove_clip(cid)
            elif kind == "gain":
                eng.set_clip_gain(cid, float(op["db"]))
            elif kind == "fades":
                eng.set_clip_fades(cid, float(op["in"]), float(op["out"]))
            elif kind == "normalize":           # pico del trozo a op["target"] dBFS (−1 por defecto)
                peak = eng.clip_peak_db(cid)
                if peak <= -99:
                    return _err("El clip está en silencio: no se puede normalizar")
                eng.set_clip_gain(cid, float(op.get("target", -1.0)) - peak)
            elif kind == "set":
                src = op.get("source") or ""           # deshacer un «Rehacer con IA»: vuelve el archivo anterior
                if src and src != (self.host.tracks.get(int(track_id)) or {}).get("originalPath"):
                    if not Path(src).is_file():
                        return _err(f"No se encuentra {Path(src).name}")
                    self._set_source(int(track_id), src)
                eng.set_clips(int(track_id), op["clips"])
            else:
                return _err(f"Edición desconocida: {kind}")
            info = next((t for t in eng.tracks() if t["id"] == int(track_id)), {})
            extra = {}
            if kind == "set" and op.get("source"):
                extra = {"peaks": self.host.tracks[int(track_id)].get("peaks", []),
                         "source": self.host.tracks[int(track_id)].get("originalPath", "")}
            return _ok(clips=eng.clips(int(track_id)), start=info.get("start_seconds", 0.0),
                       length=info.get("length_seconds", 0.0), **extra)
        except Exception as exc:
            return _err(f"No se pudo editar el clip: {exc}")

    @Slot(str, str, result=str)
    @_safe
    def projectSave(self, doc_json: str, path: str) -> str:
        """Guarda la sesión. `path` vacío = elegir archivo; la interfaz recuerda el último."""
        if (g := self._guard()):
            return g
        if not path:
            path, _ = QFileDialog.getSaveFileName(self.parent_widget, "Guardar proyecto",
                                                  str(Path(self._project_dir()) / "Proyecto.afo"),
                                                  "Proyecto AllForOne (*.afo)")
            if not path:
                return _err("", cancelled=True)
        try:
            eng = self.host.engine
            sources = {t["id"]: t.get("source_path", "") for t in eng.tracks()}
            sources.update({tid: info.get("originalPath") or sources.get(tid, "") for tid, info in self.host.tracks.items()})
            doc = project.collect(json.loads(doc_json), eng, self.host.effect_catalog(), sources, self._fx_labels, self._auto,
                                  self._writer.modes if self._writer else None)
            out = project.save(path, doc)
            library.touch(str(out))
            return _ok(path=str(out), name=out.stem, where=library.where(str(out)))
        except Exception as exc:
            return _err(f"No se pudo guardar el proyecto: {exc}")

    @Slot(str, result=str)
    @_safe
    def projectOpen(self, path: str) -> str:
        """Lee un proyecto; la interfaz recrea la sesión con él (ver qml/state/Project.qml)."""
        if not path:
            path, _ = QFileDialog.getOpenFileName(self.parent_widget, "Abrir proyecto", self._project_dir(),
                                                  "Proyecto AllForOne (*.afo)")
            if not path:
                return _err("", cancelled=True)
        try:
            doc = project.load(path)
            library.touch(path)
            return _ok(doc=doc, path=doc["file"], name=Path(path).stem, where=library.where(path))
        except Exception as exc:
            return _err(f"No se pudo abrir el proyecto: {exc}")

    # --- biblioteca (Artista → Lanzamiento → Canción) ---------------------------------
    @Slot(result=str)
    @_safe
    def libraryTree(self) -> str:
        return _ok(tree=library.tree(), root=str(library.root()))

    @Slot(str, str, str, str, result=str)
    @_safe
    def libraryCreate(self, kind: str, parent_path: str, name: str, extra_json: str) -> str:
        try:
            return _ok(item=library.create(kind, parent_path, name, json.loads(extra_json or "{}")))
        except ValueError as exc:
            return _err(str(exc))

    @Slot(str, str, result=str)
    @_safe
    def libraryRename(self, path: str, name: str) -> str:
        try:
            return _ok(item=library.rename(path, name))
        except ValueError as exc:
            return _err(str(exc))

    @Slot(str, result=str)
    @_safe
    def libraryRemove(self, path: str) -> str:
        try:
            return _ok(**library.remove(path))
        except ValueError as exc:
            return _err(str(exc))

    @Slot(result=str)
    @_safe
    def libraryRecent(self) -> str:
        return _ok(recent=library.recent())

    @Slot(str, str, result=str)
    @_safe
    def addAudioPath(self, path: str, name: str) -> str:
        """Pista de audio desde una ruta conocida (al abrir un proyecto), sin diálogo."""
        if (g := self._guard()):
            return g
        try:
            return _ok(track=self.host.add_audio(path, name))
        except Exception as exc:
            return _err(f"No se pudo cargar {Path(path).name}: {exc}")

    @Slot(int, str, float, result=str)
    @_safe
    def setTrackAudio(self, track_id: int, path: str, start: float) -> str:
        """Pone una toma guardada en una pista de voz."""
        if (g := self._guard()):
            return g
        try:
            info = dict(self.host.engine.set_track_audio(track_id, path, start))
            info["peaks"] = [round(v, 4) for v in self.host.engine.track_peaks(track_id, 600)]
            self.host.tracks[track_id] = {**info, "originalPath": path, "note": ""}
            return _ok(track=info)
        except Exception as exc:
            return _err(f"No se pudo cargar la toma {Path(path).name}: {exc}")

    # --- pistas -------------------------------------------------------------------
    @Slot(result=str)
    @_safe
    def importAudio(self) -> str:
        if (g := self._guard()):
            return g
        files, _ = QFileDialog.getOpenFileNames(self.parent_widget, "Importar audio", str(Path.home()), AUDIO_FILTER)
        if not files:
            return json.dumps({"ok": False, "cancelled": True})
        return self.import_paths(files)

    @Slot(str, result=str)
    @_safe
    def importPaths(self, payload: str) -> str:
        """Importa a Pistas archivos soltados desde el Explorador."""
        if (g := self._guard()):
            return g
        files = audio_files(json.loads(payload))
        if not files:
            return _err("Ningún archivo de audio compatible (WAV, AIFF, FLAC, OGG, MP3).")
        return self.import_paths(files)

    def import_paths(self, files: list[str]) -> str:
        """Importa en varios pasos para no congelar la ventana.

        Lo que el motor lee directamente entra al momento. Lo que no (p. ej. WAV en coma
        flotante de 64 bits, de cientos de MB) se convierte en un hilo aparte y la pista se
        crea al volver al hilo principal. Cada archivo avisa por `mixerEvent`.
        """
        added, errors, pending = [], [], []
        for f in files:
            try:
                added.append(self.host.add_audio(f, convert=False))
            except Exception as exc:
                pending.append((f, str(exc)))
        for f, _why in pending:
            self._to_convert.append(f)
        self._pump_convert()
        if not added and not pending:
            return _err("; ".join(errors) or "Ningún archivo importado")
        return _ok(tracks=added, errors=errors, converting=[Path(f).name for f, _ in pending])

    # --- conversión de formatos que el motor no lee (en segundo plano) -----------------
    def _pump_convert(self) -> None:
        if self._converting or not self._to_convert:
            return
        src = self._converting = self._to_convert.pop(0)
        self._mixer_events.put({"type": "import", "phase": "convert", "name": Path(src).name,
                                "left": len(self._to_convert),
                                "desc": f"Convirtiendo {Path(src).name} para el motor…"})

        def work():
            try:
                readable, note = audio_import.to_engine_wav(src)
                self._mixer_events.put({"type": "_converted", "src": src, "use": str(readable), "note": note})
            except Exception as exc:
                self._mixer_events.put({"type": "_converted", "src": src, "error": str(exc)})

        threading.Thread(target=work, name="afo-convert", daemon=True).start()

    def _finish_import(self, ev: dict) -> None:
        """Hilo principal: ya hay un archivo legible, se crea la pista."""
        self._converting = None
        src = ev["src"]
        if ev.get("error"):
            self._mixer_events.put({"type": "import", "phase": "error", "name": Path(src).name,
                                    "error": f"{Path(src).name}: {ev['error']}"})
        else:
            try:
                info = self.host.add_prepared(src, ev["use"], ev.get("note", ""))
                self._mixer_events.put({"type": "import", "phase": "track", "track": _clean(info)})
            except Exception as exc:
                self._mixer_events.put({"type": "import", "phase": "error", "name": Path(src).name,
                                        "error": f"{Path(src).name}: {exc}"})
        self._pump_convert()

    # --- Instrumento y Batería: sintetizador del motor (clip MIDI + plugin) --------------
    @Slot(str, int, result=str)
    @_safe
    def synthCreate(self, name: str, mode: int) -> str:
        """Pista nueva con el sintetizador del motor (mode 0 = instrumento, 1 = batería)."""
        if (g := self._guard()):
            return g
        return _ok(track=self.host.add_synth(name, int(mode)))

    @Slot(int, str, result=str)
    @_safe
    def synthUpdate(self, track_id: int, payload: str) -> str:
        """Parámetros y patrón de la pista: {type, cfg, clips, roll | pat, sus}. Inmediato (sin renderizar)."""
        if (g := self._guard()):
            return g
        try:
            data = json.loads(payload)
            cfg = data.get("cfg") or {}
            if data.get("type") == "inst":      # instrumento VST3 elegido para la pista (o el del motor)
                want = cfg.get("plugin") or ""
                if self.host.engine.track_instrument(int(track_id)) != want:
                    self.host.engine.set_track_instrument(int(track_id), want, cfg.get("pluginState") or "")
            length = self.host.update_synth(int(track_id), data)
            missing = self.host.drum_samples(int(track_id), data) if data.get("type") == "drum" else []
            if missing:
                return _ok(length=length, warning=f"No se encuentra {Path(missing[0]).name}: ese pad vuelve al sonido sintetizado")
            return _ok(length=length)
        except Exception as exc:
            return _err(f"Sintetizador: {exc}")

    # --- IA local: instrumentales con ACE-Step (ai_music.py) ------------------------
    @Slot(result=str)
    @_safe
    def aiStatus(self) -> str:
        """Motor, modelos instalados, tarjeta gráfica y generaciones guardadas."""
        from .ai_music import list_generations
        return _ok(**self.ai.status(), generations=list_generations())

    @Slot(result=str)
    @_safe
    def hardwareStatus(self) -> str:
        """Equipo detectado (gráfica, RAM, hilos) y perfil de IA en uso (hardware.py)."""
        from . import hardware
        return _ok(**hardware.status())

    @Slot(str, result=str)
    @_safe
    def hardwareSetProfile(self, name: str) -> str:
        """Fija el perfil («auto», «alto», «medio», «bajo», «cpu»); se guarda en equipo.json."""
        from . import hardware
        if self.ai.generating or self.lab.busy or self.stems.busy:
            return _err("Espera a que termine el trabajo de IA para cambiar el perfil")
        hardware.set_override(name)
        return _ok(**hardware.status())

    @Slot(str, result=str)
    @_safe
    def aiDownload(self, pack: str) -> str:
        """Descarga (o reanuda) los modelos de un paquete; el avance llega por `aiEvent`."""
        try:
            self.ai.download(pack)
        except Exception as exc:
            return _err(str(exc))
        return _ok(started=True)

    @Slot(result=str)
    @_safe
    def aiCancelDownload(self) -> str:
        self.ai.cancel_download()
        return _ok()

    @Slot(str, result=str)
    @_safe
    def aiGenerate(self, payload: str) -> str:
        """Genera una instrumental en otro proceso; el WAV llega por `aiEvent` y se carga con addAudioPath."""
        if self.lab.busy:
            return _err("El laboratorio está generando: espera a que termine.")
        try:
            return _ok(**self.ai.generate(json.loads(payload or "{}")))
        except Exception as exc:
            return _err(str(exc))

    @Slot(str, result=str)
    @_safe
    def aiPart(self, payload: str) -> str:
        """Genera una parte (guitarra, piano…) acorde al proyecto: renderiza lo que suena ahora a un
        WAV y ACE-Step (modelo base, tarea «lego») escribe la parte nueva encima, con tempo y tono."""
        from .ai_music import output_dir
        opts = json.loads(payload or "{}")
        if self.ai.generating:
            return _err("Ya se está generando una pista.")
        if self.lab.busy:
            return _err("El laboratorio está generando: espera a que termine.")
        eng = self.host.engine
        if eng is None:
            return _err("Motor de audio no disponible")
        if not [t for t in self.host.tracks if t != 0]:
            return _err("El proyecto está vacío: la parte se genera sobre lo que ya suena.")
        src = output_dir() / ".contexto_parte.wav"
        src.parent.mkdir(parents=True, exist_ok=True)
        if not eng.render_to_wav(str(src)):
            return _err("No se pudo escuchar el proyecto (render)")
        import soundfile as sf
        secs = sf.info(str(src)).duration
        opts["duration"] = min(240.0, max(5.0, secs))
        try:
            return _ok(**self.ai.generate_part(opts, src), seconds=round(secs, 1))
        except Exception as exc:
            return _err(str(exc))

    @Slot(result=str)
    @_safe
    def aiCancel(self) -> str:
        self.ai.cancel()
        return _ok()

    # --- IA local: separador de stems con Demucs (stems.py) ------------------------------
    @Slot(result=str)
    @_safe
    def stemsStatus(self) -> str:
        return _ok(**self.stems.status())

    @Slot(result=str)
    @_safe
    def stemsDownload(self) -> str:
        """Descarga (o reanuda) el modelo de Demucs (55 MB); el avance llega por `aiEvent`."""
        self.stems.download()
        return _ok(started=True)

    @Slot(int, bool, result=str)
    @_safe
    def stemsSplit(self, track_id: int, drums: bool) -> str:
        """Separa el audio de una pista en Batería, Bajo, Voz, Guitarra, Piano y Otros (y la batería
        en Bombo, Caja / Clap y Platos si `drums`). Las pistas llegan por `aiEvent` (type "stems")."""
        t = self.host.tracks.get(track_id)
        if not t:
            return _err("Elige una pista de audio")
        if self.lab.busy:
            return _err("El laboratorio está generando: espera a que termine.")
        try:
            return _ok(**self.stems.split(t.get("source_path") or "", t.get("name") or "Pista", track_id, drums))
        except Exception as exc:
            return _err(str(exc))

    @Slot(result=str)
    @_safe
    def stemsCancel(self) -> str:
        self.stems.cancel()
        return _ok()

    # --- Instrumental Lab (lab.py, docs/INSTRUMENTAL_LAB.md) -----------------------------
    # El estado completo llega también por `aiEvent` (type "labState"); el avance, con type "labJob".
    def _lab(self, fn, *args) -> str:
        try:
            r = fn(*args)
        except Exception as exc:
            return _err(str(exc))
        return _ok(state=self.lab.public(), **(r if isinstance(r, dict) and "families" not in r else {}))

    @Slot(result=str)
    @_safe
    def labStatus(self) -> str:
        return _ok(**self.lab.status(), state=self.lab.public())

    @Slot(result=str)
    @_safe
    def labSessions(self) -> str:
        return _ok(sessions=self.lab.sessions(), favorites=self.lab.favorites())

    @Slot(str, result=str)
    @_safe
    def labNew(self, payload: str) -> str:
        """Sesión nueva: {prompt, style, bpm, key, beats, bars, variants, families, name}."""
        return self._lab(self.lab.new, json.loads(payload or "{}"))

    @Slot(str, result=str)
    @_safe
    def labOpen(self, folder: str) -> str:
        return self._lab(self.lab.open, folder)

    @Slot(result=str)
    @_safe
    def labGuideText(self) -> str:
        """Guía compuesta por ACE-Step con el contexto; Demucs la separa en las V1."""
        return self._lab(self.lab.guide_text)

    @Slot(result=str)
    @_safe
    def labGuideProject(self) -> str:
        """Guía = lo que suena ahora en el proyecto (render); Demucs la separa en las V1."""
        eng = self.host.engine
        if eng is None:
            return _err("Motor de audio no disponible")
        if self.lab.folder is None:
            return _err("Abre o crea una sesión del laboratorio")
        if not [t for t in self.host.tracks if t != 0]:
            return _err("El proyecto está vacío")
        src = self.lab.folder / "proyecto.wav"
        if not eng.render_to_wav(str(src)):
            return _err("No se pudo escuchar el proyecto (render)")
        return self._lab(self.lab.guide_audio, str(src))

    @Slot(str, result=str)
    @_safe
    def labGuideFile(self, path: str) -> str:
        return self._lab(self.lab.guide_audio, path)

    @Slot(str, int, result=str)
    @_safe
    def labGenerate(self, family: str, n: int) -> str:
        """`n` variantes nuevas de una familia (0 = hasta completar las del contexto)."""
        return self._lab(self.lab.generate, family, n)

    @Slot(str, result=str)
    @_safe
    def labRegenerate(self, family: str) -> str:
        return self._lab(self.lab.regenerate, family)

    @Slot(str, str, float, result=str)
    @_safe
    def labSimilar(self, family: str, vid: str, strength: float) -> str:
        return self._lab(self.lab.similar, family, vid, strength)

    @Slot(str, str, str, bool, result=str)
    @_safe
    def labSet(self, family: str, vid: str, field: str, value: bool) -> str:
        """Elegir, bloquear o marcar como favorita una variante (field: chosen, locked, favorite)."""
        return self._lab(self.lab.set_flag, family, vid, field, value)

    @Slot(str, bool, result=str)
    @_safe
    def labReference(self, family: str, value: bool) -> str:
        return self._lab(self.lab.set_reference, family, value)

    @Slot(str, result=str)
    @_safe
    def labAddFamily(self, family: str) -> str:
        return self._lab(self.lab.add_family, family)

    @Slot(str, str, result=str)
    @_safe
    def labRemove(self, family: str, vid: str) -> str:
        return self._lab(self.lab.remove, family, vid)

    # Preescucha con pistas reales (C9): una pista «Lab (borrador)» por familia con su variante elegida,
    # desde el compás 1. Cambiar de variante cambia el audio de la misma pista (no se crea otra).
    def _drafts(self) -> dict[str, dict]:
        folder = str(self.lab.folder or "")
        live = {f: d for f, d in self._lab_tracks.items() if d["tid"] in self.host.tracks and d["folder"] == folder}
        stale = [d["tid"] for f, d in self._lab_tracks.items() if f not in live and d["tid"] in self.host.tracks]
        self._lab_tracks = live
        return {"live": live, "stale": stale}

    @Slot(result=str)
    @_safe
    def labPreview(self) -> str:
        """Crea o actualiza las pistas borrador. Devuelve qué pistas se crearon (la interfaz las añade),
        cuáles cambiaron de audio y cuáles sobran (`stale`: de otra sesión o de una familia vacía)."""
        if (g := self._guard()):
            return g
        d = self._drafts()
        live, out = d["live"], []
        want = {c["family"]: c for c in self.lab.chosen()}
        stale = d["stale"] + [x["tid"] for f, x in live.items() if f not in want]
        for f in [f for f in live if f not in want]:
            self._lab_tracks.pop(f)
        try:
            for fam, c in want.items():
                cur = self._lab_tracks.get(fam)
                if cur and cur["vid"] == c["id"]:
                    out.append({"family": fam, "id": cur["tid"], "vid": c["id"], "change": "same"})
                    continue
                if cur:
                    info = dict(self.host.engine.set_track_audio(cur["tid"], c["path"], 0.0))
                    info["peaks"] = [round(v, 4) for v in self.host.engine.track_peaks(cur["tid"], 600)]
                    self.host.tracks[cur["tid"]] = {**info, "originalPath": c["path"], "note": ""}
                    cur["vid"] = c["id"]
                    out.append({"family": fam, "id": cur["tid"], "vid": c["id"], "change": "audio", "track": info})
                else:
                    info = self.host.add_audio(c["path"], f"{fam} · Lab (borrador)")
                    self._lab_tracks[fam] = {"tid": info["id"], "vid": c["id"], "folder": str(self.lab.folder)}
                    out.append({"family": fam, "id": info["id"], "vid": c["id"], "change": "new", "track": info})
        except Exception as exc:
            return _err(f"No se pudo preparar la preescucha: {exc}")
        return _ok(tracks=out, stale=stale, bpm=(self.lab.state or {}).get("context", {}).get("bpm"))

    @Slot(result=str)
    @_safe
    def labSend(self) -> str:
        """Las pistas borrador pasan al proyecto: su audio se copia a `enviadas/` (así no depende de
        regenerar o tirar variantes) y dejan de ser borrador. La interfaz les quita la marca."""
        if (g := self._guard()):
            return g
        live, out = self._drafts()["live"], []
        try:
            for fam, d in live.items():
                path = str(self.lab.send_copy(fam, d["vid"]))
                info = dict(self.host.engine.set_track_audio(d["tid"], path, 0.0))
                info["peaks"] = [round(v, 4) for v in self.host.engine.track_peaks(d["tid"], 600)]
                self.host.tracks[d["tid"]] = {**info, "originalPath": path, "note": ""}
                out.append({"family": fam, "id": d["tid"], "track": info, "name": f"{fam} (Lab)"})
        except Exception as exc:
            return _err(f"No se pudo enviar al proyecto: {exc}")
        self._lab_tracks = {}
        return _ok(tracks=out)

    @Slot(result=str)
    @_safe
    def labDiscard(self) -> str:
        """Ids de las pistas borrador para que la interfaz las quite (con su canal)."""
        d = self._drafts()
        ids = [x["tid"] for x in d["live"].values()] + d["stale"]
        self._lab_tracks = {}
        return _ok(ids=ids)

    @Slot(result=str)
    @_safe
    def labHitLanes(self) -> str:
        """Rutas de los golpes sueltos por carril de la Batería (para el sampler de los pads)."""
        lanes = self.lab.hit_lanes()
        if not any(lanes):
            return _err("Primero corta los golpes sueltos de la batería elegida en el laboratorio")
        return _ok(lanes=lanes)

    @Slot(str, result=str)
    @_safe
    def labOneShots(self, family: str) -> str:
        """Golpes sueltos de la batería elegida (WAV en `golpes/` de la sesión)."""
        return self._lab(self.lab.one_shots, family or "Batería")

    @Slot(result=str)
    @_safe
    def labCancel(self) -> str:
        self.lab.cancel()
        return _ok()

    # --- IA local: composición MIDI con MIDI-LLM (midi_ai.py) --------------------------
    @property
    def midi(self):
        if self._midi is None:
            from .midi_ai import MidiAi
            self._midi = MidiAi(self._mixer_events.put)
        return self._midi

    def _midi_busy(self) -> bool:
        return self._midi is not None and self._midi.generating

    def _midi_shutdown(self) -> None:
        if self._midi is not None:
            self._midi.shutdown()           # cierra llama-server

    @Slot(result=str)
    @_safe
    def midiStatus(self) -> str:
        """Motor llama-server, modelo MIDI y composiciones guardadas."""
        return _ok(**self.midi.status())

    @Slot(result=str)
    @_safe
    def midiDownload(self) -> str:
        try:
            self.midi.download()
        except Exception as exc:
            return _err(str(exc))
        return _ok(started=True)

    @Slot(result=str)
    @_safe
    def midiCancelDownload(self) -> str:
        self.midi.cancel_download()
        return _ok()

    @Slot(str, result=str)
    @_safe
    def midiGenerate(self, payload: str) -> str:
        """Compone en otro proceso; las pistas (notas por instrumento) llegan por `aiEvent` (aiMidi)."""
        if self.ai.generating or self.lab.busy or self.stems.busy:     # una sola carga en la gráfica
            return _err("Otro trabajo de IA está en marcha: espera a que termine.")
        try:
            return _ok(**self.midi.generate(json.loads(payload or "{}")))
        except Exception as exc:
            return _err(str(exc))

    @Slot(result=str)
    @_safe
    def midiCancel(self) -> str:
        self.midi.cancel()
        return _ok()

    @Slot(str, float, result=str)
    @_safe
    def midiOpen(self, path: str, bpm: float) -> str:
        """Lee un .mid (una composición guardada o, con ruta vacía, uno que elige el usuario) y lo
        devuelve como pistas de Instrumento y Batería."""
        from .midi_ai import read_mid, split_tracks
        if not path:
            path, _ = QFileDialog.getOpenFileName(self.parent_widget, "Importar MIDI", str(Path.home()),
                                                  "MIDI (*.mid *.midi)")
            if not path:
                return _err("", cancelled=True)
        try:
            notes = read_mid(Path(path[8:] if path.startswith("file:///") else path))
        except Exception as exc:
            return _err(f"No se pudo leer el MIDI: {exc}")
        if not notes:
            return _err("El archivo MIDI no tiene notas.")
        return _ok(tracks=split_tracks(notes, bpm, "MIDI"), notes=len(notes), path=str(path), title=Path(path[8:] if path.startswith("file:///") else path).stem)

    # --- plugins VST3 externos ------------------------------------------------------
    @Slot(result=str)
    @_safe
    def pluginScan(self) -> str:
        """Busca VST3 en las carpetas estándar de Windows en otro proceso (un plugin que se cuelga no
        cierra AllForOne). Responde enseguida; el avance llega por `pluginScanEvent`."""
        if (g := self._guard()):
            return g
        if self._scanner is None:
            from .plugin_scan import PluginScanner, list_file
            self._scanner = PluginScanner(list_file(paths.user_data_dir() / "motor"), self)
            self._scanner.event.connect(self._scan_event)
        if not self._scanner.start():
            return _err("Ya se están buscando plugins.")
        return _ok(started=True)

    def _scan_event(self, ev: dict) -> None:
        if ev.get("phase") == "done":
            try:
                self.host.engine.reload_plugins()
                ev["plugins"] = self.host.engine.known_plugins()
            except Exception as exc:
                ev.update(ok=False, error=f"No se pudo leer la lista de plugins: {exc}", plugins=[])
        self.pluginScanEvent.emit(json.dumps(_clean(ev), ensure_ascii=False))

    @Slot(result=str)
    @_safe
    def pluginList(self) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(plugins=self.host.engine.known_plugins())
        except Exception as exc:
            return _err(f"No se pudo leer la lista de plugins: {exc}")

    @Slot(int, str, int, result=str)
    @_safe
    def fxAddPlugin(self, track_id: int, plugin_id: str, index: int) -> str:
        if (g := self._guard()):
            return g
        try:
            e = self.host.engine.add_plugin_effect(int(track_id), plugin_id, int(index), "")
            self._fx_labels[e["id"]] = e["name"]
            return _ok(effect=e, chain=self._chain(track_id))
        except Exception as exc:
            return _err(f"No se pudo cargar el plugin: {exc}")

    @Slot(int, result=str)
    @_safe
    def fxPluginEditor(self, effect_id: int) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(shown=self.host.engine.show_effect_editor(int(effect_id)))
        except Exception as exc:
            return _err(f"No se pudo abrir el plugin: {exc}")

    @Slot(int, result=str)
    @_safe
    def instPluginEditor(self, track_id: int) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(shown=self.host.engine.show_instrument_editor(int(track_id)))
        except Exception as exc:
            return _err(f"No se pudo abrir el instrumento: {exc}")

    @Slot(str, result=str)
    @_safe
    def synthAudition(self, payload: str) -> str:
        """Escuchar una nota ({type, cfg, note, seconds}) o un golpe ({type: drum, cfg, lane}) al pulsar."""
        if (g := self._guard()):
            return g
        if not self.host.engine.device_info().get("open"):
            return _err("No hay dispositivo de salida de audio abierto.")
        return _ok(playing=self.host.audition(json.loads(payload)))

    @Slot(result=str)
    @_safe
    def addTestTone(self) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(track=self.host.add_test_tone())
        except Exception as exc:
            return _err(f"Tono de prueba: {exc}")

    @Slot(int, result=str)
    @_safe
    def removeTrack(self, track_id: int) -> str:
        if (g := self._guard()):
            return g
        if self._writer:
            self._writer.forget_track(int(track_id))
        return _ok(removed=self.host.remove(int(track_id)))

    # --- exportación ------------------------------------------------------------------
    @Slot(result=str)
    @_safe
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

    # --- Mezclador V4.2 (paneles Mezcla IA, Afinador, Master IA, Antes/Después) ---------------
    @Slot(str, str, result=str)
    @_safe
    def mixer(self, cmd: str, payload: str) -> str:
        try:
            data = json.loads(payload or "{}")
            fn = getattr(self, "_mx_" + cmd, None)
            if fn is None:
                return _err(f"Comando del mezclador desconocido: {cmd}")
            return _json(fn(data))
        except Exception as exc:
            log.exception("mixer %s", cmd)
            return _err(f"{type(exc).__name__}: {exc}")

    def _mx_info(self, d):
        return self.mixsvc.info()

    def _mx_describe(self, d):
        return {"ok": True, "stems": self.mixsvc.describe_paths(audio_files(d.get("paths", [])))}

    def _mx_add(self, d):
        files, _ = QFileDialog.getOpenFileNames(self.parent_widget, "Stems para la mezcla automática", str(Path.home()), AUDIO_FILTER)
        if not files:
            return {"ok": False, "cancelled": True}
        return {"ok": True, "stems": self.mixsvc.describe_paths(files)}

    def _mx_ref(self, d):
        f, _ = QFileDialog.getOpenFileName(self.parent_widget, "Canción de referencia para el mastering", str(Path.home()), AUDIO_FILTER)
        if not f:
            return {"ok": False, "cancelled": True}
        return {"ok": True, "reference": {"path": f, "name": Path(f).stem}}

    def _mx_fromtracks(self, d):
        if not self.host.ok:
            return {"ok": False, "error": self.host.error}
        files = [t["source_path"] for t in self.host.engine.tracks() if t["source_path"]]
        if not files:
            return {"ok": False, "error": "No hay pistas de audio en el motor. Importa audio en Pistas o arrastra archivos aquí."}
        return {"ok": True, "stems": self.mixsvc.describe_paths(files)}

    def _mx_analyze(self, d):
        return self.mixsvc.analyze_async(d)

    def _mx_confirm(self, d):
        return self.mixsvc.confirm(d)

    def _mx_mix(self, d):
        return self.mixsvc.mix_async(d)

    def _mix_buses(self, buses: dict) -> dict:
        """Buses Aux de la mezcla automática: se reutilizan por nombre (también los de un proyecto abierto),
        se crean si faltan y llevan su reverb como efecto automático. Devuelve {clave: id de la pista}."""
        from . import live_mix
        eng, ids = self.host.engine, {}
        for key, (name, _prefix) in live_mix.BUSES.items():
            aux = next((k for k, v in self.host.tracks.items() if v.get("name") == name), None)
            if key not in buses:
                if aux is not None:
                    ids[key] = aux                    # sin uso en esta mezcla: sus envíos se quitan
                continue
            if aux is None:
                info = self.host.add_aux(name)
                aux = info["id"]
                self._mixer_events.put({"type": "bus", "track": info})
            chain = buses[key]["chain"]
            new = live_mix.apply_chain(eng, aux, chain, self._auto.get(aux, []))
            for old in self._auto.get(aux, []):
                self._fx_labels.pop(old, None)
            for eid, fx in zip(new, chain):
                self._fx_labels[eid] = fx["label"]
            self._auto[aux] = new
            ids[key] = aux
        return ids

    def _apply_plan(self, plan: dict) -> None:
        """Hilo principal: las decisiones del V4.2 pasan a la consola y a las cadenas del motor."""
        from . import live_mix
        eng = self.host.engine
        applied = 0
        bus_ids = self._mix_buses(plan.get("buses") or {})
        for i, t in enumerate(plan["tracks"]):
            tid = t.get("trackId", -1)
            if tid not in self.host.tracks:
                continue
            if t.get("skip"):
                self._mixer_events.put({"type": "strip", "i": i, "phase": "done", "trackId": tid, "skip": t["skip"]})
                continue
            try:
                if t.get("tuned_path"):
                    start = float(self.host.tracks[tid].get("start_seconds", 0.0))
                    info = dict(eng.set_track_audio(tid, t["tuned_path"], start))
                    self.host.tracks[tid] = {**self.host.tracks[tid], **info}
                ids = live_mix.apply_chain(eng, tid, t["chain"], self._auto.get(tid, []),
                                           start=float(self.host.tracks[tid].get("start_seconds", 0.0) or 0.0))
                for old in self._auto.get(tid, []):
                    self._fx_labels.pop(old, None)
                for eid, fx in zip(ids, t["chain"]):
                    self._fx_labels[eid] = fx["label"]
                self._auto[tid] = ids
                eng.set_track_gain_db(tid, t["gain_db"])
                eng.set_track_pan(tid, t["pan"])
                for key, aux in bus_ids.items():      # envío a la reverb compartida (o se quita)
                    eng.set_send(tid, aux, float((t.get("sends") or {}).get(key, -100.0)), False)
                applied += 1
            except Exception as exc:
                log.exception("Mezcla en vivo: %s", t.get("name"))
                t["notes"].append(f"no se aplicó: {exc}")
            self._mixer_events.put({"type": "strip", "i": i, "phase": "done", "trackId": tid, "name": t["name"],
                                    "kind": t["kind"], "position": t["position"], "pan": t["pan"], "gain_db": t["gain_db"],
                                    "tuned": bool(t.get("tuned")),
                                    "chain": [fx["label"] for fx in t["chain"]], "note": "; ".join(t["notes"]),
                                    "automated": [fx["label"] for fx in t["chain"] if fx.get("auto")]})
        self._live_plan = plan
        self._mixer_events.put({"type": "done", "live": True, "applied": applied, "seconds": plan["seconds"],
                                "profile": plan.get("profile_name", ""), "skipped": plan["skipped"],
                                "reference_lufs": plan.get("reference_lufs"), "master": plan.get("master"),
                                "automation": plan.get("automation") or {}, "template_note": plan.get("template_note", "")})

    def _master_target(self, preset: str):
        """El preset elegido; «Según referencia» = Comercial con el objetivo de la referencia (como el V4.2)."""
        if preset != REF_LABEL:
            return preset, None
        ref = (self._live_plan or {}).get("reference_lufs")
        if ref is None:
            raise ValueError("Elige una canción de referencia en Mezcla IA y vuelve a mezclar.")
        return "Comercial (-11 LUFS)", max(-16.0, min(-9.0, float(ref)))

    def _mx_master(self, d):
        """Mastering automático en vivo: la cadena del master se decide midiendo la sesión en el motor."""
        if not self.host.ok:
            return {"ok": False, "error": self.host.error}
        from . import live_mix
        from .mixer_service import load
        if self.mixsvc.busy:
            return {"ok": False, "error": "El mezclador está trabajando; espera a que termine."}
        preset, target = self._master_target(d.get("preset") or "")
        bands = (self._live_plan or {}).get("mix_bands") or {}
        eng = self.host.engine
        if eng.is_playing():
            eng.pause()                              # medir es procesar la sesión entera en memoria
        old = self._auto.get(0, [])
        ids, stats, chain = live_mix.apply_master(eng, load(), preset, bands, old, target_lufs=target)
        for e in old:
            self._fx_labels.pop(e, None)
        for eid, fx in zip(ids, chain):
            self._fx_labels[eid] = fx["label"]
        self._auto[0] = ids
        stats["preset"] = d.get("preset")
        return {"ok": True, "stats": stats, "chain": self._chain(0)}

    def _mx_unmaster(self, d):
        """Quita la cadena del master automático (el limitador del master vuelve a su techo)."""
        from . import live_mix
        old = self._auto.pop(0, [])
        live_mix.apply_chain(self.host.engine, 0, [], old)
        for e in old:
            self._fx_labels.pop(e, None)
        self.host.engine.set_master_ceiling(-1.0)
        return {"ok": True, "chain": self._chain(0)}

    def _mx_measure(self, d):
        """Sonoridad de toda la sesión (master y pistas) procesada en memoria, sin archivos."""
        if not self.host.ok:
            return {"ok": False, "error": self.host.error}
        r = dict(self.host.engine.measure_mix())
        r["tracks"] = {str(k): v for k, v in r["tracks"].items()}
        return r

    def _mx_bypass(self, d):
        """A/B de escucha: activa o puentea los efectos de la mezcla automática (pista o master)."""
        on = not bool(d.get("bypass"))
        tid = d.get("track")
        # Sin pista: las pistas de la mezcla, no el master (tiene su propio A/B en Master IA)
        targets = [int(tid)] if tid is not None else [t for t in self._auto if t != project.MASTER]
        for t in targets:
            for e in self._auto.get(t, []):
                self.host.engine.set_effect_enabled(e, on)
        return {"ok": True, "bypass": not on}

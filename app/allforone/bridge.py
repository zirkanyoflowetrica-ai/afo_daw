"""Objeto que la interfaz nativa (QML) ve como `afo`: sus métodos son slots de Qt.

QML dibuja; Python coordina; C++ procesa el audio. Por aquí solo viajan comandos, estados y
datos visuales compactos (picos de forma de onda, medidores), nunca bloques de audio.
Todas las respuestas son JSON: {"ok": bool, ...}.
"""
from __future__ import annotations

import json
import logging
import math
import queue
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QWidget

from . import audio_import, fx_presets, paths, project
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
    mixerEvent = Signal(str)   # progreso y resultados del Mezclador V4.2 (desde su hilo de trabajo)

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
        self._mixer_events: queue.SimpleQueue = queue.SimpleQueue()
        self.mixsvc = MixerService(self._mixer_events.put)
        self._mixer_timer = QTimer(self)
        self._mixer_timer.setInterval(50)
        self._mixer_timer.timeout.connect(self._drain_mixer_events)
        self._mixer_timer.start()
        self._auto: dict[int, list[int]] = {}   # pista (0 = master) -> efectos que puso la mezcla automática
        self._fx_labels: dict[int, str] = {}     # efecto -> nombre que le dio la mezcla automática
        self._live_plan: dict | None = None      # última decisión de la mezcla en vivo (bandas para el master)
        self._to_convert: list[str] = []    # audios que el motor no lee y hay que convertir
        self._converting: str | None = None

    def _drain_mixer_events(self) -> None:
        for _ in range(200):
            try:
                ev = self._mixer_events.get_nowait()
            except queue.Empty:
                return
            if ev.get("type") == "_converted":      # interno: la conversión terminó en su hilo
                self._finish_import(ev)
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
    def hello(self) -> str:
        self.hello_count += 1
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
    def seek(self, seconds: float) -> str:
        """Lleva el cursor de reproducción a ese segundo (clic en la regla o en un carril de Pistas)."""
        if (g := self._guard()):
            return g
        self.host.engine.set_position_seconds(max(0.0, float(seconds)))
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

    @Slot(float, float, bool, result=str)
    def setMasterProcessing(self, drive: float, tone: float, limiter: bool) -> str:
        """Saturación, Tono y Limitador de «Mezcla final» (sección master del motor)."""
        if (g := self._guard()):
            return g
        self.host.engine.set_master_processing(float(drive), float(tone), bool(limiter))
        return _ok()

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

    # --- tomas del grabador --------------------------------------------------------
    # --- configuración de audio (driver, dispositivo, frecuencia, búfer) ---------------------
    @Slot(str, result=str)
    def audioOptions(self, type_name: str) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(**self.host.audio_options(type_name))
        except Exception as exc:
            return _err(f"No se pudo leer el dispositivo: {exc}")

    @Slot(str, result=str)
    def setAudioDevice(self, payload: str) -> str:
        if (g := self._guard()):
            return g
        try:
            err = self.host.set_audio_device(json.loads(payload))
        except Exception as exc:
            return _err(f"No se pudo cambiar el dispositivo: {exc}")
        info = self.host.engine.device_info()
        log.info("Dispositivo de audio: %s", info)
        if err:
            return _err(err, device=info)
        return _ok(device=info)

    @Slot(result=str)
    def audioControlPanel(self) -> str:
        if (g := self._guard()):
            return g
        if not self.host.engine.show_audio_control_panel():
            return _err("Este driver no tiene panel propio (solo los ASIO, como ASIO4ALL)")
        return _ok(device=self.host.engine.device_info())

    # --- grabador de cintas: graba el motor (Tracktion), no la interfaz ---------------------
    @Slot(result=str)
    def recInputs(self) -> str:
        if (g := self._guard()):
            return g
        return _ok(inputs=self.host.engine.record_inputs())

    @Slot(str, result=str)
    def recCreate(self, name: str) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(track=self.host.add_record_track(name or "Voz"))
        except Exception as exc:
            return _err(f"No se pudo crear la pista de voz: {exc}")

    @Slot(int, str, bool, result=str)
    def recArm(self, track_id: int, input_name: str, monitor: bool) -> str:
        if (g := self._guard()):
            return g
        if track_id < 0:
            self.host.engine.disarm()
            return _ok()
        err = self.host.engine.arm_track(track_id, input_name, monitor)
        return _err(err) if err else _ok(state=self.host._rec_state())

    @Slot(result=str)
    def recStart(self) -> str:
        if (g := self._guard()):
            return g
        err = self.host.engine.start_recording()
        return _err(err) if err else _ok()

    @Slot(bool, result=str)
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
    def fxCatalog(self) -> str:
        return _ok(catalog=self.host.effect_catalog())

    @Slot(int, str, int, result=str)
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
    def fxList(self, track_id: int) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(chain=self._chain(track_id))
        except Exception as exc:
            return _err(str(exc))

    @Slot(int, int, result=str)
    def fxRemove(self, effect_id: int, track_id: int) -> str:
        if (g := self._guard()):
            return g
        self.host.engine.remove_effect(effect_id)
        self._fx_labels.pop(effect_id, None)
        return _ok(chain=self._chain(track_id))

    @Slot(int, int, int, result=str)
    def fxMove(self, effect_id: int, index: int, track_id: int) -> str:
        if (g := self._guard()):
            return g
        self.host.engine.move_effect(effect_id, index)
        return _ok(chain=self._chain(track_id))

    @Slot(int, str, float, result=str)
    def fxParam(self, effect_id: int, param: str, value: float) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok() if self.host.engine.set_effect_param(effect_id, param, value) else _err(f"Parámetro desconocido: {param}")
        except Exception as exc:
            return _err(str(exc))

    @Slot(int, bool, result=str)
    def fxEnable(self, effect_id: int, enabled: bool) -> str:
        if (g := self._guard()):
            return g
        self.host.engine.set_effect_enabled(effect_id, enabled)
        return _ok()

    @Slot(int, result=str)
    def fxMeters(self, effect_id: int) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(m=[round(v, 1) for v in self.host.engine.effect_meters(effect_id)])
        except Exception as exc:
            return _err(str(exc))

    @Slot(float, result=str)
    def setMasterCeiling(self, db: float) -> str:
        """Techo del limitador del master (−6..0 dBFS); Master IA lo fija según el preset."""
        if (g := self._guard()):
            return g
        self.host.engine.set_master_ceiling(db)
        return _ok(ceiling=self.host.engine.master_ceiling())

    @Slot(int, int, result=str)
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
    def fxPresets(self, key: str) -> str:
        try:
            return _ok(presets=fx_presets.listing(key))
        except Exception as exc:
            return _err(str(exc))

    @Slot(int, str, result=str)
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
    def fxDeletePreset(self, key: str, name: str) -> str:
        try:
            if not fx_presets.delete(key, name):
                return _err(f"«{name}» no es un preset del usuario")
            return _ok(presets=fx_presets.listing(key))
        except Exception as exc:
            return _err(str(exc))

    @Slot(int, str, result=str)
    def fxAutomation(self, effect_id: int, param: str) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(points=[[round(t, 4), v] for t, v in self.host.engine.effect_automation(effect_id, param)])
        except Exception as exc:
            return _err(str(exc))

    @Slot(int, str, str, result=str)
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

    @Slot(int, result=str)
    def fxInfo(self, effect_id: int) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(effect=self.host.engine.effect_info(effect_id))
        except Exception as exc:
            return _err(str(exc))

    @Slot(int, str, result=str)
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

    # --- proyecto -----------------------------------------------------------------
    def _project_dir(self) -> str:
        p = paths.user_data_dir() / "proyectos"
        p.mkdir(parents=True, exist_ok=True)
        return str(p)

    # --- edición de clips de audio (Pistas) -------------------------------------------
    @Slot(int, result=str)
    def clipList(self, track_id: int) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(clips=self.host.engine.clips(int(track_id)))
        except Exception as exc:
            return _err(f"No se pudieron leer los clips: {exc}")

    @Slot(int, str, result=str)
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
                eng.set_clips(int(track_id), op["clips"])
            else:
                return _err(f"Edición desconocida: {kind}")
            info = next((t for t in eng.tracks() if t["id"] == int(track_id)), {})
            return _ok(clips=eng.clips(int(track_id)), start=info.get("start_seconds", 0.0),
                       length=info.get("length_seconds", 0.0))
        except Exception as exc:
            return _err(f"No se pudo editar el clip: {exc}")

    @Slot(str, str, result=str)
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
            doc = project.collect(json.loads(doc_json), eng, self.host.effect_catalog(), sources, self._fx_labels, self._auto)
            out = project.save(path, doc)
            return _ok(path=str(out), name=out.stem)
        except Exception as exc:
            return _err(f"No se pudo guardar el proyecto: {exc}")

    @Slot(str, result=str)
    def projectOpen(self, path: str) -> str:
        """Lee un proyecto; la interfaz recrea la sesión con él (ver qml/state/Project.qml)."""
        if not path:
            path, _ = QFileDialog.getOpenFileName(self.parent_widget, "Abrir proyecto", self._project_dir(),
                                                  "Proyecto AllForOne (*.afo)")
            if not path:
                return _err("", cancelled=True)
        try:
            doc = project.load(path)
            return _ok(doc=doc, path=doc["file"], name=Path(path).stem)
        except Exception as exc:
            return _err(f"No se pudo abrir el proyecto: {exc}")

    @Slot(str, str, result=str)
    def addAudioPath(self, path: str, name: str) -> str:
        """Pista de audio desde una ruta conocida (al abrir un proyecto), sin diálogo."""
        if (g := self._guard()):
            return g
        try:
            return _ok(track=self.host.add_audio(path, name))
        except Exception as exc:
            return _err(f"No se pudo cargar {Path(path).name}: {exc}")

    @Slot(int, str, float, result=str)
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
    def importAudio(self) -> str:
        if (g := self._guard()):
            return g
        files, _ = QFileDialog.getOpenFileNames(self.parent_widget, "Importar audio", str(Path.home()), AUDIO_FILTER)
        if not files:
            return json.dumps({"ok": False, "cancelled": True})
        return self.import_paths(files)

    @Slot(str, result=str)
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
    def synthCreate(self, name: str, mode: int) -> str:
        """Pista nueva con el sintetizador del motor (mode 0 = instrumento, 1 = batería)."""
        if (g := self._guard()):
            return g
        return _ok(track=self.host.add_synth(name, int(mode)))

    @Slot(int, str, result=str)
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
            return _ok(length=self.host.update_synth(int(track_id), data))
        except Exception as exc:
            return _err(f"Sintetizador: {exc}")

    # --- plugins VST3 externos ------------------------------------------------------
    @Slot(result=str)
    def pluginScan(self) -> str:
        """Busca VST3 en las carpetas estándar de Windows. Cada plugin se abre una vez para leer sus
        datos; la lista queda guardada en la carpeta de datos."""
        if (g := self._guard()):
            return g
        try:
            return _ok(**self.host.engine.scan_plugins([]))
        except Exception as exc:
            return _err(f"No se pudieron buscar plugins: {exc}")

    @Slot(result=str)
    def pluginList(self) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(plugins=self.host.engine.known_plugins())
        except Exception as exc:
            return _err(f"No se pudo leer la lista de plugins: {exc}")

    @Slot(int, str, int, result=str)
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
    def fxPluginEditor(self, effect_id: int) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(shown=self.host.engine.show_effect_editor(int(effect_id)))
        except Exception as exc:
            return _err(f"No se pudo abrir el plugin: {exc}")

    @Slot(int, result=str)
    def instPluginEditor(self, track_id: int) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(shown=self.host.engine.show_instrument_editor(int(track_id)))
        except Exception as exc:
            return _err(f"No se pudo abrir el instrumento: {exc}")

    @Slot(str, result=str)
    def synthAudition(self, payload: str) -> str:
        """Escuchar una nota ({type, cfg, note, seconds}) o un golpe ({type: drum, cfg, lane}) al pulsar."""
        if (g := self._guard()):
            return g
        if not self.host.engine.device_info().get("open"):
            return _err("No hay dispositivo de salida de audio abierto.")
        return _ok(playing=self.host.audition(json.loads(payload)))

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

    # --- Mezclador V4.2 (paneles Mezcla IA, Afinador, Master IA, Antes/Después) ---------------
    @Slot(str, str, result=str)
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
        files = [t["source_path"] for t in self.host.engine.tracks()]
        if not files:
            return {"ok": False, "error": "No hay pistas de audio en el motor. Importa audio en Pistas o arrastra archivos aquí."}
        return {"ok": True, "stems": self.mixsvc.describe_paths(files)}

    def _mx_analyze(self, d):
        return self.mixsvc.analyze_async(d)

    def _mx_confirm(self, d):
        return self.mixsvc.confirm(d)

    def _mx_mix(self, d):
        return self.mixsvc.mix_async(d)

    def _apply_plan(self, plan: dict) -> None:
        """Hilo principal: las decisiones del V4.2 pasan a la consola y a las cadenas del motor."""
        from . import live_mix
        eng = self.host.engine
        applied = 0
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
                ids = live_mix.apply_chain(eng, tid, t["chain"], self._auto.get(tid, []))
                for old in self._auto.get(tid, []):
                    self._fx_labels.pop(old, None)
                for eid, fx in zip(ids, t["chain"]):
                    self._fx_labels[eid] = fx["label"]
                self._auto[tid] = ids
                eng.set_track_gain_db(tid, t["gain_db"])
                eng.set_track_pan(tid, t["pan"])
                applied += 1
            except Exception as exc:
                log.exception("Mezcla en vivo: %s", t.get("name"))
                t["notes"].append(f"no se aplicó: {exc}")
            self._mixer_events.put({"type": "strip", "i": i, "phase": "done", "trackId": tid, "name": t["name"],
                                    "kind": t["kind"], "position": t["position"], "pan": t["pan"], "gain_db": t["gain_db"],
                                    "tuned": bool(t.get("tuned_path")),
                                    "chain": [fx["label"] for fx in t["chain"]], "note": "; ".join(t["notes"])})
        self._live_plan = plan
        self._mixer_events.put({"type": "done", "live": True, "applied": applied, "seconds": plan["seconds"],
                                "profile": plan.get("profile_name", ""), "skipped": plan["skipped"],
                                "reference_lufs": plan.get("reference_lufs"), "master": plan.get("master")})

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
        targets = [int(tid)] if tid is not None else list(self._auto)
        for t in targets:
            for e in self._auto.get(t, []):
                self.host.engine.set_effect_enabled(e, on)
        return {"ok": True, "bypass": not on}

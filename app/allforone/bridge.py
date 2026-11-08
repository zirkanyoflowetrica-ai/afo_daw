"""Objeto expuesto a JavaScript mediante QWebChannel (nombre: "afo").

JavaScript dibuja; Python coordina; C++ procesa el audio. Por el canal solo viajan comandos,
estados y datos visuales compactos (picos de forma de onda), nunca bloques de audio.
Todas las respuestas son JSON: {"ok": bool, ...}.
"""
from __future__ import annotations

import base64
import json
import logging
import math
import queue
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QWidget

from . import audio_import, paths
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
        self.js_hello_count = 0
        self.last_error: str | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 Hz para cursor y medidores
        self._timer.timeout.connect(self._tick)
        if host.ok:
            self._timer.start()
        # El mezclador trabaja en otro hilo: sus eventos se encolan y se emiten desde el hilo
        # principal (QWebChannel solo reenvía a JavaScript señales emitidas en su propio hilo).
        self._mixer_events: queue.SimpleQueue = queue.SimpleQueue()
        self.mixsvc = MixerService(self._mixer_events.put)
        self._mixer_timer = QTimer(self)
        self._mixer_timer.setInterval(50)
        self._mixer_timer.timeout.connect(self._drain_mixer_events)
        self._mixer_timer.start()
        self._takes: dict[str, dict] = {}   # tomas del grabador que están llegando por trozos
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
            return _ok(effect=self.host.engine.add_effect(track_id, key, index), chain=self.host.engine.effects(track_id))
        except Exception as exc:
            return _err(f"No se pudo insertar el efecto: {exc}")

    @Slot(int, result=str)
    def fxList(self, track_id: int) -> str:
        if (g := self._guard()):
            return g
        try:
            return _ok(chain=self.host.engine.effects(track_id))
        except Exception as exc:
            return _err(str(exc))

    @Slot(int, int, result=str)
    def fxRemove(self, effect_id: int, track_id: int) -> str:
        if (g := self._guard()):
            return g
        self.host.engine.remove_effect(effect_id)
        return _ok(chain=self.host.engine.effects(track_id))

    @Slot(int, int, int, result=str)
    def fxMove(self, effect_id: int, index: int, track_id: int) -> str:
        if (g := self._guard()):
            return g
        self.host.engine.move_effect(effect_id, index)
        return _ok(chain=self.host.engine.effects(track_id))

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

    @Slot(int, int, result=str)
    def fxSpectrum(self, effect_id: int, bands: int) -> str:
        """Espectro del Analizador (AF-76): dB por banda logarítmica de 20 Hz a 20 kHz."""
        if (g := self._guard()):
            return g
        try:
            return _ok(bands=[round(v, 1) for v in self.host.engine.effect_spectrum(effect_id, max(8, min(256, bands)))])
        except Exception as exc:
            return _err(str(exc))

    # El grabador de la plantilla produce un Blob en el navegador. JavaScript lo decodifica,
    # arma un WAV PCM de 24 bits y lo manda por trozos: aquí solo se escriben los bytes.
    @Slot(str, result=str)
    def takeBegin(self, name: str) -> str:
        token = f"t{len(self._takes) + 1}_{datetime.now():%H%M%S}"
        safe = re.sub(r"[^\w.\- ]+", "_", name or "toma").strip() or "toma"
        self._takes[token] = {"name": safe, "parts": [], "bytes": 0}
        return _ok(token=token)

    @Slot(str, str, result=str)
    def takeChunk(self, token: str, b64: str) -> str:
        t = self._takes.get(token)
        if t is None:
            return _err("Toma desconocida (vuelve a empezar)")
        try:
            data = base64.b64decode(b64, validate=True)
        except Exception as exc:
            self._takes.pop(token, None)
            return _err(f"Trozo de audio inválido: {exc}")
        t["bytes"] += len(data)
        if t["bytes"] > 512 * 1024 * 1024:
            self._takes.pop(token, None)
            return _err("Toma demasiado larga (más de 512 MB)")
        t["parts"].append(data)
        return _ok()

    @Slot(str, result=str)
    def takeEnd(self, token: str) -> str:
        t = self._takes.pop(token, None)
        if t is None:
            return _err("Toma desconocida (vuelve a empezar)")
        folder = paths.user_data_dir() / "tomas"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f"{t['name']}_{datetime.now():%Y%m%d_%H%M%S}.wav"
        try:
            dest.write_bytes(b"".join(t["parts"]))
        except OSError as exc:
            return _err(f"No se pudo guardar la toma: {exc}")
        try:
            stem = self.mixsvc.describe_paths([str(dest)])[0]
        except Exception as exc:
            return _err(f"Toma guardada en {dest}, pero el mezclador no pudo clasificarla: {exc}")
        log.info("Toma guardada: %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
        return _ok(stem=stem, path=str(dest))

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
            return _ok(length=self.host.update_synth(int(track_id), json.loads(payload)))
        except Exception as exc:
            return _err(f"Sintetizador: {exc}")

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

    def _mx_remix(self, d):
        d["label"] = f"Remezcla · {d.get('profile_name') or ''}".strip(" ·")
        return self.mixsvc.mix_async(d)

    def _run(self, d):
        runs = self.mixsvc.runs
        i = d.get("run")
        if i is None or not (0 <= int(i) < len(runs)):
            raise ValueError("Todavía no hay una mezcla terminada.")
        return runs[int(i)]

    def _master_file(self, run, sel):
        names = list(self.mixsvc.info()["masters"]) + [REF_LABEL]
        name = names[int(sel)]
        if name not in run["masters"]:
            raise ValueError(f"No hay «{name}» en esta mezcla.")
        return name, run["masters"][name]["file"]

    def _mx_listen(self, d):
        if not self.host.ok:
            return {"ok": False, "error": self.host.error}
        eng = self.host.engine
        if d.get("ab") == "stop":
            eng.preview_stop()
            return {"ok": True, "playing": False}
        run = self._run(d)
        if d.get("what") == "master":
            path = run["mix"] if d.get("ab") == "A" else self._master_file(run, d.get("sel", 3))[1]
        else:
            item = run["review"][int(d.get("sel", 0))]
            path = item["a"] if d.get("ab") == "A" else item["b"]
        if not eng.device_info().get("open"):
            return {"ok": False, "error": "No hay dispositivo de salida de audio abierto."}
        if eng.is_playing():
            eng.pause()
        pos = eng.preview_position() if eng.preview_playing() else 0.0   # A/B: misma posición
        if not eng.preview_play(path, pos):
            return {"ok": False, "error": f"No se pudo reproducir {Path(path).name}"}
        return {"ok": True, "playing": True, "file": Path(path).name}

    def _mx_tracks(self, d):
        if not self.host.ok:
            return {"ok": False, "error": self.host.error}
        run = self._run(d)
        name, path = self._master_file(run, d.get("sel", 3))
        info = self.host.add_audio(path, f"Master IA · {name.split(' (')[0]} #{run['id'] + 1}")
        return {"ok": True, "tracks": [info]}

    def _mx_zip(self, d):
        """El ZIP se arma aquí, no al mezclar: para una canción entera son GB y casi un minuto."""
        run = self._run(d)
        target, _ = QFileDialog.getSaveFileName(self.parent_widget, "Guardar sesión de mezcla", str(Path.home() / Path(run["zip"]).name), "ZIP (*.zip)")
        if not target:
            return {"ok": False, "cancelled": True}
        self._mixer_events.put({"type": "progress", "panel": "mezcla", "p": 5, "desc": "Comprimiendo la sesión…"})

        def work():
            try:
                src = self.mixsvc.make_zip(run, lambda i, n: self._mixer_events.put(
                    {"type": "progress", "panel": "mezcla", "p": round(100 * i / max(1, n), 1),
                     "desc": f"Comprimiendo la sesión… {i}/{n} archivos"}))
                shutil.copy2(src, target)
                self._mixer_events.put({"type": "progress", "panel": "mezcla", "p": 100, "desc": f"Sesión guardada: {target}"})
            except Exception as exc:
                self._mixer_events.put({"type": "error", "panel": "mezcla", "error": f"No se pudo crear el ZIP: {exc}"})

        threading.Thread(target=work, name="afo-zip", daemon=True).start()
        return {"ok": True, "pendiente": True, "path": target}

    def _mx_folder(self, d):
        run = self._run(d)
        QDesktopServices.openUrl(QUrl.fromLocalFile(run["folder"]))
        return {"ok": True, "path": run["folder"]}

    def _mx_report(self, d):
        return {"ok": True, "report": self._run(d)["report"]}

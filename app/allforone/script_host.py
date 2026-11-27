"""F8: scripts del usuario (como ReaScript): archivos .py en `scripts/` con la API `afo`.

Cómo corre un script, sin tocar el audio en tiempo real ni parar la interfaz:
  1. La ventana manda una copia del proyecto (pistas con sus clips y el archivo que suena, tempo,
     tonalidad, acordes, secciones y efectos disponibles) a `ScriptRunner.run`.
  2. Un proceso aparte (`AllForOne.exe --run-script` o `python -m allforone --run-script`) carga el
     script con la API `afo` sobre esa copia. Lo que el script lee sale de la copia; lo que cambia se
     apunta como órdenes. Puede leer audio y analizarlo (numpy, `allforone.analysis`) en ese proceso.
  3. Al terminar, las órdenes vuelven por el puente y la ventana las aplica en su hilo, todas juntas
     como **un solo paso de Ctrl+Z**.

Órdenes: track (vol en dB, pan, mute, solo, name, color), clip_gain, markers, chords, key, fx (añadir
un efecto de la Biblioteca nativa), export_stems, seek, play, stop. Un script no puede crear ni borrar
pistas, ni tocar el bloque de audio: eso lo hacen el motor C++ y la interfaz.
"""
from __future__ import annotations

import ast
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Callable

from . import paths

log = logging.getLogger("allforone.scripts")

TIMEOUT_S = 300.0
# Colores de pista que puede pedir un script: los de la paleta del tema (Theme.pc), nunca un «#…»
COLORS = ("pistas", "inst", "piano", "drums", "cinta", "ia", "audios", "afina", "mezcla", "fx", "master")
SAFE_TYPES = ("audio", "voz", "inst", "drum", "ia", "aux")


def scripts_dir() -> Path:
    """`scripts/` junto al programa (EXE\\scripts) o en la raíz del proyecto durante el desarrollo."""
    return paths.app_root() / "scripts"


def _describe(path: Path) -> dict:
    """Nombre y explicación de un script: primera línea y resto de su docstring."""
    name, tip = path.stem.replace("_", " ").capitalize(), ""
    try:
        doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
        lines = [x.strip() for x in doc.strip().splitlines()]
        if lines and lines[0]:
            name = lines[0].rstrip(".")
            tip = " ".join(x for x in lines[1:] if x)[:200]
    except (OSError, SyntaxError, ValueError) as exc:
        tip = f"No se puede leer: {exc}"
    return {"file": path.name, "id": "script." + path.stem, "name": name, "tip": tip or name}


def list_scripts(folder: Path | None = None) -> list[dict]:
    d = folder or scripts_dir()
    if not d.is_dir():
        return []
    return [_describe(p) for p in sorted(d.glob("*.py")) if not p.name.startswith("_")]


def child_command(script: Path, io_path: Path) -> list[str]:
    if paths.is_frozen():
        return [sys.executable, "--run-script", str(script), "--script-io", str(io_path)]
    return [sys.executable, "-m", "allforone", "--run-script", str(script), "--script-io", str(io_path)]


class ScriptRunner:
    """Lanza un script en un proceso aparte (uno a la vez) y entrega el resultado por `emit`."""

    def __init__(self, emit: Callable[[dict], None]):
        self.emit = emit
        self.busy = ""
        self._proc: subprocess.Popen | None = None

    def run(self, file: str, snapshot: dict, folder: Path | None = None) -> dict:
        if self.busy:
            return {"ok": False, "error": f"Ya corre el script «{self.busy}»; espera a que termine."}
        d = folder or scripts_dir()
        script = (d / file).resolve()
        if script.parent != d.resolve() or script.suffix != ".py" or not script.is_file():
            return {"ok": False, "error": f"No existe el script {file} en {d}"}
        desc = _describe(script)
        tmp = Path(tempfile.mkdtemp(prefix="afo_script_"))
        io_path = tmp / "io.json"
        io_path.write_text(json.dumps({"snapshot": snapshot}), encoding="utf-8")
        self.busy = desc["name"]
        threading.Thread(target=self._work, args=(script, io_path, desc), name="afo-script", daemon=True).start()
        return {"ok": True, "started": True, "name": desc["name"]}

    def _work(self, script: Path, io_path: Path, desc: dict) -> None:
        from . import procs
        t0 = time.monotonic()
        out = {"type": "scriptDone", "ok": False, "file": script.name, "name": desc["name"], "commands": [], "log": []}
        try:
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            if not paths.is_frozen():
                env["PYTHONPATH"] = os.pathsep.join([str(paths.package_dir().parent), env.get("PYTHONPATH", "")])
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self._proc = procs.spawn(child_command(script, io_path), env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, creationflags=flags)
            try:
                text, _ = self._proc.communicate(timeout=TIMEOUT_S)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                text, _ = self._proc.communicate()
                out["error"] = f"El script tardó más de {int(TIMEOUT_S)} s y se paró; no se cambió nada."
            res = json.loads(io_path.read_text(encoding="utf-8")).get("result") if io_path.is_file() else None
            if res is None and "error" not in out:
                tail = (text or b"").decode("utf-8", "replace").strip().splitlines()[-3:]
                out["error"] = "El script se cerró sin terminar" + (": " + " ".join(tail) if tail else "")
            elif res is not None:
                out.update(res)
        except Exception as exc:
            log.exception("script %s", script)
            out["error"] = f"No se pudo lanzar el script: {exc}"
        finally:
            self._proc = None
            out["seconds"] = round(time.monotonic() - t0, 2)
            try:
                io_path.unlink(missing_ok=True)
                io_path.parent.rmdir()
            except OSError:
                pass
            self.busy = ""
            self.emit(out)


# ------------------------------ proceso del script ------------------------------
class ScriptError(Exception):
    pass


class Clip:
    def __init__(self, track: "Track", d: dict):
        self.track, self._d = track, d
        self.id = d.get("id")
        self.start = float(d.get("start", 0.0))
        self.length = float(d.get("length", 0.0))
        self.offset = float(d.get("offset", 0.0))
        self.speed = float(d.get("speed", 1.0) or 1.0)
        self.gain_db = float(d.get("gain_db", 0.0))

    def __repr__(self) -> str:
        return f"<Clip {self.id} de «{self.track.name}» {self.start:.2f}–{self.start + self.length:.2f} s {self.gain_db:+.1f} dB>"

    def audio(self):
        """Lo que suena del archivo en este clip (mono, float32, a la frecuencia del archivo), sin su
        ganancia de clip ni efectos. Devuelve (muestras, frecuencia)."""
        import numpy as np
        import soundfile as sf
        if not self.track.path:
            raise ScriptError(f"La pista «{self.track.name}» no tiene archivo de audio")
        info = sf.info(self.track.path)
        a = int(self.offset * self.speed * info.samplerate)
        n = int(self.length * self.speed * info.samplerate)
        x, sr = sf.read(self.track.path, start=max(0, a), frames=max(0, n), dtype="float32", always_2d=True)
        return np.ascontiguousarray(x.mean(axis=1)), sr

    def peak_db(self) -> float:
        """Pico del clip en dBFS tal como sale del clip (con su ganancia de ahora)."""
        import numpy as np
        x, _ = self.audio()
        p = float(np.max(np.abs(x))) if x.size else 0.0
        return (20 * np.log10(p) if p > 0 else -120.0) + self.gain_db

    def set_gain(self, db: float) -> None:
        db = round(max(-48.0, min(24.0, float(db))), 2)
        self.gain_db = db
        self.track._afo._cmd({"op": "clip_gain", "uid": self.track.uid, "clip": self.id, "db": db})


class Track:
    def __init__(self, afo: "Afo", d: dict):
        self._afo = afo
        self.uid = d.get("uid", "")
        self.id = int(d.get("id", -1))
        self.type = d.get("type", "")
        self.name = d.get("name", "")
        self.volume_db = float(d.get("vol_db", 0.0))
        self.pan = float(d.get("pan", 0.0))           # −1 izquierda … 1 derecha
        self.mute = bool(d.get("mute", False))
        self.solo = bool(d.get("solo", False))
        self.color = d.get("color", "")
        self.path = d.get("path", "")
        self.clips = [Clip(self, c) for c in d.get("clips", [])]

    def __repr__(self) -> str:
        return f"<Track «{self.name}» {self.type} {len(self.clips)} clips>"

    @property
    def is_voice(self) -> bool:
        """Pista de voz: grabada como voz o con un nombre de voz (voz, vocal, coro…)."""
        n = self.name.lower()
        return self.type == "voz" or any(w in n for w in ("voz", "vocal", "coro", "voice", "lead vox", "adlib"))

    def _set(self, **kw) -> None:
        self._afo._cmd({"op": "track", "uid": self.uid, **kw})

    def set_volume(self, db: float) -> None:
        self.volume_db = max(-24.0, min(6.0, float(db)))
        self._set(vol_db=round(self.volume_db, 2))

    def set_pan(self, pan: float) -> None:
        self.pan = max(-1.0, min(1.0, float(pan)))
        self._set(pan=round(self.pan, 3))

    def set_mute(self, on: bool = True) -> None:
        self.mute = bool(on)
        self._set(mute=self.mute)

    def set_solo(self, on: bool = True) -> None:
        self.solo = bool(on)
        self._set(solo=self.solo)

    def rename(self, name: str) -> None:
        name = str(name).strip()[:60]
        if not name:
            raise ScriptError("El nombre de la pista no puede quedar vacío")
        self.name = name
        self._set(name=name)

    def set_color(self, color: str) -> None:
        """Color de la paleta del tema (afo.colors: pistas, inst, piano, drums…; "" = el de su tipo)."""
        if color and color not in COLORS:
            raise ScriptError(f"Color «{color}» desconocido; usa uno de {', '.join(COLORS)}")
        self.color = color
        self._set(color=color)

    def add_effect(self, key: str) -> None:
        """Añade al final de la cadena un efecto de la Biblioteca nativa (p. ej. «eq», «compressor»)."""
        if key not in self._afo.effects:
            raise ScriptError(f"Efecto «{key}» desconocido; hay: {', '.join(self._afo.effects)}")
        self._afo._cmd({"op": "fx", "uid": self.uid, "key": key})


class Afo:
    """La API que ve un script: `afo.tracks()`, `afo.analyze()`, `afo.set_markers()`…"""

    def __init__(self, snap: dict):
        self._snap = snap
        self.commands: list[dict] = []
        self.messages: list[str] = []
        self.bpm = float(snap.get("bpm", 120.0))
        self.key = dict(snap.get("key") or {"key": "", "scale": ""})
        self.chords = list(snap.get("chords") or [])
        self.markers = list(snap.get("markers") or [])
        self.effects = list(snap.get("effects") or [])
        self.colors = COLORS
        self._tracks = [Track(self, t) for t in snap.get("tracks", []) if t.get("type") in SAFE_TYPES]

    def _cmd(self, c: dict) -> None:
        self.commands.append(c)

    # --- lectura ---
    def tracks(self, type: str | None = None) -> list[Track]:
        return [t for t in self._tracks if type is None or t.type == type]

    def track(self, name: str) -> Track:
        for t in self._tracks:
            if t.name == name:
                return t
        raise ScriptError(f"No hay ninguna pista «{name}»")

    def voices(self) -> list[Track]:
        return [t for t in self._tracks if t.is_voice and t.clips]

    def log(self, *parts) -> None:
        """Mensaje para el usuario (sale en la barra de estado al terminar)."""
        self.messages.append(" ".join(str(p) for p in parts))

    def mix(self, tracks: list[Track] | None = None):
        """Suma mono a 22,05 kHz de las pistas dadas (o de las que suenan), clips en su sitio."""
        from . import analysis
        parts = []
        for t in tracks if tracks is not None else [x for x in self._tracks if not x.mute]:
            if not t.path:
                continue
            for c in t.clips:
                parts.append((t.path, c.start, c.offset * c.speed, c.length * c.speed, c.length, c.gain_db))
        if not parts:
            raise ScriptError("No hay audio que sumar: ninguna pista con clips y archivo")
        return analysis.mix_clips(parts)

    def analyze(self, tracks: list[Track] | None = None) -> dict:
        """Tempo, tonalidad, acordes y secciones (lo mismo que «Editar › Analizar el proyecto»)."""
        from . import analysis
        return analysis.analyze_mix(self.mix(tracks), self.bpm)

    # --- canción ---
    def set_markers(self, markers: list[dict]) -> None:
        """Secciones [{start, end, label}] en segundos."""
        ms = [{"start": round(float(m["start"]), 3), "end": round(float(m["end"]), 3), "label": str(m["label"])[:24]} for m in markers]
        self.markers = ms
        self._cmd({"op": "markers", "markers": ms})

    def set_chords(self, chords: list[dict]) -> None:
        self.chords = [dict(c) for c in chords]
        self._cmd({"op": "chords", "chords": self.chords})

    def set_key(self, key: str, scale: str) -> None:
        self.key = {"key": key, "scale": scale}
        self._cmd({"op": "key", "key": key, "scale": scale})

    # --- transporte y exportación ---
    def seek(self, seconds: float) -> None:
        self._cmd({"op": "seek", "t": max(0.0, float(seconds))})

    def play(self) -> None:
        self._cmd({"op": "play"})

    def stop(self) -> None:
        self._cmd({"op": "stop"})

    def export_stems(self, folder: str = "", tracks: list[Track] | None = None) -> None:
        """Escribe un WAV por pista (con sus efectos y el master) en `folder` (si no, junto al proyecto)."""
        ts = tracks if tracks is not None else [t for t in self._tracks if t.clips or t.type in ("inst", "drum")]
        self._cmd({"op": "export_stems", "folder": str(folder), "uids": [t.uid for t in ts]})


def run_child(script: str, io_file: str) -> int:
    """Proceso del script: carga la copia del proyecto, ejecuta el script con `afo` y escribe las órdenes."""
    io_path = Path(io_file)
    data = json.loads(io_path.read_text(encoding="utf-8"))
    afo = Afo(data.get("snapshot") or {})
    result: dict = {"ok": True}
    try:
        src = Path(script).read_text(encoding="utf-8")
        g = {"__name__": "__afo_script__", "__file__": script, "afo": afo, "ScriptError": ScriptError}
        exec(compile(src, script, "exec"), g)
    except ScriptError as exc:
        result = {"ok": False, "error": str(exc)}
    except Exception as exc:
        tb = traceback.extract_tb(exc.__traceback__)
        line = next((f.lineno for f in reversed(tb) if f.filename == script), None)
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}" + (f" (línea {line})" if line else "")}
    # si falla a medias no se aplica nada: o todo o nada, como un solo paso de deshacer
    result.update(commands=afo.commands if result["ok"] else [], log=afo.messages)
    data["result"] = result
    io_path.write_text(json.dumps(data), encoding="utf-8")
    return 0 if result["ok"] else 1

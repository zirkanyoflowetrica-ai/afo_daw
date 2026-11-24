"""Separador de stems con IA local: Demucs v4 (htdemucs de 6 fuentes) por demucs.cpp.

Como la IA de ACE-Step, todo corre en el equipo y en un proceso aparte:
  * El motor es `motores/demucs/afo-demucs.exe` (demucs.cpp, C++17 + Eigen + OpenMP, licencia MIT,
    compilado con `tools/build_demucs.ps1`). Si falla o se cancela, AllForOne sigue en pie.
  * El modelo ggml (55 MB) se descarga desde la aplicación a `modelos/demucs`.
  * Separa en Batería, Bajo, Voz, Guitarra, Piano y Otros. Las que salen en silencio no se cargan.
  * La batería se puede dividir además en Bombo, Caja / Clap y Platos por bandas de frecuencia
    (filtros complementarios: las tres suman exactamente la batería separada).
Por el puente solo viajan textos de avance; el audio va de archivo a archivo.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np

from . import paths

log = logging.getLogger("allforone.stems")

MODEL = "ggml-model-htdemucs-6s-f16.bin"
MODEL_SIZE = 54855129                     # bytes exactos (Hugging Face)
MODEL_URL = "https://huggingface.co/datasets/Retrobear/demucs.cpp/resolve/main/" + MODEL
EXE = "afo-demucs.exe" if os.name == "nt" else "afo-demucs"
SR = 44100                                # Demucs trabaja a 44,1 kHz estéreo
THREADS = 8                               # con 12 hilos demucs.cpp se cae (medido); 8 es estable
SECONDS_PER_THREAD = 5.0                  # cada hilo necesita su trozo: 10,7 s con 8 hilos se cae (medido)
# Orden de salida de htdemucs_6s → nombre en la interfaz
SOURCES = [("drums", "Batería"), ("bass", "Bajo"), ("other", "Otros"), ("vocals", "Voz"),
           ("guitar", "Guitarra"), ("piano", "Piano")]
DRUM_PARTS = ("Bombo", "Caja / Clap", "Platos")
SILENT_DB = -50.0                         # una fuente por debajo de esto no se carga como pista
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_RE_PCT = re.compile(r"\[THREAD (\d+)\] \((\d+(?:\.\d+)?)%\)")


# ---------------- rutas -------------------------------------------------------------------------
def _ancestors() -> list[Path]:
    root = paths.app_root()
    return [root, *root.parents]


def engine_exe() -> Path | None:
    cands = []
    if os.environ.get("AFO_DEMUCS_ENGINE"):
        cands.append(Path(os.environ["AFO_DEMUCS_ENGINE"]))
    cands.append(paths.app_root() / "motores" / "demucs" / EXE)
    if not paths.is_frozen():
        for p in _ancestors():
            cands += [p / "EXE" / "motores" / "demucs" / EXE,
                      p / ".cache" / "demucs.cpp" / "build-msvc" / "demucs_mt.cpp.main.exe"]
    return next((c for c in cands if c.is_file()), None)


def models_dir() -> Path:
    if os.environ.get("AFO_DEMUCS_MODELS"):
        return Path(os.environ["AFO_DEMUCS_MODELS"])
    if paths.is_frozen():
        return paths.app_root() / "modelos" / "demucs"
    for p in _ancestors():
        c = p / "EXE" / "modelos" / "demucs"
        if c.is_dir():
            return c
    return paths.user_data_dir() / "modelos" / "demucs"


def output_dir() -> Path:
    p = paths.media_dir() / "stems"
    p.mkdir(parents=True, exist_ok=True)
    return p


def status() -> dict:
    f = models_dir() / MODEL
    part = f.with_name(MODEL + ".parte")
    ready = f.is_file() and f.stat().st_size == MODEL_SIZE
    return {"engineOk": engine_exe() is not None, "modelOk": ready, "size": MODEL_SIZE,
            "got": MODEL_SIZE if ready else (part.stat().st_size if part.is_file() else 0),
            "sources": [n for _, n in SOURCES], "drumParts": list(DRUM_PARTS)}


# ---------------- audio ------------------------------------------------------------------------
def _load_44k(path: str) -> np.ndarray:
    """(muestras, 2) en float32 a 44,1 kHz."""
    import soundfile as sf
    from scipy.signal import resample_poly
    x, sr = sf.read(path, always_2d=True, dtype="float32")
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    x = x[:, :2]
    if sr != SR:
        g = np.gcd(int(sr), SR)
        x = resample_poly(x, SR // g, int(sr) // g, axis=0).astype("float32")
    return x


def rms_db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(np.square(x, dtype=np.float64))) + 1e-12))


def split_drums(x: np.ndarray, sr: int = SR) -> dict[str, np.ndarray]:
    """Batería → Bombo (graves), Caja / Clap (medios) y Platos (agudos) con máscaras complementarias
    en el espectro (cruces suaves en 90–180 Hz y 4,5–8 kHz). Suman exactamente la entrada."""
    from scipy.signal import istft, stft
    n = x.shape[0]
    f, _, z = stft(x.T, fs=sr, nperseg=2048, noverlap=1536)
    def ramp(lo, hi):            # 0 por debajo de lo, 1 por encima de hi, coseno en medio
        r = np.clip((f - lo) / (hi - lo), 0, 1)
        return 0.5 - 0.5 * np.cos(np.pi * r)
    high = ramp(4500, 8000)
    low = 1 - ramp(90, 180)
    mid = 1 - low - high
    out = {}
    for name, m in zip(DRUM_PARTS, (low, mid, high)):
        _, y = istft(z * m[None, :, None], fs=sr, nperseg=2048, noverlap=1536)
        y = y.T[:n]
        if y.shape[0] < n:
            y = np.pad(y, ((0, n - y.shape[0]), (0, 0)))
        out[name] = y.astype("float32")
    return out


# ---------------- servicio ---------------------------------------------------------------------
class _Cancelled(Exception):
    pass


def threads_for(seconds: float) -> int:
    """Hilos para un audio de `seconds`: uno por cada 5 s, de 1 a 8. Medido con demucs.cpp: 10,7 s con
    8 hilos se cae y 16 s con 3 hilos tarda 56 s (con 8, 85–99 s)."""
    return max(1, min(THREADS, int(seconds // SECONDS_PER_THREAD)))


def separate(exe: Path, x: np.ndarray, work: Path, cancel: threading.Event, progress, hold=None,
             last_log: list | None = None) -> dict[str, np.ndarray]:
    """Separa `x` ((muestras, 2) a 44,1 kHz) en las 6 fuentes de SOURCES, a la misma escala que `x`.
    Si el pico pasa de 0,99 se baja antes (el WAV de entrada es PCM de 24 bits) y se devuelve igual."""
    import soundfile as sf
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    gain = 0.99 / peak if peak > 0.99 else 1.0
    sf.write(str(work / "entrada.wav"), x * gain, SR, subtype="PCM_24")
    files = run_demucs(exe, work / "entrada.wav", work, cancel, progress, hold, last_log,
                       threads_for(x.shape[0] / SR))
    out = {}
    for (src, label), f in zip(SOURCES, files):
        if not f.is_file():
            raise RuntimeError(f"El separador no escribió «{label}»")
        y, _ = sf.read(str(f), always_2d=True, dtype="float32")
        if not np.isfinite(y).all():
            raise RuntimeError(f"El separador devolvió audio no válido en «{label}»")
        out[src] = y / gain
    return out


def run_demucs(exe: Path, wav: Path, work: Path, cancel: threading.Event, progress, hold=None,
               last_log: list | None = None, threads: int = THREADS) -> list[Path]:
    """Ejecuta el separador sobre `wav` (44,1 kHz estéreo) y deja `target_{i}_{fuente}.wav` en `work`.
    `progress(0..1)` recibe el avance; `hold(proc)` guarda el proceso para poder cancelarlo."""
    cmd = [str(exe), str(models_dir() / MODEL), str(wav), str(work), str(threads)]
    log.info("Stems: %s", " ".join(cmd))
    proc = subprocess.Popen(cmd, cwd=str(work), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
                            env={**os.environ, "PATH": str(exe.parent) + os.pathsep + os.environ.get("PATH", "")})
    if hold:
        hold(proc)
    per: dict[str, float] = {}
    last = 0.0
    with open(work / "demucs.log", "w", encoding="utf-8", errors="replace") as logf:
        for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            logf.write(line + "\n")
            if last_log is not None:
                last_log[:] = (last_log + [line])[-30:]
            m = _RE_PCT.search(line)
            if m:
                per[m.group(1)] = float(m.group(2))
                if time.monotonic() - last > 0.3:
                    last = time.monotonic()
                    progress(sum(per.values()) / (100.0 * max(len(per), threads)))
    code = proc.wait()
    if hold:
        hold(None)
    if cancel.is_set():
        raise _Cancelled()
    if code != 0:
        raise RuntimeError(f"El separador terminó con el código {code}")
    return [work / f"target_{i}_{src}.wav" for i, (src, _) in enumerate(SOURCES)]


class StemSeparator:
    """Descarga del modelo y separaciones, cada una en su hilo. Los eventos llevan type "stems"."""

    def __init__(self, emit):
        self.emit = emit
        self._job: threading.Thread | None = None
        self._dl: threading.Thread | None = None
        self._cancel = threading.Event()
        self._dl_cancel = threading.Event()
        self._proc: subprocess.Popen | None = None
        self.last_log: list[str] = []

    @property
    def busy(self) -> bool:
        return self._job is not None and self._job.is_alive()

    @property
    def downloading(self) -> bool:
        return self._dl is not None and self._dl.is_alive()

    def status(self) -> dict:
        return {**status(), "busy": self.busy, "downloading": self.downloading}

    # --- descarga (reanudable, como los modelos de ACE-Step) ---
    def download(self) -> None:
        if self.downloading:
            return
        self._dl_cancel.clear()
        self._dl = threading.Thread(target=self._download, name="stems-descarga", daemon=True)
        self._dl.start()

    def cancel_download(self) -> None:
        self._dl_cancel.set()

    def _download(self) -> None:
        mdir = models_dir()
        dest, part = mdir / MODEL, mdir / (MODEL + ".parte")
        try:
            mdir.mkdir(parents=True, exist_ok=True)
            have = part.stat().st_size if part.is_file() else 0
            req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "AllForOne"})
            if have:
                req.add_header("Range", f"bytes={have}-")
            with urllib.request.urlopen(req, timeout=30) as resp:
                if have and resp.status != 206:
                    have = 0
                last = 0.0
                with open(part, "ab" if have else "wb") as fh:
                    while chunk := resp.read(1 << 20):
                        if self._dl_cancel.is_set():
                            raise _Cancelled()
                        fh.write(chunk)
                        have += len(chunk)
                        if time.monotonic() - last > 0.25:
                            last = time.monotonic()
                            self.emit({"type": "stemsDownload", "phase": "progress", "progress": have / MODEL_SIZE,
                                       "message": f"Descargando el separador · {have / 1048576:.0f} de {MODEL_SIZE / 1048576:.0f} MB"})
            if have != MODEL_SIZE:
                raise RuntimeError(f"El modelo quedó incompleto ({have} de {MODEL_SIZE} bytes); vuelve a intentarlo")
            part.replace(dest)
            self.emit({"type": "stemsDownload", "phase": "done", "ok": True, "message": "Separador de stems instalado"})
        except _Cancelled:
            self.emit({"type": "stemsDownload", "phase": "done", "ok": False, "cancelled": True,
                       "message": "Descarga en pausa: «Descargar» la reanuda"})
        except Exception as exc:
            log.exception("Descarga del separador")
            self.emit({"type": "stemsDownload", "phase": "done", "ok": False, "error": f"No se pudo descargar: {exc}"})

    # --- separación ---
    def split(self, path: str, name: str, track_id: int = -1, drums: bool = False) -> dict:
        if self.busy:
            raise RuntimeError("Ya se está separando una pista.")
        exe = engine_exe()
        if exe is None:
            raise RuntimeError("Falta el separador (motores/demucs junto a AllForOne.exe).")
        if not status()["modelOk"]:
            raise RuntimeError("Falta el modelo del separador: descárgalo (55 MB).")
        if not path or not Path(path).is_file():
            raise RuntimeError("Esta pista no tiene un audio que separar.")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r"[^\w\- ]+", "", name).strip()[:40] or "pista"
        out = output_dir() / f"{stamp}_{safe}"
        self._cancel.clear()
        self._job = threading.Thread(target=self._split, args=(exe, path, name, out, track_id, drums),
                                     name="stems-separar", daemon=True)
        self._job.start()
        return {"folder": str(out)}

    def cancel(self) -> None:
        self._cancel.set()
        p = self._proc
        if p is not None and p.poll() is None:
            p.kill()

    def shutdown(self) -> None:
        self.cancel()
        self.cancel_download()

    def _progress(self, p: float, msg: str) -> None:
        self.emit({"type": "stems", "phase": "progress", "progress": p, "message": msg})

    def _split(self, exe: Path, path: str, name: str, out: Path, track_id: int, drums: bool) -> None:
        import soundfile as sf
        work = out / ".trabajo"
        t0 = time.monotonic()
        try:
            work.mkdir(parents=True, exist_ok=True)
            self._progress(0.02, "Preparando el audio")
            x = _load_44k(path)
            secs = x.shape[0] / SR
            def hold(proc):
                self._proc = proc
            self.last_log = []
            sep = separate(exe, x, work, self._cancel, lambda d: self._progress(0.05 + 0.85 * d, "Separando con Demucs"),
                           hold, self.last_log)
            self._progress(0.92, "Guardando las pistas")
            stems, silent = [], []
            for src, label in SOURCES:
                y = sep[src]
                db = rms_db(y)
                if db < SILENT_DB:
                    silent.append(label)
                    continue
                parts = split_drums(y) if drums and src == "drums" else {label: y}
                for pl, py in parts.items():
                    pdb = rms_db(py)
                    if pdb < SILENT_DB:
                        silent.append(pl)
                        continue
                    dest = out / f"{name} - {pl}.wav".replace("/", "-")
                    sf.write(str(dest), py, SR, subtype="FLOAT")
                    stems.append({"label": pl, "path": str(dest), "rms_db": round(pdb, 1)})
            import shutil
            shutil.rmtree(work, ignore_errors=True)
            secs_run = round(time.monotonic() - t0, 1)
            self.emit({"type": "stems", "phase": "done", "ok": True, "trackId": track_id, "name": name,
                       "stems": stems, "silent": silent, "seconds": secs_run, "progress": 1.0,
                       "message": f"«{name}» separada en {len(stems)} pistas en {secs_run:.0f} s ({secs:.0f} s de audio)"
                                  + (f" · en silencio: {', '.join(silent)}" if silent else "")})
        except _Cancelled:
            import shutil
            shutil.rmtree(out, ignore_errors=True)
            self.emit({"type": "stems", "phase": "done", "ok": False, "cancelled": True, "message": "Separación cancelada"})
        except Exception as exc:
            log.exception("Separación de stems (registro en %s)", work)
            self.emit({"type": "stems", "phase": "done", "ok": False, "error": f"No se pudo separar: {exc}"})

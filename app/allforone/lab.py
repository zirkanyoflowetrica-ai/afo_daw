"""Instrumental Lab: la instrumental se construye por piezas (docs/INSTRUMENTAL_LAB.md).

Una sesión del laboratorio tiene un contexto musical común (tempo, compás, tonalidad, compases,
estilo y descripción) y una fila por familia (Batería, Bajo, Piano…) con sus variantes V1…Vn.
Todo es real y corre en el equipo:
  * Guía: ACE-Step compone una canción del contexto (`text2music`) o se usa el audio del proyecto.
    Demucs la separa y cada fuente es la V1 de su familia: todas nacen de la misma canción.
  * Variantes: ACE-Step `lego` (modelo base) de la clase de la familia sobre el contexto, que es la
    mezcla de las variantes elegidas en las demás familias (o la guía sin esa familia). Cada una
    lleva su semilla.
  * «Parecida»: ACE-Step `cover` con la variante como fuente.
  * Todas las variantes duran exactamente los compases del contexto y empiezan en el compás 1.
Los motores corren en procesos aparte, uno a la vez, en una cola cancelable. Por el puente solo
viajan textos y el estado; el audio va de archivo a archivo en `datos/media/lab/<sesión>/`.
"""
from __future__ import annotations

import json
import logging
import math
import os
import queue
import random
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import ai_music as A
from . import hardware as H
from . import paths, procs
from . import stems as S

log = logging.getLogger("allforone.lab")

SR = S.SR
VERSION = 1
# Familias: nombre visible → (parte de ACE-Step en ai_music.PARTS, fuente de Demucs para la V1 de la guía)
FAMILIES = {
    "Batería": ("Batería", "drums"),
    "Bajo": ("Bajo", "bass"),
    "Piano / teclados": ("Piano / teclados", "piano"),
    "Guitarra": ("Guitarra", "guitar"),
    "Sintetizador": ("Sintetizador", None),
    "Cuerdas": ("Cuerdas", None),
    "Metales": ("Metales", None),
    "Maderas": ("Maderas", None),
    "Percusión": ("Percusión", None),
}
# Familias que se proponen al crear una sesión de cada estilo
DEFAULT_FAMILIES = {
    "Hip hop": ["Batería", "Bajo", "Piano / teclados"],
    "Trap": ["Batería", "Bajo", "Sintetizador"],
    "Lo-fi": ["Batería", "Bajo", "Piano / teclados"],
    "House": ["Batería", "Bajo", "Sintetizador"],
    "Cinemático": ["Percusión", "Cuerdas", "Piano / teclados", "Metales"],
    "Rock": ["Batería", "Bajo", "Guitarra"],
}
FIELDS = ("chosen", "locked", "favorite")
# «A tempo»: cuántas veces más caen los ataques en la rejilla de corcheas del contexto que por azar.
# Medido (trap a 140): la batería real da 3,75; las generadas que siguen el tempo, 2,95–3,8; las que
# no, 1,2–1,6. Las familias rítmicas se reintentan con otra semilla si quedan por debajo.
ON_GRID = 2.0
RHYTHMIC = ("Batería", "Percusión")
RETRIES = 2
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def lab_dir() -> Path:
    p = paths.media_dir() / "lab"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------- contexto y audio ---------------------------------------------------------------
def make_context(opts: dict) -> dict:
    style = str(opts.get("style") or "Libre")
    if style not in A.STYLES:
        raise ValueError(f"Estilo desconocido: {style}")
    key = str(opts.get("key") or "Auto")
    if key not in A.KEYS:
        raise ValueError(f"Tonalidad desconocida: {key}")
    bpm = float(opts.get("bpm") or 90)
    if not 40 <= bpm <= 220:
        raise ValueError("El tempo va de 40 a 220 BPM")
    beats = int(opts.get("beats") or 4)
    if beats not in (3, 4, 6):
        raise ValueError("Compás: 3, 4 o 6 tiempos")
    bars = int(opts.get("bars") or 8)
    seconds = bars * beats * 60.0 / bpm
    if not 5.0 <= seconds <= 240.0:
        raise ValueError(f"{bars} compases a {bpm:g} BPM son {seconds:.0f} s: el laboratorio trabaja de 5 a 240 s")
    return {"prompt": str(opts.get("prompt") or "").strip(), "style": style, "bpm": round(bpm, 2), "key": key,
            "beats": beats, "bars": bars, "seconds": round(seconds, 4),
            "variants": max(1, min(8, int(opts.get("variants") or 4)))}


def n_samples(ctx: dict) -> int:
    return int(round(ctx["bars"] * ctx["beats"] * 60.0 / ctx["bpm"] * SR))


def fit(x: np.ndarray, n: int) -> np.ndarray:
    """Recorta o completa con silencio a `n` muestras exactas, con fundidos cortos en los bordes."""
    y = np.zeros((n, 2), dtype="float32")
    m = min(n, x.shape[0])
    y[:m] = x[:m]
    fi, fo = min(64, n), min(int(0.005 * SR), n)
    y[:fi] *= np.linspace(0, 1, fi, dtype="float32")[:, None]
    y[n - fo:] *= np.linspace(1, 0, fo, dtype="float32")[:, None]
    return y


def disc(x: np.ndarray) -> dict:
    """Lo que dibuja el disco de una variante, sacado de su audio: envolvente (48 surcos) y la
    energía de 8 bandas (el color del disco). Dos variantes distintas se ven distintas."""
    mono = x.mean(axis=1)
    seg = np.array_split(mono, 48)
    env = np.array([math.sqrt(float(np.mean(s ** 2))) if len(s) else 0.0 for s in seg])
    env = env / (env.max() + 1e-9)
    spec = np.abs(np.fft.rfft(mono[: min(len(mono), SR * 30)]))
    f = np.fft.rfftfreq(min(len(mono), SR * 30), 1.0 / SR)
    edges = [20, 80, 200, 500, 1200, 2500, 5000, 10000, 20000]
    bands = np.array([float(np.sum(spec[(f >= lo) & (f < hi)] ** 2)) for lo, hi in zip(edges, edges[1:])])
    bands = bands / (bands.sum() + 1e-12)
    return {"env": [round(float(v), 3) for v in env], "bands": [round(float(v), 4) for v in bands],
            "rms_db": round(S.rms_db(x), 1)}


def grid_score(x: np.ndarray, bpm: float, div: int = 2) -> float:
    """Concentración de los ataques (flujo de energía, 10 ms) en la rejilla de 1/`div` de tiempo a
    `bpm`, con la mejor fase: 1 = azar; una batería a tempo da 3–4."""
    m = x.mean(axis=1)
    if len(m) < 2048:
        return 0.0
    fr = np.lib.stride_tricks.sliding_window_view(m, 1024)[::441]
    e = np.log1p(1e3 * np.mean(fr ** 2, axis=1))
    o = np.maximum(0.0, np.diff(e))
    if o.sum() <= 0:
        return 0.0
    step = 60.0 / bpm / div / 0.01
    k = np.arange(len(o))
    best = 0.0
    for ph in np.arange(0.0, step, 0.5):
        d = np.abs(((k - ph + step / 2) % step) - step / 2)      # distancia a la línea más cercana
        mask = d <= 2.0
        if mask.any():
            best = max(best, float(o[mask].sum() / o.sum() / mask.mean()))
    return round(best, 2)


HIT_LANES = {"Bombo": 0, "Caja / Clap": 1, "Platos": 6}   # golpe suelto → carril de la Batería (Sequencer.dn)


def cut_hit(x: np.ndarray, max_s: float = 0.8) -> np.ndarray | None:
    """El golpe más fuerte de una parte de batería: desde 5 ms antes de su ataque hasta el siguiente
    ataque (o `max_s`), con fundido de salida de 20 ms y pico a −1 dBFS. None si no hay golpes."""
    m = np.abs(x).max(axis=1)
    hop = 441
    n = len(m) // hop
    if n < 4:
        return None
    env = m[: n * hop].reshape(n, hop).max(axis=1)
    if env.max() < 10 ** (S.SILENT_DB / 20):
        return None
    rise = np.diff(env, prepend=0.0)
    thr = 0.3 * rise.max()
    onsets = [i for i in range(1, n) if rise[i] >= thr and rise[i] >= rise[i - 1] and (i + 1 >= n or rise[i] >= rise[i + 1])]
    if not onsets:
        return None
    best = max(onsets, key=lambda i: env[i:i + 5].max())
    nxt = [i for i in onsets if i > best + 2]
    start = max(0, best * hop - int(0.005 * SR))
    end = min(len(x), start + int(max_s * SR), (nxt[0] * hop) if nxt else len(x))
    y = x[start:end].copy()
    fo = min(len(y), int(0.02 * SR))
    y[len(y) - fo:] *= np.linspace(1, 0, fo, dtype="float32")[:, None]
    peak = float(np.abs(y).max())
    return (y * (10 ** (-1 / 20) / peak)).astype("float32") if peak > 0 else None


def _write(path: Path, x: np.ndarray) -> None:
    import soundfile as sf
    sf.write(str(path), x, SR, subtype="FLOAT")


def _read(path: Path) -> np.ndarray:
    return S._load_44k(str(path))


class _Cancelled(Exception):
    pass


# ---------------- servicio ---------------------------------------------------------------------
class Lab:
    """Una sesión abierta a la vez y una cola de trabajos (un motor de IA a la vez)."""

    def __init__(self, emit, others_busy=lambda: False):
        self.emit = emit
        self.others_busy = others_busy
        self.folder: Path | None = None
        self.state: dict | None = None
        self._lock = threading.RLock()
        self._jobs: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = ""
        self._cancel = threading.Event()
        self._proc: subprocess.Popen | None = None
        self.last_log: list[str] = []

    # --- estado ---
    @property
    def busy(self) -> bool:
        return bool(self._running) or not self._jobs.empty()

    def status(self) -> dict:
        return {"engineOk": A.engine_dir() is not None, "textOk": A.pack_for_use() is not None,
                "legoOk": A.pack_status("partes")["installed"],
                "demucsOk": S.status()["engineOk"] and S.status()["modelOk"],
                "families": list(FAMILIES), "defaults": DEFAULT_FAMILIES, "styles": list(A.STYLES),
                "keys": A.KEYS, "busy": self.busy, "running": self._running, "folder": str(self.folder or "")}

    def public(self) -> dict | None:
        """El estado para la interfaz: rutas absolutas y etiquetas V1…Vn."""
        with self._lock:
            if self.state is None:
                return None
            st = json.loads(json.dumps(self.state))
        root = self.folder
        def absp(v):
            v["path"] = str(root / v["path"])
            v["parts"] = {k: str(root / p) for k, p in v.get("parts", {}).items()}
            return v
        for fam in st["families"]:
            for i, v in enumerate(fam["variants"]):
                absp(v)["label"] = f"V{i + 1}"
                v["chosen"] = v["id"] == fam.get("chosen")
        for v in st["history"]:
            absp(v)
        if st.get("oneshots"):
            st["oneshots"]["hits"] = {k: str(root / p) for k, p in st["oneshots"]["hits"].items()}
        if st.get("guide"):
            st["guide"]["path"] = str(root / st["guide"]["path"])
        st.update(folder=str(root), busy=self.busy, running=self._running)
        return st

    def _changed(self) -> None:
        self._save()
        self.emit({"type": "labState", "state": self.public()})

    def _save(self) -> None:
        with self._lock:
            if self.state is None:
                return
            tmp = self.folder / "lab.json.tmp"
            tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.folder / "lab.json")

    # --- sesiones ---
    def new(self, opts: dict) -> dict:
        if self.busy:
            raise RuntimeError("El laboratorio está generando: espera o cancela.")
        ctx = make_context(opts)
        fams = list(opts.get("families") or DEFAULT_FAMILIES.get(ctx["style"], ["Batería", "Bajo", "Piano / teclados"]))
        for f in fams:
            if f not in FAMILIES:
                raise ValueError(f"Familia desconocida: {f}")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = str(opts.get("name") or "").strip() or (ctx["style"] if ctx["style"] != "Libre" else "Instrumental")
        base = lab_dir() / f"{stamp}_{A.slug(name)}"
        folder, k = base, 2
        while folder.exists():                    # dos sesiones con el mismo nombre en el mismo segundo
            folder, k = base.with_name(f"{base.name}_{k}"), k + 1
        folder.mkdir(parents=True)
        with self._lock:
            self.folder = folder
            self.state = {"version": VERSION, "name": name, "created": stamp, "context": ctx, "guide": None,
                          "next": 1, "history": [],
                          "families": [{"name": f, "chosen": None, "reference": False, "variants": []} for f in dict.fromkeys(fams)]}
        self._changed()
        return self.public()

    def open(self, folder: str) -> dict:
        if self.busy:
            raise RuntimeError("El laboratorio está generando: espera o cancela.")
        p = Path(folder)
        st = json.loads((p / "lab.json").read_text(encoding="utf-8"))
        if st.get("version") != VERSION:
            raise RuntimeError("Sesión del laboratorio de otra versión")
        with self._lock:
            self.folder, self.state = p, st
        return self.public()

    @staticmethod
    def sessions(limit: int = 40) -> list[dict]:
        out = []
        for f in sorted(lab_dir().glob("*/lab.json"), reverse=True)[:limit]:
            try:
                st = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            c = st.get("context", {})
            out.append({"folder": str(f.parent), "name": st.get("name", ""), "created": st.get("created", ""),
                        "style": c.get("style", ""), "bpm": c.get("bpm"), "key": c.get("key"), "bars": c.get("bars"),
                        "variants": sum(len(x["variants"]) for x in st.get("families", []))})
        return out

    @staticmethod
    def favorites() -> list[dict]:
        """Las variantes marcadas como favoritas en todas las sesiones (para reutilizarlas)."""
        out = []
        for f in sorted(lab_dir().glob("*/lab.json"), reverse=True):
            try:
                st = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            for fam in st.get("families", []):
                for v in fam["variants"]:
                    if v.get("favorite"):
                        out.append({"family": fam["name"], "session": st.get("name", ""), "path": str(f.parent / v["path"]),
                                    "bpm": st["context"]["bpm"], "key": st["context"]["key"], "id": v["id"]})
        return out

    # --- edición (inmediata) ---
    def _family(self, name: str) -> dict:
        if self.state is None:
            raise RuntimeError("Abre o crea una sesión del laboratorio")
        for f in self.state["families"]:
            if f["name"] == name:
                return f
        raise ValueError(f"La sesión no tiene la familia «{name}»")

    def _variant(self, fam: dict, vid: str) -> dict:
        for v in fam["variants"]:
            if v["id"] == vid:
                return v
        raise ValueError("Esa variante ya no está")

    def set_flag(self, family: str, vid: str, field: str, value: bool) -> dict:
        if field not in FIELDS:
            raise ValueError(f"Campo desconocido: {field}")
        with self._lock:
            fam = self._family(family)
            v = self._variant(fam, vid)
            if field == "chosen":
                fam["chosen"] = vid if value else None
            else:
                v[field] = bool(value)
        self._changed()
        return self.public()

    def set_reference(self, family: str, value: bool) -> dict:
        with self._lock:
            self._family(family)["reference"] = bool(value)
        self._changed()
        return self.public()

    def add_family(self, family: str) -> dict:
        if family not in FAMILIES:
            raise ValueError(f"Familia desconocida: {family}")
        with self._lock:
            if self.state is None:
                raise RuntimeError("Abre o crea una sesión del laboratorio")
            if all(f["name"] != family for f in self.state["families"]):
                self.state["families"].append({"name": family, "chosen": None, "reference": False, "variants": []})
        self._changed()
        return self.public()

    def remove(self, family: str, vid: str) -> dict:
        """Quita una variante: su audio va a la papelera de la sesión (se puede recuperar a mano)."""
        with self._lock:
            fam = self._family(family)
            v = self._variant(fam, vid)
            trash = self.folder / ".papelera"
            trash.mkdir(exist_ok=True)
            for rel in [v["path"], *v.get("parts", {}).values()]:
                src = self.folder / rel
                if src.is_file():
                    src.replace(trash / src.name)
            fam["variants"].remove(v)
            if fam["chosen"] == vid:
                fam["chosen"] = fam["variants"][0]["id"] if fam["variants"] else None
        self._changed()
        return self.public()

    # --- preescucha y envío al proyecto (C9) ---
    def chosen(self) -> list[dict]:
        """Variante elegida de cada familia que tenga alguna: {family, id, path}."""
        with self._lock:
            if self.state is None:
                return []
            return [{"family": f["name"], "id": f["chosen"], "path": str(self.folder / self._variant(f, f["chosen"])["path"])}
                    for f in self.state["families"] if f["chosen"]]

    def send_copy(self, family: str, vid: str) -> Path:
        """Copia la variante a `enviadas/` de la sesión: lo que va al proyecto no depende de que la
        variante se regenere o vaya a la papelera."""
        v = self._variant(self._family(family), vid)
        dest = self.folder / "enviadas" / Path(v["path"]).name
        dest.parent.mkdir(exist_ok=True)
        if not dest.is_file():
            shutil.copy2(self.folder / v["path"], dest)
        return dest

    def one_shots(self, family: str = "Batería") -> dict:
        """Golpes sueltos (bombo, caja / clap, platos) cortados de la batería elegida: el golpe más
        fuerte de cada parte, del ataque al siguiente (máx. 0,8 s), con fundido y pico a −1 dBFS."""
        with self._lock:
            fam = self._family(family)
            if not fam["chosen"]:
                raise RuntimeError(f"Elige una variante de {family}")
            v = self._variant(fam, fam["chosen"])
            if not v.get("parts"):
                raise RuntimeError(f"La variante de {family} no está dividida en partes")
            out = {}
            folder = self.folder / "golpes"
            folder.mkdir(exist_ok=True)
            for label, rel in v["parts"].items():
                hit = cut_hit(_read(self.folder / rel))
                if hit is None:
                    continue
                dest = folder / f"{A.slug(label)}_{v['id']}.wav"
                _write(dest, hit)
                out[label] = str(dest.relative_to(self.folder)).replace("\\", "/")
            self.state["oneshots"] = {"from": v["id"], "family": family, "hits": out}
        self._changed()
        return {k: str(self.folder / p) for k, p in out.items()}

    def hit_lanes(self) -> list[str]:
        """Los golpes sueltos en los carriles de la Batería (Bombo → Bombo, Caja / Clap → Caja,
        Platos → Platillo); "" en los carriles sin golpe."""
        lanes = [""] * 8
        with self._lock:
            hits = ((self.state or {}).get("oneshots") or {}).get("hits") or {}
            for label, rel in hits.items():
                if label in HIT_LANES:
                    lanes[HIT_LANES[label]] = str(self.folder / rel)
        return lanes

    # --- trabajos (cola) ---
    def _check_engines(self, need: str) -> None:
        if self.state is None:
            raise RuntimeError("Abre o crea una sesión del laboratorio")
        if self.others_busy():
            raise RuntimeError("Otra tarea de IA está en marcha (generación o separación): espera a que termine.")
        st = self.status()
        if not st["engineOk"]:
            raise RuntimeError("Falta el motor de IA (motores/acestep junto a AllForOne.exe).")
        if need == "text" and not st["textOk"]:
            raise RuntimeError("Faltan los modelos del compositor: instálalos en «Modelos de IA».")
        if need in ("lego", "cover") and not st["legoOk"]:
            raise RuntimeError("Falta el sintetizador base: instálalo en «Modelos de IA» (Partes).")
        if need in ("text", "audio") and not st["demucsOk"]:
            raise RuntimeError("Falta el separador Demucs o su modelo (botón «Dividir» de una pista).")

    def _queue(self, kind: str, *args) -> dict:
        self._cancel.clear()
        self._jobs.put((kind, args))
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._loop, name="lab", daemon=True)
            self._worker.start()
        self.emit({"type": "labState", "state": self.public()})
        return {"queued": self._jobs.qsize() + (1 if self._running else 0)}

    def guide_text(self) -> dict:
        self._check_engines("text")
        return self._queue("guide_text")

    def guide_audio(self, path: str) -> dict:
        self._check_engines("audio")
        if not Path(path).is_file():
            raise RuntimeError("No hay audio para la guía")
        return self._queue("guide_audio", str(path))

    def generate(self, family: str, n: int = 0) -> dict:
        self._check_engines("lego")
        fam = self._family(family)
        n = n or max(1, self.state["context"]["variants"] - len(fam["variants"]))
        return self._queue("lego", family, int(n))

    def regenerate(self, family: str) -> dict:
        """Las variantes no bloqueadas pasan al historial y se generan otras con semillas nuevas."""
        self._check_engines("lego")
        with self._lock:
            fam = self._family(family)
            keep = [v for v in fam["variants"] if v.get("locked")]
            gone = [v for v in fam["variants"] if not v.get("locked")]
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.state["history"] += [{**v, "family": family, "replaced": stamp} for v in gone]
            fam["variants"] = keep
            if fam["chosen"] not in {v["id"] for v in keep}:
                fam["chosen"] = keep[0]["id"] if keep else None
            n = max(1, self.state["context"]["variants"] - len(keep))
        self._save()
        return self._queue("lego", family, n)

    def similar(self, family: str, vid: str, strength: float = 0.5) -> dict:
        self._check_engines("cover")
        self._variant(self._family(family), vid)
        return self._queue("cover", family, vid, float(strength))

    def cancel(self) -> None:
        self._cancel.set()
        while not self._jobs.empty():
            try:
                self._jobs.get_nowait()
            except queue.Empty:
                break
        p = self._proc
        if p is not None and p.poll() is None:
            p.kill()

    def shutdown(self) -> None:
        self.cancel()

    def _loop(self) -> None:
        while True:
            try:
                kind, args = self._jobs.get(timeout=0.5)
            except queue.Empty:
                return
            self._running = kind
            work = self.folder / f".trabajo_{kind}"
            t0 = time.monotonic()
            try:
                if work.exists():
                    shutil.rmtree(work, ignore_errors=True)
                work.mkdir(parents=True)
                msg = getattr(self, "_job_" + kind)(work, *args)
                shutil.rmtree(work, ignore_errors=True)
                self._running = ""
                self.emit({"type": "labJob", "phase": "done", "ok": True, "job": kind, "progress": 1.0,
                           "message": f"{msg} en {time.monotonic() - t0:.0f} s"})
            except _Cancelled:
                shutil.rmtree(work, ignore_errors=True)
                self._running = ""
                self.emit({"type": "labJob", "phase": "done", "ok": False, "cancelled": True, "job": kind,
                           "message": "Laboratorio: cancelado"})
            except Exception as exc:
                log.exception("Laboratorio: %s (registro en %s)", kind, work)
                self._running = ""
                self.emit({"type": "labJob", "phase": "done", "ok": False, "job": kind,
                           "error": f"Laboratorio: {exc}", "log": str(work)})
            finally:
                self._running = ""
                self._changed()

    def _progress(self, p: float, msg: str, family: str = "") -> None:
        self.emit({"type": "labJob", "phase": "progress", "progress": round(p, 3), "message": msg, "family": family})

    def _run(self, exe: Path, args: list[str], cwd: Path, stage: str, duration: float, base: float, span: float,
             family: str = "") -> None:
        if self._cancel.is_set():
            raise _Cancelled()
        job = "synth" if stage == "synth" else "lm:" + (A.pack_for_use() or "ligero")
        H.GUARD.before(job, self._cancel, lambda m: self._progress(base, m, family))
        if self._cancel.is_set():
            raise _Cancelled()
        cmd = [str(exe), *args, *H.engine_args(stage)]
        t0 = time.monotonic()
        log.info("Lab: %s", " ".join(cmd))
        self._proc = procs.spawn(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
                                      env={**os.environ, "PATH": str(exe.parent) + os.pathsep + os.environ.get("PATH", "")})
        self.last_log = []
        with open(cwd / f"{stage}.log", "a", encoding="utf-8", errors="replace") as logf:
            for raw in self._proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                logf.write(line + "\n")
                self.last_log = (self.last_log + [line])[-40:]
                pr = A.progress_of(line, stage, duration)
                if pr:
                    # progress_of da 0..0,42 para el compositor y 0,46..1 para el sintetizador
                    frac = pr[0] / 0.42 if stage == "lm" else (pr[0] - 0.46) / 0.54
                    self._progress(base + span * max(0.0, min(1.0, frac)), pr[1], family)
        code = self._proc.wait()
        self._proc = None
        H.GUARD.after(time.monotonic() - t0)
        if self._cancel.is_set():
            raise _Cancelled()
        if code != 0:
            tail = next((x for x in reversed(self.last_log) if "FATAL" in x or "ERROR" in x or "error" in x), "")
            raise RuntimeError(f"{exe.name} terminó con el código {code}. {tail}".strip())

    # --- variantes ---
    def _add_variant(self, family: str, x: np.ndarray, task: str, seed: int, request: dict | None,
                     extra: dict | None = None) -> dict:
        with self._lock:
            vid = f"v{self.state['next']}"
            self.state["next"] += 1
            rel = f"{A.slug(family)}_{vid}.wav"
            _write(self.folder / rel, x)
            v = {"id": vid, "path": rel, "task": task, "seed": seed, "created": datetime.now().strftime("%Y%m%d_%H%M%S"),
                 "locked": False, "favorite": False, "request": request, "disc": disc(x), "parts": {}}
            g = grid_score(x, self.state["context"]["bpm"])
            v["grid"] = g
            v["onGrid"] = g >= ON_GRID
            v.update(extra or {})
            if FAMILIES[family][1] == "drums":
                for label, y in S.split_drums(x).items():
                    if S.rms_db(y) > S.SILENT_DB:
                        prel = f"{A.slug(family)}_{vid}_{A.slug(label)}.wav"
                        _write(self.folder / prel, y)
                        v["parts"][label] = prel
            fam = self._family(family)
            fam["variants"].append(v)
            if fam["chosen"] is None:
                fam["chosen"] = vid
        self._changed()
        return v

    def _guide_from(self, work: Path, x: np.ndarray, source: str) -> str:
        """Guarda la guía, la separa con Demucs y crea la V1 de cada familia que tenga fuente."""
        n = n_samples(self.state["context"])
        g = fit(x, n)
        _write(self.folder / "guia.wav", g)
        def hold(p):
            self._proc = p
        sep = S.separate(S.engine_exe(), g, work, self._cancel,
                         lambda d: self._progress(0.45 + 0.45 * d, "Separando la guía con Demucs"), hold)
        stems_rel = {}
        (self.folder / "guia").mkdir(exist_ok=True)
        for src, _ in S.SOURCES:
            y = fit(sep[src], n)
            rel = f"guia/{src}.wav"
            _write(self.folder / rel, y)
            stems_rel[src] = {"path": rel, "rms_db": round(S.rms_db(y), 1)}
        with self._lock:
            self.state["guide"] = {"path": "guia.wav", "source": source, "stems": stems_rel}
        made = []
        for fam in list(self.state["families"]):
            src = FAMILIES[fam["name"]][1]
            if src and stems_rel[src]["rms_db"] > S.SILENT_DB:
                self._add_variant(fam["name"], _read(self.folder / stems_rel[src]["path"]), "guia", -1, None)
                made.append(fam["name"])
        return f"Guía lista; V1 de {', '.join(made) if made else 'ninguna familia (la guía no las tiene)'}"

    def _job_guide_text(self, work: Path) -> str:
        ctx = self.state["context"]
        pack = A.pack_for_use()
        opts = {"prompt": ctx["prompt"], "style": ctx["style"], "bpm": ctx["bpm"], "key": ctx["key"],
                "duration": math.ceil(ctx["seconds"]), "instrumental": True, "seed": random.randint(1, 2 ** 31 - 1)}
        if not ctx["prompt"] and ctx["style"] == "Libre":
            opts["prompt"] = "instrumental"
        req = A.build_request(opts, pack)
        req["duration"] = max(10, math.ceil(ctx["seconds"]))
        req["timesignature"] = str(ctx["beats"])
        (work / "req.json").write_text(json.dumps(req, ensure_ascii=False, indent=1), encoding="utf-8")
        mdir = str(A.models_dir())
        eng = A.engine_dir()
        self._progress(0.02, "Componiendo la guía")
        self._run(eng / A.ENGINE_EXES[0], ["--models", mdir, "--request", "req.json"], work, "lm", req["duration"], 0.02, 0.2)
        self._run(eng / A.ENGINE_EXES[1], ["--models", mdir, "--request", "req0.json"], work, "synth", req["duration"], 0.22, 0.22)
        wav = work / "req00.wav"
        if not wav.is_file():
            raise RuntimeError("El sintetizador no escribió la guía")
        with self._lock:
            self.state["guideRequest"] = req
        return self._guide_from(work, _read(wav), "text2music")

    def _job_guide_audio(self, work: Path, path: str) -> str:
        self._progress(0.05, "Preparando la guía")
        return self._guide_from(work, _read(Path(path)), "audio")

    def context_mix(self, family: str) -> np.ndarray:
        """Lo que escucha el modelo al crear una variante de `family`: las variantes elegidas de las
        demás familias (solo las de referencia, si hay alguna), o la guía sin esa familia."""
        n = n_samples(self.state["context"])
        others = [f for f in self.state["families"] if f["name"] != family and f["chosen"]]
        use = [f for f in others if f.get("reference")] or others
        if use:
            mix = np.zeros((n, 2), dtype="float32")
            for f in use:
                mix += fit(_read(self.folder / self._variant(f, f["chosen"])["path"]), n)
        elif self.state.get("guide"):
            g = self.state["guide"]
            mix = fit(_read(self.folder / g["path"]), n)
            src = FAMILIES[family][1]
            if src:
                mix = mix - fit(_read(self.folder / g["stems"][src]["path"]), n)
        else:
            raise RuntimeError("Primero hace falta una guía o una variante de otra familia")
        peak = float(np.max(np.abs(mix)))
        return mix * (0.9 / peak) if peak > 0.9 else mix

    def _synth(self, work: Path, req: dict, src: Path, family: str, base: float, span: float) -> np.ndarray:
        (work / "req.json").write_text(json.dumps(req, ensure_ascii=False, indent=1), encoding="utf-8")
        out = work / "req0.wav"
        if out.exists():
            out.unlink()
        self._run(A.engine_dir() / A.ENGINE_EXES[1], ["--models", str(A.models_dir()), "--request", "req.json",
                                                      "--src-audio", str(src)], work, "synth", req["duration"], base, span, family)
        if not out.is_file():
            raise RuntimeError("El sintetizador no escribió el audio")
        return fit(_read(out), n_samples(self.state["context"]))

    def _part_request(self, family: str, seed: int) -> dict:
        ctx = self.state["context"]
        req = A.build_part_request({"part": FAMILIES[family][0], "style": ctx["style"], "prompt": ctx["prompt"],
                                    "duration": math.ceil(ctx["seconds"]), "seed": seed, "bpm": ctx["bpm"],
                                    "key": ctx["key"]})
        # El tempo también en la descripción: con él, 2 de 3 baterías de trap siguen los 140 BPM; sin él, 0 de 2
        req["caption"] = f"{ctx['bpm']:g} bpm, {req['caption']}"
        return req

    def _job_lego(self, work: Path, family: str, n: int) -> str:
        src = work / "contexto.wav"
        _write(src, self.context_mix(family))
        bpm = self.state["context"]["bpm"]
        off = 0
        for i in range(n):
            best = None
            tries = 1 + (RETRIES if family in RHYTHMIC else 0)
            for t in range(tries):
                seed = random.randint(1, 2 ** 31 - 1)
                req = self._part_request(family, seed)
                self._progress(i / n, f"{family}: variante {i + 1} de {n}" + (f" (otra vez: no iba a tempo)" if t else ""), family)
                x = self._synth(work, req, src, family, i / n, 1 / n)
                g = grid_score(x, bpm)
                if best is None or g > best[0]:
                    best = (g, x, seed, req, t + 1)
                if g >= ON_GRID:
                    break
            g, x, seed, req, used = best
            self._add_variant(family, x, "lego", seed, req, {"tries": used})
            off += family in RHYTHMIC and g < ON_GRID
        msg = f"{family}: {n} variante{'s' if n != 1 else ''} nueva{'s' if n != 1 else ''}"
        return msg + (f" ({off} sin seguir del todo el tempo)" if off else "")

    def _job_cover(self, work: Path, family: str, vid: str, strength: float) -> str:
        v = self._variant(self._family(family), vid)
        seed = random.randint(1, 2 ** 31 - 1)
        req = self._part_request(family, seed)
        req.update(task_type="cover", audio_cover_strength=max(0.1, min(1.0, strength)))
        req.pop("track", None)
        self._progress(0.0, f"{family}: parecida a la variante", family)
        x = self._synth(work, req, self.folder / v["path"], family, 0.0, 1.0)
        nv = self._add_variant(family, x, "cover", seed, {**req, "from": vid})
        return f"{family}: variante parecida ({nv['id']})"

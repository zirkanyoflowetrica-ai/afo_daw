"""Generador de instrumentales con IA local (ACE-Step 1.5 por acestep.cpp, GGML + Vulkan).

Todo corre en el equipo, dentro de AllForOne y sin programas aparte (como Folio):
  * El motor son los ejecutables de acestep.cpp (`ace-lm`, `ace-synth` y las DLL de GGML), compilados
    con Vulkan y copiados en `motores/acestep` junto a AllForOne.exe (`tools/build_acestep.bat`).
  * Los modelos GGUF se descargan desde la propia aplicación a `modelos/acestep` junto al exe
    (descarga reanudable: `.parte` + cabecera Range, como Folio).
  * Generar es: `ace-lm` escribe letra/metadatos/códigos de audio y `ace-synth` los convierte en un WAV
    estéreo de 48 kHz. Cada paso es un proceso aparte (si falla o se cancela, AllForOne sigue en pie) y
    por el puente solo viajan textos de avance, nunca audio.
  * El WAV resultante se carga como pista de audio normal del motor (Pistas, mezclador, efectos).

Los eventos (`emit(dict)`) salen de hilos de trabajo; el puente los reenvía desde el hilo de Qt.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from . import hardware as H, paths, procs

log = logging.getLogger("allforone.ia")

HF_REPO = "Serveurperso/ACE-Step-1.5-GGUF"
HF_URL = "https://huggingface.co/{repo}/resolve/main/{name}"
ENGINE_EXES = ("ace-lm.exe", "ace-synth.exe") if os.name == "nt" else ("ace-lm", "ace-synth")
ENGINE_DLLS = ("ggml.dll", "ggml-base.dll", "ggml-cpu.dll", "ggml-vulkan.dll") if os.name == "nt" else ()

# Tamaños exactos en bytes (lista del repositorio en Hugging Face): sirven para comprobar la descarga.
FILES = {
    "Qwen3-Embedding-0.6B-Q8_0.gguf": (784144960, "Codificador de texto"),
    "acestep-5Hz-lm-4B-Q8_0.gguf": (4457323648, "Compositor 4B (letra, estructura y códigos)"),
    "acestep-5Hz-lm-1.7B-Q8_0.gguf": (1975837568, "Compositor 1,7B (letra, estructura y códigos)"),
    "acestep-v15-turbo-Q8_0.gguf": (2549528000, "Sintetizador DiT turbo (8 pasos)"),
    "vae-BF16.gguf": (337420928, "Decodificador de audio (VAE)"),
    "acestep-v15-base-Q8_0.gguf": (2549527936, "Sintetizador DiT base (50 pasos): partes sobre el proyecto"),
}
COMMON = ("Qwen3-Embedding-0.6B-Q8_0.gguf", "acestep-v15-turbo-Q8_0.gguf", "vae-BF16.gguf")
PACKS = {
    "calidad": {"name": "Calidad", "lm": "acestep-5Hz-lm-4B-Q8_0.gguf", "vram_gb": 12,
                "desc": "Compositor de 4B: mejor estructura y letras. Para tarjetas de 12 GB o más."},
    "ligero": {"name": "Ligero", "lm": "acestep-5Hz-lm-1.7B-Q8_0.gguf", "vram_gb": 8,
               "desc": "Compositor de 1,7B: algo más simple y más rápido. Para tarjetas de 8 GB."},
    "partes": {"name": "Partes (instrumentos sobre el proyecto)", "lm": None, "vram_gb": 8,
               "desc": "Sintetizador base: genera una guitarra, un piano, cuerdas… que encajan con lo que ya suena."},
}
SYNTH_MODEL = "acestep-v15-turbo-Q8_0.gguf"
BASE_MODEL = "acestep-v15-base-Q8_0.gguf"      # el turbo no hace «lego» (probado: devuelve la mezcla)

# Partes que el sintetizador base sabe añadir a un proyecto (tarea «lego» de ACE-Step 1.5): el
# nombre que ve el usuario y la clase de pista del modelo.
PARTS = {
    "Guitarra": "guitar", "Piano / teclados": "keyboard", "Bajo": "bass", "Cuerdas": "strings",
    "Sintetizador": "synth", "Metales": "brass", "Maderas": "woodwinds", "Percusión": "percussion",
    "Batería": "drums", "Coros": "backing_vocals",
}

# Estilos: el nombre que ve el usuario y las etiquetas (en inglés, como se entrenó el modelo) que se
# añaden a la descripción.
STYLES = {
    "Libre": "",
    "Trap": "trap, 808 bass, hi-hat rolls, dark",
    "Reguetón": "reggaeton, dembow rhythm, latin urban",
    "Hip hop": "hip hop, boom bap drums, sampled groove",
    "Lo-fi": "lo-fi hip hop, dusty drums, mellow keys, vinyl texture",
    "Pop": "pop, catchy, bright synths, punchy drums",
    "R&B": "r&b, smooth, warm keys, laid-back groove",
    "Rock": "rock, electric guitars, live drums, bass guitar",
    "Electrónica": "electronic, edm, synth leads, four on the floor",
    "House": "house, four on the floor, groovy bassline, chords",
    "Funk": "funk, slap bass, tight drums, clavinet",
    "Jazz": "jazz, upright bass, brushes, piano trio",
    "Ambient": "ambient, pads, atmospheric, slow evolving",
    "Cinemático": "cinematic, orchestral, strings, epic percussion",
}
KEYS = ["Auto"] + [f"{n} {m}" for m in ("major", "minor")
                   for n in ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")]
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


# ---------------- rutas -------------------------------------------------------------------------
def _ancestors() -> list[Path]:
    root = paths.app_root()
    return [root, *root.parents]


def engine_dir() -> Path | None:
    """Carpeta con ace-lm / ace-synth: `motores/acestep` junto al programa o, en desarrollo, la
    compilación de `.cache/acestep.cpp/build-vk`."""
    cands = []
    if os.environ.get("AFO_ACESTEP_ENGINE"):
        cands.append(Path(os.environ["AFO_ACESTEP_ENGINE"]))
    cands.append(paths.app_root() / "motores" / "acestep")
    if not paths.is_frozen():
        cands += [p / ".cache" / "acestep.cpp" / "build-vk" for p in _ancestors()]
    for c in cands:
        if all((c / e).is_file() for e in ENGINE_EXES):
            return c
    return None


def models_dir() -> Path:
    """`modelos/acestep` junto a AllForOne.exe. En desarrollo se usa la del programa instalado (EXE)
    si existe, para no duplicar gigas."""
    if os.environ.get("AFO_ACESTEP_MODELS"):
        return Path(os.environ["AFO_ACESTEP_MODELS"])
    if paths.is_frozen():
        return paths.app_root() / "modelos" / "acestep"
    for p in _ancestors():
        c = p / "EXE" / "modelos" / "acestep"
        if c.is_dir():
            return c
    return paths.user_data_dir() / "modelos" / "acestep"


def output_dir() -> Path:
    p = paths.media_dir() / "ia"
    p.mkdir(parents=True, exist_ok=True)
    return p


def gpu_info() -> dict:
    """Nombre y memoria de la tarjeta gráfica (hardware.py). Sin dato devuelve vram_gb = 0."""
    hw = H.hardware()
    return {"name": hw["gpu"], "vram_gb": hw["vram_gb"]}


def pack_files(pack: str) -> list[str]:
    if pack == "partes":
        return [COMMON[0], BASE_MODEL, COMMON[2]]
    return [*COMMON[:1], PACKS[pack]["lm"], *COMMON[1:]]


def pack_status(pack: str, mdir: Path | None = None) -> dict:
    mdir = mdir or models_dir()
    files, total, have = [], 0, 0
    for name in pack_files(pack):
        size, what = FILES[name]
        f = mdir / name
        part = f.with_name(name + ".parte")
        done = f.is_file() and f.stat().st_size == size
        got = size if done else (part.stat().st_size if part.is_file() else 0)
        files.append({"name": name, "what": what, "size": size, "done": done, "got": got})
        total += size
        have += got
    return {"id": pack, **PACKS[pack], "files": files, "size": total, "got": have,
            "installed": all(x["done"] for x in files)}


def installed_pack(mdir: Path | None = None) -> str | None:
    for p in ("calidad", "ligero"):
        if pack_status(p, mdir)["installed"]:
            return p
    return None


def recommended_pack(vram_gb: float | None = None) -> str:
    """El compositor del perfil del equipo (hardware.py): 4B solo en el perfil alto. Con `vram_gb`,
    el de una tarjeta de esa memoria con RAM holgada (para las pruebas)."""
    if vram_gb is None:
        return H.profile()["lm"]
    return H.PROFILES[H.auto_profile({"vram_gb": vram_gb, "ram_gb": 64})]["lm"]


def pack_for_use(mdir: Path | None = None) -> str | None:
    """El compositor que se usa: el del perfil si está instalado; si no, el otro instalado (el 4B
    solo si la tarjeta tiene memoria para él). None si no hay ninguno que sirva."""
    want = recommended_pack()
    if pack_status(want, mdir)["installed"]:
        return want
    other = "ligero" if want == "calidad" else "calidad"
    if pack_status(other, mdir)["installed"] and (other == "ligero" or H.hardware()["vram_gb"] >= H.NEED_GB["lm:calidad"]):
        return other
    return None


def max_seconds() -> int:
    return int(H.profile()["max_seconds"])


# ---------------- petición ---------------------------------------------------------------------
def build_part_request(opts: dict) -> dict:
    """Petición «lego» de ace-synth: una parte nueva (guitarra, piano…) sobre el audio del proyecto,
    con su tempo y tonalidad. Va con el modelo base y guía 7 (sin guía sale una copia del contexto)."""
    part = str(opts.get("part") or "Guitarra")
    if part not in PARTS:
        raise ValueError(f"Parte desconocida: {part}")
    tags = STYLES.get(str(opts.get("style") or "Libre"), "")
    desc = str(opts.get("prompt") or "").strip()
    req = {
        "task_type": "lego", "track": PARTS[part],
        "caption": ", ".join(x for x in (tags, desc or part.lower()) if x),
        "lyrics": "[Instrumental]",
        "duration": int(max(5, min(max_seconds(), float(opts.get("duration", 30))))),
        "seed": int(opts.get("seed", -1)), "guidance_scale": 7.0,
        "output_format": "wav16", "synth_model": BASE_MODEL,
    }
    bpm = int(float(opts.get("bpm") or 0))
    if bpm > 0:
        req["bpm"] = max(40, min(220, bpm))
    key = str(opts.get("key") or "Auto")
    if key != "Auto":
        req["keyscale"] = key
    return req



COVER_MODES = ("Parecida", "Libre")


def build_cover_request(opts: dict, seconds: float) -> dict:
    """Petición «cover» de ace-synth (C13): otra versión de un trozo de audio. «Parecida» usa
    `cover-nofsq` (guarda melodía, estructura y timbre; se le pasa el mismo audio como referencia);
    «Libre» usa `cover` (la fuente solo da la forma). `likeness` 0–1 = cuánto se parece al original
    (`audio_cover_strength`, en el rango que la documentación del motor da por bueno para cada modo)."""
    if seconds < 2.0:
        raise ValueError("Elige al menos 2 s de audio para hacer una versión")
    if seconds > max_seconds():
        raise ValueError(f"Con el perfil de tu equipo se versionan como mucho {max_seconds()} s seguidos: "
                         "acota el trozo con «Dividir»")
    mode = str(opts.get("mode") or "Parecida")
    if mode not in COVER_MODES:
        raise ValueError(f"Modo de versión desconocido: {mode}")
    like = max(0.0, min(1.0, float(opts.get("likeness", 0.5))))
    strength = 0.2 + 0.3 * like if mode == "Parecida" else 0.3 + 0.6 * like
    tags = STYLES.get(str(opts.get("style") or "Libre"), "")
    desc = str(opts.get("prompt") or "").strip()
    req = {
        "task_type": "cover-nofsq" if mode == "Parecida" else "cover",
        "caption": ", ".join(x for x in (tags, desc) if x) or "same instruments and style as the original",
        "lyrics": "[Instrumental]",
        "audio_cover_strength": round(strength, 3),
        "duration": int(max(1, round(seconds))),          # ace-synth usa el largo del audio; esto es para el avance
        "seed": int(opts.get("seed", -1)), "output_format": "wav16", "synth_model": SYNTH_MODEL,
    }
    bpm = int(float(opts.get("bpm") or 0))
    if bpm > 0:
        req["bpm"] = max(40, min(220, bpm))
    key = str(opts.get("key") or "Auto")
    if key != "Auto":
        req["keyscale"] = key
    return req


def build_repaint_request(opts: dict, src_seconds: float) -> dict:
    """Petición «repaint» de ace-synth: rehace la zona [start, end) (segundos del archivo) y deja el
    resto igual. Va con el sintetizador turbo; sin descripción, pide seguir el estilo de la canción."""
    start, end = float(opts.get("start", 0)), float(opts.get("end", 0))
    if not (0 <= start < end <= src_seconds + 0.05):
        raise ValueError(f"La zona a rehacer ({start:.2f}–{end:.2f} s) está fuera del audio ({src_seconds:.2f} s)")
    if end - start < 1.0:
        raise ValueError("Elige al menos 1 s para rehacer")
    if end - start > max_seconds():
        raise ValueError(f"Con el perfil de tu equipo se rehacen como mucho {max_seconds()} s seguidos")
    tags = STYLES.get(str(opts.get("style") or "Libre"), "")
    desc = str(opts.get("prompt") or "").strip()
    req = {
        "task_type": "repaint",
        "caption": ", ".join(x for x in (tags, desc) if x) or "same instruments and style as the rest of the song",
        "lyrics": "[Instrumental]",
        "repainting_start": round(start, 3), "repainting_end": round(min(end, src_seconds), 3),
        "duration": int(max(1, round(src_seconds))),        # ace-synth usa el largo del audio; esto es para el avance
        "seed": int(opts.get("seed", -1)), "output_format": "wav16", "synth_model": SYNTH_MODEL,
    }
    bpm = int(float(opts.get("bpm") or 0))
    if bpm > 0:
        req["bpm"] = max(40, min(220, bpm))
    key = str(opts.get("key") or "Auto")
    if key != "Auto":
        req["keyscale"] = key
    return req


def build_request(opts: dict, pack: str) -> dict:
    """Petición de ace-lm a partir de lo que eligió el usuario (descripción, estilo, tempo…)."""
    desc = str(opts.get("prompt") or "").strip()
    tags = STYLES.get(str(opts.get("style") or "Libre"), "")
    caption = ", ".join(x for x in (tags, desc) if x)
    if not caption:
        raise ValueError("Describe lo que quieres o elige un estilo.")
    instrumental = bool(opts.get("instrumental", True))
    lyrics = "[Instrumental]" if instrumental else str(opts.get("lyrics") or "").strip()
    cre = max(0.0, min(100.0, float(opts.get("creativity", 50))))
    req = {
        "caption": caption,
        "lyrics": lyrics,                       # "" = el compositor escribe la letra
        "duration": int(max(10, min(max_seconds(), float(opts.get("duration", 60))))),
        "timesignature": "4",
        "vocal_language": "unknown" if instrumental else str(opts.get("language") or "es"),
        "seed": int(opts.get("seed", -1)),
        "lm_temperature": round(0.6 + 0.5 * cre / 100.0, 3),   # Creatividad 0..100 → 0,60..1,10
        "output_format": "wav16",
        "lm_model": PACKS[pack]["lm"],
        "synth_model": SYNTH_MODEL,
    }
    bpm = int(float(opts.get("bpm") or 0))
    if bpm > 0:
        req["bpm"] = max(40, min(220, bpm))
    key = str(opts.get("key") or "Auto")
    if key != "Auto":
        req["keyscale"] = key
    return req


def slug(text: str, n: int = 32) -> str:
    """Nombre de archivo sin acentos ni símbolos (sirve en cualquier programa y sistema)."""
    import unicodedata
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", plain.lower()).strip("_")
    return (s[:n].rstrip("_") or "ia")


def list_generations(limit: int = 30) -> list[dict]:
    """Generaciones guardadas (la más reciente primero): WAV + JSON con lo que se pidió."""
    out = []
    for meta in sorted(output_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        wav = meta.with_suffix(".wav")
        if not wav.is_file():
            continue
        try:
            d = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            continue
        d.update(path=str(wav), file=wav.name)
        out.append(d)
        if len(out) >= limit:
            break
    return out


# ---------------- avance a partir del registro del motor ----------------------------------------
_RE_LM_STEP = re.compile(r"\[LM-Phase2\] Step (\d+)")
_RE_DIT_STEP = re.compile(r"\[DiT\] Step (\d+)/(\d+)")


def progress_of(line: str, stage: str, duration: float) -> tuple[float, str] | None:
    """(fracción 0..1 del total, texto) para una línea del registro de ace-lm / ace-synth."""
    if stage == "lm":
        if "[Store] Load LM" in line:
            return 0.06, "Compositor cargado"
        if "[LM-Phase1]" in line:
            return 0.08, "Escribiendo la estructura"
        m = _RE_LM_STEP.search(line)
        if m:
            codes = max(1.0, duration * 5.0)        # 5 códigos por segundo de audio
            return 0.08 + 0.32 * min(1.0, int(m.group(1)) / codes), "Componiendo"
        if "[Ace-LM] Total" in line:
            return 0.42, "Composición lista"
    else:
        if "[Store] Load FSQ" in line or "[Context] Decoded" in line:
            return 0.46, "Preparando la síntesis"
        if "[Store] Load DiT" in line:
            return 0.55, "Sintetizador cargado"
        m = _RE_DIT_STEP.search(line)
        if m:
            return 0.55 + 0.3 * int(m.group(1)) / max(1, int(m.group(2))), "Sintetizando"
        if "[Store] Load VAE" in line:
            return 0.88, "Convirtiendo en audio"
        if "[WAV] Wrote" in line:
            return 0.99, "Audio escrito"
    return None


# ---------------- servicio ---------------------------------------------------------------------
class AiMusic:
    """Descargas de modelos y generación, cada una en su hilo. Una cosa de cada tipo a la vez."""

    def __init__(self, emit):
        self.emit = emit
        self._dl: threading.Thread | None = None
        self._gen: threading.Thread | None = None
        self._dl_cancel = threading.Event()
        self._gen_cancel = threading.Event()
        self._proc: subprocess.Popen | None = None
        self._gpu: dict | None = None
        self._prog = 0.0                         # último avance enviado (el aviso de descanso no lo hace retroceder)
        self.last_log: list[str] = []

    # --- estado ---
    @property
    def downloading(self) -> bool:
        return self._dl is not None and self._dl.is_alive()

    @property
    def generating(self) -> bool:
        return self._gen is not None and self._gen.is_alive()

    def gpu(self) -> dict:
        if self._gpu is None:
            self._gpu = gpu_info()
        return self._gpu

    def status(self) -> dict:
        eng, mdir, g = engine_dir(), models_dir(), self.gpu()
        return {
            "engine": str(eng) if eng else "", "engineOk": eng is not None, "models": str(mdir),
            "gpu": g, "recommended": recommended_pack(), "installed": installed_pack(mdir) or "",
            "using": pack_for_use(mdir) or "", "equipo": H.status(), "maxSeconds": max_seconds(),
            "packs": [pack_status(p, mdir) for p in PACKS], "downloading": self.downloading,
            "generating": self.generating, "styles": list(STYLES), "keys": KEYS, "parts": list(PARTS),
            "partsReady": pack_status("partes", mdir)["installed"],
            "output": str(output_dir()),
        }

    # --- descarga ---
    def download(self, pack: str) -> None:
        if pack not in PACKS:
            raise ValueError(f"Paquete desconocido: {pack}")
        if self.downloading:
            raise RuntimeError("Ya hay una descarga en curso.")
        self._dl_cancel.clear()
        self._dl = threading.Thread(target=self._download, args=(pack,), name="ia-descarga", daemon=True)
        self._dl.start()

    def cancel_download(self) -> None:
        self._dl_cancel.set()

    def _download(self, pack: str) -> None:
        mdir = models_dir()
        try:
            mdir.mkdir(parents=True, exist_ok=True)
            st = pack_status(pack, mdir)
            total, base = st["size"], 0
            for f in st["files"]:
                if not f["done"]:
                    self._fetch(f["name"], f["size"], mdir, base, total)
                base += f["size"]
            self.emit({"type": "aiDownload", "phase": "done", "ok": True, "pack": pack, "progress": 1.0,
                       "message": f"Modelos «{PACKS[pack]['name']}» instalados"})
        except _Cancelled:
            self.emit({"type": "aiDownload", "phase": "done", "ok": False, "cancelled": True, "pack": pack,
                       "message": "Descarga en pausa: al reanudarla sigue donde quedó"})
        except Exception as exc:
            log.exception("Descarga de modelos")
            self.emit({"type": "aiDownload", "phase": "done", "ok": False, "pack": pack,
                       "error": f"No se pudo descargar: {exc}"})

    def _fetch(self, name: str, size: int, mdir: Path, base: int, total: int) -> None:
        dest = mdir / name
        part = mdir / (name + ".parte")
        have = part.stat().st_size if part.is_file() else 0
        if have > size:
            part.unlink()
            have = 0
        req = urllib.request.Request(HF_URL.format(repo=HF_REPO, name=name), headers={"User-Agent": "AllForOne"})
        if have:
            req.add_header("Range", f"bytes={have}-")
        try:
            resp = urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as e:
            if e.code == 416 and have == size:
                part.replace(dest)
                return
            if e.code in (401, 403):
                raise RuntimeError(f"Hugging Face no permite descargar {name} ({e.code})") from e
            raise
        with resp:
            if have and resp.status != 206:          # el servidor no reanuda: empezar de cero
                have = 0
            last = 0.0
            with open(part, "ab" if have else "wb") as fh:
                while True:
                    if self._dl_cancel.is_set():
                        raise _Cancelled()
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
                    have += len(chunk)
                    now = time.monotonic()
                    if now - last > 0.25:
                        last = now
                        self.emit({"type": "aiDownload", "phase": "progress", "file": name,
                                   "progress": (base + have) / total, "got": base + have, "size": total,
                                   "message": f"Descargando {FILES[name][1].lower()}"})
        if have != size:
            raise RuntimeError(f"{name} quedó incompleto ({have} de {size} bytes); vuelve a intentarlo")
        part.replace(dest)

    # --- generación ---
    def generate(self, opts: dict) -> dict:
        if self.generating:
            raise RuntimeError("Ya se está generando una pista.")
        eng = engine_dir()
        if eng is None:
            raise RuntimeError("Falta el motor de IA (motores/acestep junto a AllForOne.exe).")
        pack = pack_for_use()
        if pack is None:
            raise RuntimeError("Faltan los modelos: instálalos en «Modelos de IA» de este módulo.")
        req = build_request(opts, pack)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{stamp}_{slug(str(opts.get('style') or ''))}_{slug(str(opts.get('prompt') or ''), 24)}".rstrip("_")
        self._gen_cancel.clear()
        meta = {"title": str(opts.get("title") or "").strip() or _title(opts), "style": opts.get("style") or "Libre",
                "prompt": str(opts.get("prompt") or ""), "pack": pack, "created": stamp, "request": req}
        self._gen = threading.Thread(target=self._generate, args=(eng, req, name, meta), name="ia-generar",
                                     daemon=True)
        self._gen.start()
        return {"name": name}

    def generate_part(self, opts: dict, src: Path) -> dict:
        """Una parte nueva sobre `src` (la mezcla del proyecto, ya renderizada): llega por `aiEvent`
        como cualquier generación y la interfaz la carga en Pistas."""
        if self.generating:
            raise RuntimeError("Ya se está generando una pista.")
        eng = engine_dir()
        if eng is None:
            raise RuntimeError("Falta el motor de IA (motores/acestep junto a AllForOne.exe).")
        if not pack_status("partes")["installed"]:
            raise RuntimeError("Falta el sintetizador base: instálalo en «Modelos de IA» (Partes).")
        req = build_part_request(opts)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        part = str(opts.get("part") or "Guitarra")
        name = f"{stamp}_parte_{slug(part)}"
        title = str(opts.get("title") or "").strip() or f"{part} (IA)"
        meta = {"title": title, "style": opts.get("style") or "Libre", "prompt": str(opts.get("prompt") or ""),
                "part": part, "created": stamp, "request": req, "source": str(src)}
        self._gen_cancel.clear()
        self._gen = threading.Thread(target=self._part, args=(eng, req, Path(src), name, meta), name="ia-parte",
                                     daemon=True)
        self._gen.start()
        return {"name": name}

    def repaint(self, opts: dict, src: Path, seconds: float) -> dict:
        """Rehace una zona del audio `src` (archivo de una pista). El resultado (el archivo entero,
        igual fuera de la zona) llega por `aiEvent` con `repaint` = {trackId, start, end, source}."""
        if self.generating:
            raise RuntimeError("Ya se está generando una pista.")
        eng = engine_dir()
        if eng is None:
            raise RuntimeError("Falta el motor de IA (motores/acestep junto a AllForOne.exe).")
        if not (models_dir() / SYNTH_MODEL).is_file():
            raise RuntimeError("Falta el sintetizador: instala los modelos en «Modelos de IA».")
        req = build_repaint_request(opts, seconds)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{stamp}_rehecho_{slug(Path(src).stem, 24)}"
        meta = {"title": f"{Path(src).stem} (rehecho {req['repainting_start']:.1f}–{req['repainting_end']:.1f} s)",
                "style": opts.get("style") or "Libre", "prompt": str(opts.get("prompt") or ""), "created": stamp,
                "request": req, "source": str(src),
                "repaint": {"trackId": int(opts.get("trackId", -1)), "start": req["repainting_start"],
                            "end": req["repainting_end"], "source": str(src)}}
        self._gen_cancel.clear()
        self._gen = threading.Thread(target=self._part, args=(eng, req, Path(src), name, meta), name="ia-rehacer",
                                     daemon=True)
        self._gen.start()
        return {"name": name}

    def cover(self, opts: dict, src: Path, start: float, end: float) -> dict:
        """Otra versión (C13) del trozo [start, end) del archivo `src`: se recorta a un WAV de trabajo
        y va a ace-synth en modo cover. El resultado llega por `aiEvent` con `cover` = {trackId, at}
        y la interfaz lo pone en una pista nueva (el original no se toca)."""
        if self.generating:
            raise RuntimeError("Ya se está generando una pista.")
        eng = engine_dir()
        if eng is None:
            raise RuntimeError("Falta el motor de IA (motores/acestep junto a AllForOne.exe).")
        if not (models_dir() / SYNTH_MODEL).is_file():
            raise RuntimeError("Falta el sintetizador: instala los modelos en «Modelos de IA».")
        import soundfile as sf
        info = sf.info(str(src))
        start = max(0.0, float(start)); end = min(float(end), info.duration)
        req = build_cover_request(opts, end - start)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{stamp}_version_{slug(Path(src).stem, 24)}"
        work = output_dir() / f".trabajo_{name}"
        work.mkdir(parents=True, exist_ok=True)
        cut = work / "fuente.wav"
        data, sr = sf.read(str(src), start=int(start * info.samplerate), stop=int(end * info.samplerate),
                           dtype="float32", always_2d=True)
        sf.write(str(cut), data, sr, subtype="PCM_16")
        mode = str(opts.get("mode") or "Parecida")
        meta = {"title": f"{Path(src).stem} (versión {mode.lower()})", "style": opts.get("style") or "Libre",
                "prompt": str(opts.get("prompt") or ""), "created": stamp, "request": req, "source": str(src),
                "cover": {"trackId": int(opts.get("trackId", -1)), "at": float(opts.get("at", 0.0)),
                          "start": round(start, 3), "end": round(end, 3), "mode": mode}}
        self._gen_cancel.clear()
        ref = ["--ref-audio", str(cut)] if req["task_type"] == "cover-nofsq" else []
        self._gen = threading.Thread(target=self._part, args=(eng, req, cut, name, meta, ref), name="ia-version",
                                     daemon=True)
        self._gen.start()
        return {"name": name}

    def _part(self, eng: Path, req: dict, src: Path, name: str, meta: dict, extra: list | None = None) -> None:
        work = output_dir() / f".trabajo_{name}"
        t0 = time.monotonic()
        try:
            work.mkdir(parents=True, exist_ok=True)
            (work / "req.json").write_text(json.dumps(req, ensure_ascii=False, indent=1), encoding="utf-8")
            self.last_log = []
            self._prog = 0.05
            self.emit({"type": "aiGenerate", "phase": "progress", "progress": 0.05,
                       "message": "Escuchando el proyecto"})
            self._run(eng / ENGINE_EXES[1], ["--models", str(models_dir()), "--request", "req.json",
                                             "--src-audio", str(src), *(extra or [])], "synth", req["duration"], work)
            wav = work / "req0.wav"
            if not wav.is_file():
                raise RuntimeError("El sintetizador no escribió el audio.")
            out = output_dir() / f"{name}.wav"
            wav.replace(out)
            meta["seconds"] = round(time.monotonic() - t0, 1)
            out.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
            _rmtree(work)
            self.emit({"type": "aiGenerate", "phase": "done", "ok": True, "progress": 1.0, "path": str(out),
                       "title": meta["title"], "meta": meta, "part": meta.get("part", ""), "repaint": meta.get("repaint"),
                       "cover": meta.get("cover"),
                       "message": f"«{meta['title']}» lista en {meta['seconds']:.0f} s"})
        except _Cancelled:
            _rmtree(work)
            self.emit({"type": "aiGenerate", "phase": "done", "ok": False, "cancelled": True,
                       "message": "Generación cancelada"})
        except Exception as exc:
            log.exception("Parte con IA (registro en %s)", work)
            self.emit({"type": "aiGenerate", "phase": "done", "ok": False,
                       "error": f"No se pudo generar la parte: {exc}", "log": str(work)})

    def cancel(self) -> None:
        self._gen_cancel.set()
        p = self._proc
        if p is not None and p.poll() is None:
            p.kill()

    def shutdown(self) -> None:
        self.cancel()
        self.cancel_download()

    def _run(self, exe: Path, args: list[str], stage: str, duration: float, cwd: Path, job: str = "synth") -> None:
        H.GUARD.before(job, self._gen_cancel,
                       lambda m: self.emit({"type": "aiGenerate", "phase": "progress", "progress": self._prog, "message": m}))
        if self._gen_cancel.is_set():
            raise _Cancelled()
        cmd = [str(exe), *args, *H.engine_args(stage)]
        t0 = time.monotonic()
        log.info("IA: %s", " ".join(cmd))
        self._proc = procs.spawn(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
                                      env={**os.environ, "PATH": str(exe.parent) + os.pathsep + os.environ.get("PATH", "")})
        with open(cwd / f"{stage}.log", "w", encoding="utf-8", errors="replace") as logf:
            for raw in self._proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                logf.write(line + "\n")
                self.last_log = (self.last_log + [line])[-40:]
                pr = progress_of(line, stage, duration)
                if pr:
                    self._prog = max(self._prog, pr[0])
                    self.emit({"type": "aiGenerate", "phase": "progress", "progress": self._prog, "message": pr[1]})
        code = self._proc.wait()
        self._proc = None
        H.GUARD.after(time.monotonic() - t0)
        if self._gen_cancel.is_set():
            raise _Cancelled()
        if code != 0:
            tail = next((x for x in reversed(self.last_log) if "FATAL" in x or "ERROR" in x or "error" in x), "")
            raise RuntimeError(f"{exe.name} terminó con el código {code}. {tail}".strip())

    def _generate(self, eng: Path, req: dict, name: str, meta: dict) -> None:
        work = output_dir() / f".trabajo_{name}"
        t0 = time.monotonic()
        try:
            work.mkdir(parents=True, exist_ok=True)
            (work / "req.json").write_text(json.dumps(req, ensure_ascii=False, indent=1), encoding="utf-8")
            self.last_log = []
            self._prog = 0.02
            self.emit({"type": "aiGenerate", "phase": "progress", "progress": 0.02, "message": "Cargando el compositor"})
            mdir = str(models_dir())
            self._run(eng / ENGINE_EXES[0], ["--models", mdir, "--request", "req.json"], "lm", req["duration"], work,
                      "lm:" + meta["pack"])
            if not (work / "req0.json").is_file():
                raise RuntimeError("El compositor no escribió su resultado.")
            self._run(eng / ENGINE_EXES[1], ["--models", mdir, "--request", "req0.json"], "synth", req["duration"], work)
            wav = work / "req00.wav"
            if not wav.is_file():
                raise RuntimeError("El sintetizador no escribió el audio.")
            composed = json.loads((work / "req0.json").read_text(encoding="utf-8"))
            composed.pop("audio_codes", None)
            out = output_dir() / f"{name}.wav"
            wav.replace(out)
            meta.update(composed={k: composed.get(k) for k in ("bpm", "keyscale", "duration", "lyrics", "seed",
                                                                "caption", "timesignature")},
                        seconds=round(time.monotonic() - t0, 1))
            out.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
            _rmtree(work)
            self.emit({"type": "aiGenerate", "phase": "done", "ok": True, "progress": 1.0, "path": str(out),
                       "title": meta["title"], "meta": meta,
                       "message": f"«{meta['title']}» lista en {meta['seconds']:.0f} s"})
        except _Cancelled:
            _rmtree(work)
            self.emit({"type": "aiGenerate", "phase": "done", "ok": False, "cancelled": True,
                       "message": "Generación cancelada"})
        except Exception as exc:
            log.exception("Generación con IA (registro en %s)", work)
            self.emit({"type": "aiGenerate", "phase": "done", "ok": False,
                       "error": f"No se pudo generar: {exc}", "log": str(work)})


class _Cancelled(Exception):
    pass


def _title(opts: dict) -> str:
    style = str(opts.get("style") or "")
    desc = str(opts.get("prompt") or "").strip()
    base = desc[:28].rstrip() + ("…" if len(desc) > 28 else "") if desc else ""
    return " · ".join(x for x in (style if style != "Libre" else "", base) if x) or "Pista IA"


def _rmtree(p: Path) -> None:
    import shutil
    shutil.rmtree(p, ignore_errors=True)


if __name__ == "__main__":  # diagnóstico rápido: python -m allforone.ai_music
    print(json.dumps(AiMusic(print).status(), ensure_ascii=False, indent=1))
    sys.exit(0)

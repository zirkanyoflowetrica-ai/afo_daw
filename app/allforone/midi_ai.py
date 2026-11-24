"""Composición MIDI con IA local (MIDI-LLM: Llama 3.2 1B con vocabulario de notas AMT, por llama.cpp).

Es la otra mitad de la IA del DAW: `ai_music.py` genera canciones completas en audio (WAV con voz o
instrumental); este módulo compone solo las NOTAS, que entran como pistas de Instrumento y Batería
editables y que suenan con el sintetizador del motor (o el VST3 que elija el usuario).

Todo corre en el equipo:
  * Motor: `llama-server` de llama.cpp compilado con Vulkan (`tools/build_llama.bat`), en
    `motores/llama` junto a AllForOne.exe. Es un proceso aparte que escucha solo en 127.0.0.1; se
    arranca con la primera composición y se cierra con la aplicación.
  * Modelo: `MIDI-LLM_Llama-3.2-1B.Q8_0.gguf` (1,84 GB) en `modelos/midi`, descargado desde la app
    (reanudable: `.parte` + cabecera Range).
  * El modelo escribe tríos (tiempo, duración, nota·instrumento) del vocabulario de Anticipatory
    Music Transformer desplazado 128 256 posiciones tras el de Llama. Aquí se decodifican a notas con
    segundos reales, se agrupan por instrumento General MIDI y se guardan como .mid estándar.

Los eventos (`emit(dict)`, tipo "aiMidi") salen de hilos de trabajo; el puente los reenvía desde Qt.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from . import paths, procs
from .ai_music import _Cancelled, _ancestors, _NO_WINDOW, output_dir, slug

log = logging.getLogger("allforone.ia.midi")

# ---------------- modelo y vocabulario ----------------------------------------------------------
HF_URL = "https://huggingface.co/mradermacher/MIDI-LLM_Llama-3.2-1B-GGUF/resolve/main/{name}"
MODEL = "MIDI-LLM_Llama-3.2-1B.Q8_0.gguf"
MODEL_SIZE = 1_841_405_120
SERVER_EXE = "llama-server.exe" if os.name == "nt" else "llama-server"

LLAMA_VOCAB = 128_256          # las fichas MIDI van detrás del vocabulario de texto de Llama 3
EOS = 128_001
SYSTEM = "You are a world-class composer. Please compose some music according to the following description: "
# Vocabulario AMT (anticipation, codificación por tiempo de llegada)
TIME_RES = 100                 # fichas de tiempo por segundo (10 ms)
MAX_TIME = 10_000
MAX_DUR = 1_000
DUR_OFFSET = MAX_TIME
NOTE_OFFSET = DUR_OFFSET + MAX_DUR
MAX_NOTE = 128 * 129           # nota = instrumento·128 + altura; el instrumento 128 es la batería
REST = NOTE_OFFSET + MAX_NOTE
CONTROL_OFFSET = REST + 1
SEPARATOR = CONTROL_OFFSET + MAX_TIME + MAX_DUR + MAX_NOTE
AUTOREGRESS = SEPARATOR + 1    # «BOS» de la música: va tras el texto
DRUMS = 128

# Familias General MIDI → sonido del sintetizador del motor (índice de Sequencer.insts)
PIANO, BASS, GUITAR, PAD, STRINGS, CHOIR, BELLS = 0, 1, 3, 4, 5, 6, 7
GM_FAMILIES = ["Piano", "Percusión cromática", "Órgano", "Guitarra", "Bajo", "Cuerdas", "Conjunto",
               "Metales", "Lengüetas", "Vientos", "Sintetizador solista", "Sintetizador pad", "Efectos",
               "Étnicos", "Percusión", "Efectos de sonido"]


def gm_name(program: int) -> str:
    return "Batería" if program == DRUMS else GM_FAMILIES[max(0, min(127, program)) // 8]


def gm_to_voice(program: int) -> int:
    fam = max(0, min(127, program)) // 8
    if fam == 6 and 52 <= program <= 54:
        return CHOIR
    return {0: PIANO, 1: BELLS, 2: PAD, 3: GUITAR, 4: BASS, 5: STRINGS, 6: STRINGS, 7: STRINGS, 8: PAD,
            9: PAD, 10: GUITAR, 11: PAD, 12: PAD, 13: GUITAR, 14: BELLS, 15: PAD}[fam]


# Notas de percusión General MIDI → carril de la Batería del motor
# (Bombo, Caja, Hi-hat, Hi-hat abierto, Palmas, Tom, Platillo, Cencerro)
_GM_DRUM = {35: 0, 36: 0, 37: 1, 38: 1, 40: 1, 39: 4, 42: 2, 44: 2, 46: 3, 54: 3, 41: 5, 43: 5, 45: 5, 47: 5,
            48: 5, 50: 5, 49: 6, 51: 6, 52: 6, 53: 6, 55: 6, 57: 6, 59: 6, 56: 7}
FIRST_DRUM_NOTE = 36


def drum_lane(note: int) -> int:
    if note in _GM_DRUM:
        return _GM_DRUM[note]
    return 7 if note >= 60 else 2          # congas, bongós, maracas… → cencerro; el resto → hi-hat


# ---------------- rutas -------------------------------------------------------------------------
def engine_dir() -> Path | None:
    """`motores/llama` junto al programa o, en desarrollo, la compilación de `.cache/llama.cpp`."""
    cands = []
    if os.environ.get("AFO_LLAMA_ENGINE"):
        cands.append(Path(os.environ["AFO_LLAMA_ENGINE"]))
    cands.append(paths.app_root() / "motores" / "llama")
    if not paths.is_frozen():
        cands += [p / ".cache" / "llama.cpp" / "build-vk" / "bin" for p in _ancestors()]
    for c in cands:
        if (c / SERVER_EXE).is_file():
            return c
    return None


def models_dir() -> Path:
    if os.environ.get("AFO_MIDI_MODELS"):
        return Path(os.environ["AFO_MIDI_MODELS"])
    if paths.is_frozen():
        return paths.app_root() / "modelos" / "midi"
    for p in _ancestors():
        c = p / "EXE" / "modelos" / "midi"
        if c.is_dir():
            return c
    return paths.user_data_dir() / "modelos" / "midi"


def model_status(mdir: Path | None = None) -> dict:
    mdir = mdir or models_dir()
    f, part = mdir / MODEL, mdir / (MODEL + ".parte")
    done = f.is_file() and f.stat().st_size == MODEL_SIZE
    have = MODEL_SIZE if done else (part.stat().st_size if part.is_file() else 0)
    return {"name": MODEL, "size": MODEL_SIZE, "have": have, "done": done}


# ---------------- decodificación ----------------------------------------------------------------
def decode(tokens: list[int]) -> list[tuple[float, float, int, int]]:
    """Fichas MIDI (ya restado LLAMA_VOCAB) → notas (inicio s, duración s, altura, programa GM).

    Lee tríos en orden y descarta los que no tienen forma de nota (tiempo, duración, nota): el modelo
    rara vez se sale del vocabulario, pero una ficha suelta no debe desalinear el resto. Un SEPARATOR
    empieza otra sección a continuación de la anterior, como en `events_to_compound` de AMT."""
    out = []
    i, offset, sect_end = 0, 0, 0
    while i + 2 < len(tokens):
        t, d, n = tokens[i], tokens[i + 1], tokens[i + 2]
        if t == SEPARATOR:
            offset, sect_end = offset + sect_end, 0
            i += 3
            continue
        if t >= CONTROL_OFFSET and t != SEPARATOR:      # controles anticipados: mismo trío desplazado
            t, d, n = t - CONTROL_OFFSET, d - CONTROL_OFFSET, n - CONTROL_OFFSET
        if not (0 <= t < MAX_TIME and DUR_OFFSET <= d < NOTE_OFFSET and NOTE_OFFSET <= n < REST):
            i += 1
            continue
        dur = d - DUR_OFFSET
        note = n - NOTE_OFFSET
        sect_end = max(sect_end, t + dur)
        out.append(((t + offset) / TIME_RES, max(dur, 1) / TIME_RES, note % 128, note // 128))
        i += 3
    best: dict[tuple, tuple] = {}            # la misma nota repetida en el mismo instante: la más larga
    for n in out:
        k = (n[0], n[2], n[3])
        if k not in best or n[1] > best[k][1]:
            best[k] = n
    return sorted(best.values())


def too_dense(notes: list[tuple[float, float, int, int]], limit: int = 64) -> bool:
    """La misma comprobación que el MIDI-LLM original: más de `limit` notas a la vez = salida rota."""
    count: dict[float, int] = {}
    for t, *_ in notes:
        count[t] = count.get(t, 0) + 1
    return any(c > limit for c in count.values())


def split_tracks(notes: list[tuple[float, float, int, int]], bpm: float, tag: str = "IA") -> list[dict]:
    """Agrupa por programa GM y pasa los segundos a negras del proyecto (la IA no conoce el tempo:
    sus segundos se conservan tocando al bpm del proyecto)."""
    bps = max(20.0, float(bpm)) / 60.0
    groups: dict[int, list] = {}
    for t, d, p, prog in notes:
        groups.setdefault(prog, []).append((t, d, p))
    out = []
    for prog in sorted(groups, key=lambda g: (g == DRUMS, g)):
        ev = groups[prog]
        if prog == DRUMS:
            midi = [[round(t * bps, 4), 0.25, FIRST_DRUM_NOTE + drum_lane(p), 100] for t, d, p in ev]
            out.append({"type": "drum", "program": prog, "name": f"Batería {tag}", "midi": midi})
        else:
            midi = [[round(t * bps, 4), round(max(0.05, d * bps), 4), p, 96] for t, d, p in ev]
            out.append({"type": "inst", "program": prog, "voice": gm_to_voice(prog),
                        "name": f"{gm_name(prog)} {tag}", "midi": midi})
    return out


# ---------------- patrón por familia del Instrumental Lab (C14) ----------------------------------
# Familia del laboratorio → programas General MIDI que cuentan como ella y cómo pedirla en inglés.
FAMILY_GM = {
    "Batería": ({DRUMS}, "drum beat"),
    "Percusión": ({DRUMS} | set(range(112, 120)), "percussion groove"),
    "Bajo": (set(range(32, 40)), "bass line"),
    "Piano / teclados": (set(range(0, 8)) | set(range(16, 24)), "piano chords and melody"),
    "Guitarra": (set(range(24, 32)), "guitar riff"),
    "Sintetizador": (set(range(80, 96)), "synth lead and pads"),
    "Cuerdas": (set(range(40, 52)), "string section"),
    "Metales": (set(range(56, 64)), "brass section"),
    "Maderas": (set(range(64, 80)), "woodwinds"),
}
FAMILY_TRIES = 3


def family_prompt(family: str, style_tags: str, key: str, bpm: float, extra: str = "") -> str:
    if family not in FAMILY_GM:
        raise ValueError(f"Familia desconocida: {family}")
    parts = [style_tags, FAMILY_GM[family][1], f"{bpm:g} bpm"]
    if key and key != "Auto":
        parts.append(f"in {key}")
    if extra:
        parts.append(extra)
    return ", ".join(p for p in parts if p)


def pick_family(notes: list[tuple[float, float, int, int]], family: str) -> list[tuple[float, float, int, int]]:
    """Solo las notas de los instrumentos de la familia; nunca se cambia el instrumento de otras."""
    progs = FAMILY_GM[family][0]
    return [n for n in notes if n[3] in progs]


def to_pattern(notes: list[tuple[float, float, int, int]], bpm: float, bars: int, beats: int = 4) -> list:
    """El modelo no conoce el tempo: ataques y duraciones se ajustan a semicorcheas del tempo de la
    sesión y se cortan a sus compases (lo que cae fuera no entra). Un patrón es una pista: si el modelo
    usó varios instrumentos de la familia (p. ej. tres bajos), todo va con el que más notas tiene."""
    step = 60.0 / max(20.0, float(bpm)) / 4
    count: dict[int, int] = {}
    for n in notes:
        count[n[3]] = count.get(n[3], 0) + 1
    main = max(count, key=lambda g: (count[g], -g)) if count else 0
    end = bars * beats * 4 * step
    out, seen = [], set()
    for t, d, p, prog in notes:
        q = round(t / step) * step
        if q >= end - 1e-6 or (q, p) in seen:
            continue
        seen.add((q, p))
        out.append((round(q, 6), round(min(max(step, round(d / step) * step), end - q), 6), p, main))
    return sorted(out)


# ---------------- archivo .mid (formato 1, sin dependencias) ------------------------------------
def _vlq(n: int) -> bytes:
    b = [n & 0x7F]
    n >>= 7
    while n:
        b.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(b))


def write_mid(path: Path, notes: list[tuple[float, float, int, int]], bpm: float = 120.0) -> None:
    """Guarda las notas en un .mid estándar a `bpm` (los segundos se mantienen)."""
    tpq = 480
    ticks = lambda s: int(round(s * bpm / 60.0 * tpq))
    tempo = int(round(60_000_000 / bpm))
    tracks = [b"\x00\xff\x51\x03" + tempo.to_bytes(3, "big") + b"\x00\xff\x2f\x00"]
    chans: dict[int, int] = {}
    progs = sorted({n[3] for n in notes}, key=lambda g: (g == DRUMS, g))
    for prog in progs:
        if prog == DRUMS:
            ch = 9
        else:
            ch = len([c for c in chans.values() if c != 9])
            ch = ch + 1 if ch >= 9 else ch
            ch = min(ch, 15)
        chans[prog] = ch
        ev = []
        for t, d, p, g in notes:
            if g == prog:
                ev.append((ticks(t), 1, p))
                ev.append((ticks(t + d), 0, p))
        ev.sort()
        data = bytearray()
        name = gm_name(prog).encode("latin-1", "replace")
        data += b"\x00\xff\x03" + _vlq(len(name)) + name
        if prog != DRUMS:
            data += b"\x00" + bytes([0xC0 | ch, prog])
        now = 0
        for tk, on, p in ev:
            data += _vlq(tk - now) + bytes([(0x90 if on else 0x80) | ch, p, 96 if on else 0])
            now = tk
        data += b"\x00\xff\x2f\x00"
        tracks.append(bytes(data))
    with open(path, "wb") as fh:
        fh.write(b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), tpq))
        for tr in tracks:
            fh.write(b"MTrk" + struct.pack(">I", len(tr)) + tr)


def read_mid(path: Path) -> list[tuple[float, float, int, int]]:
    """Lee un .mid (formato 0 o 1, con cambios de tempo) → notas (inicio s, duración s, altura, programa GM;
    el canal 10 es la batería, programa 128). Sirve para las composiciones guardadas y para importar MIDI."""
    data = Path(path).read_bytes()
    if data[:4] != b"MThd":
        raise ValueError("No es un archivo MIDI")
    hlen, _fmt, ntr, div = struct.unpack(">IHHH", data[4:14])
    if div & 0x8000:
        raise ValueError("MIDI con división SMPTE: no compatible")
    pos = 8 + hlen
    raw: list[tuple[int, int, int, int, int]] = []          # (tick, orden, tipo, a, b)
    tempos: list[tuple[int, int]] = [(0, 500_000)]
    for _ in range(ntr):
        if data[pos:pos + 4] != b"MTrk":
            break
        ln = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        i, end, tick, status = pos + 8, pos + 8 + ln, 0, 0
        pos = end
        while i < end:
            dt = 0
            while True:
                c = data[i]; i += 1
                dt = (dt << 7) | (c & 0x7F)
                if not c & 0x80:
                    break
            tick += dt
            c = data[i]
            if c == 0xFF:
                typ, i = data[i + 1], i + 2
                ml = 0
                while True:
                    c = data[i]; i += 1
                    ml = (ml << 7) | (c & 0x7F)
                    if not c & 0x80:
                        break
                if typ == 0x51 and ml == 3:
                    tempos.append((tick, int.from_bytes(data[i:i + 3], "big")))
                i += ml
                continue
            if c in (0xF0, 0xF7):
                i += 1
                ml = 0
                while True:
                    c = data[i]; i += 1
                    ml = (ml << 7) | (c & 0x7F)
                    if not c & 0x80:
                        break
                i += ml
                continue
            if c & 0x80:
                status, i = c, i + 1
            kind, ch = status & 0xF0, status & 0x0F
            if kind in (0xC0, 0xD0):
                raw.append((tick, 0, kind, ch, data[i])); i += 1
            else:
                raw.append((tick, 1, kind, ch, (data[i] << 8) | data[i + 1])); i += 2
    tempos.sort()
    def secs(tk: int) -> float:
        t, last_tk, us = 0.0, 0, 500_000
        for at, tempo in tempos:
            if at >= tk:
                break
            t += (at - last_tk) * us / div / 1e6
            last_tk, us = at, tempo
        return t + (tk - last_tk) * us / div / 1e6
    prog = [0] * 16
    open_: dict[tuple[int, int], tuple[int, int]] = {}
    out = []
    for tick, _o, kind, ch, v in sorted(raw, key=lambda e: (e[0], e[1])):
        if kind == 0xC0:
            prog[ch] = v
            continue
        if kind not in (0x80, 0x90):
            continue
        note, vel = v >> 8, v & 0xFF
        key = (ch, note)
        if key in open_:                                     # cierra la nota anterior
            t0, p = open_.pop(key)
            out.append((secs(t0), max(0.01, secs(tick) - secs(t0)), note, p))
        if kind == 0x90 and vel > 0:
            open_[key] = (tick, DRUMS if ch == 9 else prog[ch])
    out.sort()
    return out


def list_compositions(limit: int = 30) -> list[dict]:
    out = []
    for f in sorted(output_dir().glob("*.mid.json"), reverse=True)[:limit]:
        try:
            meta = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        mid = f.with_suffix("")
        if mid.is_file():
            out.append({"path": str(mid), "json": str(f), "title": meta.get("title", mid.stem),
                        "notes": meta.get("notes", 0), "seconds": meta.get("seconds", 0),
                        "created": meta.get("created", "")})
    return out


# ---------------- servidor y trabajos -----------------------------------------------------------
def creativity_temperature(creativity) -> float:
    """Perilla Creatividad (0..100) → temperatura del muestreo: 0,70..1,20 (más alta, más sorpresas)."""
    return max(0.5, min(1.3, 0.7 + float(creativity) / 200))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _post(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class MidiAi:
    """Descarga del modelo y composiciones, cada una en su hilo; un llama-server compartido."""

    def __init__(self, emit):
        self.emit = emit
        self._dl: threading.Thread | None = None
        self._gen: threading.Thread | None = None
        self._dl_cancel = threading.Event()
        self._gen_cancel = threading.Event()
        self._server: subprocess.Popen | None = None
        self._port = 0
        self._lock = threading.Lock()
        self.last_log = ""

    @property
    def downloading(self) -> bool:
        return self._dl is not None and self._dl.is_alive()

    @property
    def generating(self) -> bool:
        return self._gen is not None and self._gen.is_alive()

    def status(self) -> dict:
        eng = engine_dir()
        return {"engine": str(eng) if eng else "", "engineOk": eng is not None, "models": str(models_dir()),
                "model": model_status(), "downloading": self.downloading, "generating": self.generating,
                "compositions": list_compositions()}

    # --- descarga ---
    def download(self) -> None:
        if self.downloading:
            raise RuntimeError("Ya se está descargando el modelo MIDI.")
        self._dl_cancel.clear()
        self._dl = threading.Thread(target=self._download, name="ia-midi-descarga", daemon=True)
        self._dl.start()

    def cancel_download(self) -> None:
        self._dl_cancel.set()

    def _download(self) -> None:
        mdir = models_dir()
        dest, part = mdir / MODEL, mdir / (MODEL + ".parte")
        try:
            mdir.mkdir(parents=True, exist_ok=True)
            have = part.stat().st_size if part.is_file() else 0
            if have > MODEL_SIZE:
                part.unlink()
                have = 0
            if have < MODEL_SIZE:
                req = urllib.request.Request(HF_URL.format(name=MODEL), headers={"User-Agent": "AllForOne"})
                if have:
                    req.add_header("Range", f"bytes={have}-")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    if have and resp.status != 206:
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
                            if time.monotonic() - last > 0.25:
                                last = time.monotonic()
                                self.emit({"type": "aiMidiDownload", "phase": "progress",
                                           "progress": have / MODEL_SIZE, "got": have, "size": MODEL_SIZE,
                                           "message": "Descargando el modelo de composición MIDI"})
            if have != MODEL_SIZE:
                raise RuntimeError(f"El modelo quedó incompleto ({have} de {MODEL_SIZE} bytes); vuelve a intentarlo")
            part.replace(dest)
            self.emit({"type": "aiMidiDownload", "phase": "done", "ok": True, "progress": 1.0,
                       "message": "Modelo de composición MIDI instalado"})
        except _Cancelled:
            self.emit({"type": "aiMidiDownload", "phase": "done", "ok": False, "cancelled": True,
                       "message": "Descarga en pausa: al reanudarla sigue donde quedó"})
        except Exception as exc:
            log.exception("Descarga del modelo MIDI")
            self.emit({"type": "aiMidiDownload", "phase": "done", "ok": False, "error": f"No se pudo descargar: {exc}"})

    # --- servidor ---
    def _ensure_server(self) -> str:
        with self._lock:
            if self._server is not None and self._server.poll() is None:
                return f"http://127.0.0.1:{self._port}"
            eng = engine_dir()
            if eng is None:
                raise RuntimeError("Falta el motor de composición (motores/llama junto a AllForOne.exe).")
            if not model_status()["done"]:
                raise RuntimeError("Falta el modelo MIDI: descárgalo en «Modelo MIDI» de este módulo.")
            self._port = _free_port()
            logf = paths.user_data_dir() / "logs" / "llama-server.log"
            logf.parent.mkdir(parents=True, exist_ok=True)
            self.last_log = str(logf)
            args = [str(eng / SERVER_EXE), "-m", str(models_dir() / MODEL), "--host", "127.0.0.1",
                    "--port", str(self._port), "-c", "4096", "-ngl", "99", "--parallel", "1", "--no-webui"]
            with open(logf, "wb") as lf:
                self._server = procs.spawn(args, cwd=str(eng), stdout=lf, stderr=subprocess.STDOUT,
                                                stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
            url = f"http://127.0.0.1:{self._port}"
            t0 = time.monotonic()
            while time.monotonic() - t0 < 120:
                if self._gen_cancel.is_set():
                    raise _Cancelled()
                if self._server.poll() is not None:
                    raise RuntimeError(f"El motor de composición se cerró al cargar el modelo (registro: {logf})")
                try:
                    with urllib.request.urlopen(url + "/health", timeout=2) as r:
                        if r.status == 200:
                            return url
                except (urllib.error.URLError, OSError):
                    pass
                time.sleep(0.3)
            raise RuntimeError("El motor de composición no respondió en 2 minutos")

    def shutdown(self) -> None:
        self.cancel()
        self.cancel_download()
        p = self._server
        if p is not None and p.poll() is None:
            p.kill()
        self._server = None

    # --- composición ---
    def generate(self, opts: dict) -> dict:
        if self.generating:
            raise RuntimeError("Ya se está componiendo.")
        if engine_dir() is None:
            raise RuntimeError("Falta el motor de composición (motores/llama junto a AllForOne.exe).")
        if not model_status()["done"]:
            raise RuntimeError("Falta el modelo MIDI: descárgalo en «Modelo MIDI» de este módulo.")
        text = str(opts.get("prompt") or "").strip()
        fam = str(opts.get("family") or "")
        if fam:                                       # patrón del laboratorio: la descripción sale de la sesión
            from .ai_music import STYLES
            text = family_prompt(fam, STYLES.get(str(opts.get("style") or "Libre"), ""), str(opts.get("key") or "Auto"),
                                 float(opts.get("bpm") or 120), text)
        if not text:
            raise ValueError("Describe la música que quieres (en inglés el modelo entiende mejor).")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{stamp}_midi_{slug(text, 28)}".rstrip("_")
        self._gen_cancel.clear()
        self._gen = threading.Thread(target=self._generate, args=(opts, text, name, stamp), name="ia-midi",
                                     daemon=True)
        self._gen.start()
        return {"name": name}

    def cancel(self) -> None:
        self._gen_cancel.set()

    def _generate(self, opts: dict, text: str, name: str, stamp: str) -> None:
        try:
            self.emit({"type": "aiMidi", "phase": "progress", "progress": 0.02, "message": "Cargando el modelo…"})
            url = self._ensure_server()
            fam = str(opts.get("family") or "")
            bpm = float(opts.get("bpm") or 120)
            if fam:                                   # patrón del laboratorio: solo esa familia, a tempo
                o = dict(opts)
                for _ in range(FAMILY_TRIES):
                    notes, tokens = self.compose(url, text, o)
                    notes = to_pattern(pick_family(notes, fam), bpm, int(opts.get("bars") or 8), int(opts.get("beats") or 4))
                    if notes:
                        break
                    o["seed"] = -1
                else:
                    raise RuntimeError(f"El modelo no compuso {fam.lower()} en {FAMILY_TRIES} intentos; "
                                       "prueba con otra descripción o con otro estilo")
            else:
                notes, tokens = self.compose(url, text, opts)
            path = output_dir() / f"{name}.mid"
            write_mid(path, notes, bpm)
            secs = max((t + d for t, d, *_ in notes), default=0.0)
            meta = {"title": text[:60], "prompt": text, "created": stamp, "notes": len(notes),
                    "seconds": round(secs, 2), "bpm": bpm, "tokens": len(tokens)}
            Path(str(path) + ".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
            self.emit({"type": "aiMidi", "phase": "done", "ok": True, "progress": 1.0, "path": str(path),
                       "title": meta["title"], "notes": len(notes), "seconds": meta["seconds"],
                       "tracks": split_tracks(notes, bpm, "· patrón IA" if fam else "IA"), "family": fam,
                       "message": f"{len(notes)} notas en {len({n[3] for n in notes})} instrumentos"})
        except _Cancelled:
            self.emit({"type": "aiMidi", "phase": "done", "ok": False, "cancelled": True, "message": "Composición cancelada"})
        except Exception as exc:
            log.exception("Composición MIDI")
            self.emit({"type": "aiMidi", "phase": "done", "ok": False, "error": f"No se pudo componer: {exc}"})

    def compose(self, url: str, text: str, opts: dict) -> tuple[list, list[int]]:
        """Pide las fichas al servidor en tandas (para poder avisar del avance y cancelar)."""
        prompt = _post(url + "/tokenize", {"content": SYSTEM + text + " ", "add_special": True}, 30)["tokens"]
        prompt = [int(t["id"]) if isinstance(t, dict) else int(t) for t in prompt]
        prompt.append(AUTOREGRESS + LLAMA_VOCAB)
        total = int(max(300, min(4000, float(opts.get("length") or 2046))))
        total -= total % 3
        temp = creativity_temperature(opts.get("creativity", 60))
        seed = int(opts.get("seed", -1))
        out: list[int] = []
        chunk = 300
        for attempt in range(3):
            out = []
            while len(out) < total:
                if self._gen_cancel.is_set():
                    raise _Cancelled()
                r = _post(url + "/completion", {
                    "prompt": prompt + [t + LLAMA_VOCAB for t in out], "n_predict": min(chunk, total - len(out)),
                    "temperature": temp, "top_p": 0.98, "top_k": 0, "min_p": 0.0, "repeat_penalty": 1.0,
                    "seed": seed if seed >= 0 else -1, "cache_prompt": True, "return_tokens": True,
                    "stream": False}, 600)
                toks = [int(t) for t in r.get("tokens") or []]
                stop = not toks or EOS in toks or r.get("stop_type") == "eos"
                out += [t - LLAMA_VOCAB for t in toks if t >= LLAMA_VOCAB]
                self.emit({"type": "aiMidi", "phase": "progress", "progress": 0.05 + 0.9 * min(1, len(out) / total),
                           "message": f"Componiendo… {len(out) // 3} notas"})
                if stop:
                    break
            notes = decode(out)
            if notes and not too_dense(notes):
                return notes, out
            seed = -1                                   # salida rota: otra semilla
        raise RuntimeError("El modelo no produjo notas válidas; prueba con otra descripción")

"""Perfil del equipo para la IA local: qué modelo usar y cuánto cargar la tarjeta gráfica.

Se detecta la tarjeta (nombre y memoria, del registro de Windows), la RAM y los hilos del procesador,
y de ahí sale un perfil (`alto`, `medio`, `bajo`, `cpu`) que decide:
  * el compositor (`lm`): 4B solo en equipos holgados; 1,7B en el resto;
  * `vae_chunk`: el tamaño de los bloques del decodificador de audio (menos memoria de pico);
  * `rest`: descanso de la gráfica tras cada trabajo, en fracción de lo que tardó (con 0,5 la
    tarjeta trabaja como mucho dos tercios del tiempo, también en tandas de variantes);
  * `max_seconds`: duración máxima de lo que se genera;
  * `device`: `CPU` cuando no hay gráfica que sirva;
  * `demucs_threads`: hilos máximos del separador (deja dos libres para el audio y la interfaz).
Antes de cada trabajo se mira la memoria de vídeo que ya usan otros programas (contador de Windows
«GPU Adapter Memory»): si no cabe el modelo, no se lanza y se dice por qué.
El usuario puede fijar otro perfil (se guarda en `equipo.json` de sus datos)."""
from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from . import paths

log = logging.getLogger("allforone.hardware")
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

PROFILES = {
    "alto": {"name": "Alto", "lm": "calidad", "vae_chunk": 1024, "rest": 0.25, "max_seconds": 240, "device": "",
             "desc": "Gráfica de 16 GB o más y 32 GB de RAM: compositor 4B, piezas de hasta 4 min"},
    "medio": {"name": "Medio", "lm": "ligero", "vae_chunk": 512, "rest": 0.5, "max_seconds": 150, "device": "",
              "desc": "Gráfica de 10 GB o más y 16 GB de RAM: compositor 1,7B, la gráfica descansa la mitad de lo que trabaja"},
    "bajo": {"name": "Bajo", "lm": "ligero", "vae_chunk": 256, "rest": 1.0, "max_seconds": 60, "device": "",
             "desc": "Gráfica de 6 a 10 GB: compositor 1,7B, piezas de hasta 1 min y descanso igual al trabajo"},
    "cpu": {"name": "Solo procesador", "lm": "ligero", "vae_chunk": 256, "rest": 0.0, "max_seconds": 30, "device": "CPU",
            "desc": "Sin gráfica que sirva: todo en el procesador, lento; piezas de hasta 30 s"},
}
ORDER = ("alto", "medio", "bajo", "cpu")
# Memoria de vídeo que ocupa cada trabajo, sin contar lo que usen otros programas: los modelos más
# un margen para activaciones y el decodificador (GB).
NEED_GB = {"lm:calidad": 6.0, "lm:ligero": 3.5, "synth": 4.5}


def _ram_gb() -> float:
    if os.name != "nt":
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
        except (ValueError, OSError, AttributeError):
            return 0.0

    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MS()
    m.dwLength = ctypes.sizeof(MS)
    try:
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    except Exception:
        return 0.0
    return m.ullTotalPhys / 2 ** 30


def _gpu() -> dict:
    """La tarjeta con más memoria (registro de Windows; el valor de 64 bits es el real en tarjetas
    de más de 4 GB, Win32_VideoController se queda en 4 GB)."""
    best = {"name": "", "vram_gb": 0.0}
    if os.name != "nt":
        return best
    try:
        import winreg
        base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
            for i in range(32):
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                if not sub.isdigit():
                    continue
                try:
                    with winreg.OpenKey(k, sub) as s:
                        name = str(winreg.QueryValueEx(s, "DriverDesc")[0])
                        try:
                            mem = int(winreg.QueryValueEx(s, "HardwareInformation.qwMemorySize")[0])
                        except OSError:
                            raw = winreg.QueryValueEx(s, "HardwareInformation.MemorySize")[0]
                            mem = int.from_bytes(raw, "little") if isinstance(raw, bytes) else int(raw)
                except OSError:
                    continue
                gb = round(mem / 2 ** 30, 1)
                if gb > best["vram_gb"]:
                    best = {"name": name, "vram_gb": gb}
    except Exception:
        log.exception("No se pudo leer la tarjeta gráfica")
    return best


def detect() -> dict:
    g = _gpu()
    return {"gpu": g["name"], "vram_gb": g["vram_gb"], "ram_gb": round(_ram_gb(), 1),
            "threads": os.cpu_count() or 1}


def auto_profile(hw: dict) -> str:
    """Perfil por la memoria de vídeo y la RAM (con medio GB de holgura: 16 GB de RAM se ven como 15,9)."""
    v, r = hw["vram_gb"], hw["ram_gb"]
    if v >= 15.5 and r >= 31:
        return "alto"
    if v >= 9.5 and r >= 15:
        return "medio"
    if v >= 5.5 and r >= 11:
        return "bajo"
    return "cpu"


def _settings_file() -> Path:
    return paths.user_data_dir() / "equipo.json"


def chosen_override() -> str:
    try:
        p = json.loads(_settings_file().read_text(encoding="utf-8")).get("perfil", "auto")
        return p if p in PROFILES else "auto"
    except (OSError, ValueError, AttributeError):
        return "auto"


def set_override(name: str) -> None:
    if name != "auto" and name not in PROFILES:
        raise ValueError(f"Perfil desconocido: {name}")
    f = _settings_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"perfil": name}), encoding="utf-8")
    _cache.pop("profile", None)


_cache: dict = {}


def hardware() -> dict:
    if "hw" not in _cache:
        _cache["hw"] = detect()
        log.info("Equipo: %s", _cache["hw"])
    return _cache["hw"]


def profile() -> dict:
    """El perfil en uso: {id, auto, override, …PROFILES[id], demucs_threads}."""
    if "profile" not in _cache:
        hw = hardware()
        auto = auto_profile(hw)
        ov = chosen_override()
        pid = auto if ov == "auto" else ov
        _cache["profile"] = {"id": pid, "auto": auto, "override": ov, **PROFILES[pid],
                             "demucs_threads": max(1, min(8, hw["threads"] - 2))}
    return _cache["profile"]


def status() -> dict:
    return {"hardware": hardware(), "profile": profile(),
            "profiles": [{"id": k, **PROFILES[k]} for k in ORDER]}


def vram_in_use_gb() -> float | None:
    """Memoria de vídeo dedicada que ya está en uso (todos los programas), o None si no se puede leer."""
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Usage').CounterSamples"
                              " | ForEach-Object { $_.CookedValue }"],
                             capture_output=True, text=True, timeout=15, creationflags=_NO_WINDOW)
        vals = [float(x.replace(",", ".")) for x in out.stdout.split() if x.strip()]
        return max(vals) / 2 ** 30 if vals else None
    except Exception:
        log.exception("No se pudo leer la memoria de vídeo en uso")
        return None


def engine_args(stage: str) -> list[str]:
    """Opciones de ace-lm / ace-synth según el perfil."""
    p = profile()
    args = ["--device", p["device"]] if p["device"] else []
    if stage == "synth":
        args += ["--vae-chunk", str(p["vae_chunk"])]
    return args


class GpuGuard:
    """Un trabajo de IA en la gráfica a la vez, con descanso entre trabajos y comprobación de memoria.
    `before(job, cancel, notify)` espera el descanso pendiente y comprueba que el modelo cabe;
    `after(seconds)` apunta cuánto tiene que descansar la gráfica."""

    def __init__(self):
        self._lock = threading.Lock()
        self._next = 0.0

    def before(self, job: str, cancel: threading.Event | None = None, notify=None) -> None:
        p = profile()
        if p["device"] == "CPU":
            return
        while (wait := self._next - time.monotonic()) > 0:
            if notify:
                notify(f"La gráfica descansa {wait:.0f} s (perfil {p['name']})")
            if cancel is not None and cancel.wait(min(1.0, wait)):
                return
            if cancel is None:
                time.sleep(min(1.0, wait))
        total = hardware()["vram_gb"]
        used = vram_in_use_gb()
        need = NEED_GB.get(job, 4.5)
        if total and used is not None and total - used < need:
            raise RuntimeError(f"La gráfica tiene {total - used:.1f} GB libres y este paso necesita unos {need:.0f} GB: "
                               "cierra juegos u otros programas que la estén usando y vuelve a intentarlo")

    def after(self, seconds: float) -> None:
        with self._lock:
            self._next = time.monotonic() + profile()["rest"] * max(0.0, seconds)


GUARD = GpuGuard()

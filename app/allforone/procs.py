"""Procesos de la IA local atados a la sesión (ace-lm / ace-synth, llama-server, demucs).

Cada motor que abre AllForOne se lanza con `spawn()`:
  * Windows: entra en un «Job Object» con KILL_ON_JOB_CLOSE. El asa del trabajo es de este proceso;
    si AllForOne se cierra de cualquier forma (normal, caída, «Finalizar tarea»), Windows cierra el
    trabajo y con él todos sus motores: no se acumulan en la memoria ni en la gráfica.
  * Linux: PR_SET_PDEATHSIG = SIGKILL (el motor muere cuando muere su padre).
Además se apuntan en `logs/ia_procesos.json` (pid, ejecutable y sesión dueña). Al arrancar,
`reap_orphans()` cierra solo los apuntados cuya sesión ya no existe y cuyo ejecutable sigue siendo
el mismo: nunca procesos de otros programas (p. ej. un Ollama del usuario) ni de otro AllForOne abierto.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import threading
from pathlib import Path

from . import paths

log = logging.getLogger("allforone.procs")
_lock = threading.Lock()
_job = None
IS_WIN = os.name == "nt"

if IS_WIN:
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    _k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]

    class _Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class _Io(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]

    class _Extended(ctypes.Structure):
        _fields_ = [("Basic", _Basic), ("Io", _Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    _KILL_ON_JOB_CLOSE = 0x2000
    _EXTENDED_LIMIT_INFO = 9
    _QUERY = 0x1000                     # PROCESS_QUERY_LIMITED_INFORMATION
    _TERMINATE = 0x0001
    _STILL_ACTIVE = 259


def _job_handle():
    """El trabajo de la sesión (uno por proceso de AllForOne), creado la primera vez."""
    global _job
    if _job is None and IS_WIN:
        h = _k32.CreateJobObjectW(None, None)
        if not h:
            raise OSError(ctypes.get_last_error(), "CreateJobObject")
        info = _Extended()
        info.Basic.LimitFlags = _KILL_ON_JOB_CLOSE
        if not _k32.SetInformationJobObject(h, _EXTENDED_LIMIT_INFO, ctypes.byref(info), ctypes.sizeof(info)):
            err = ctypes.get_last_error()
            _k32.CloseHandle(h)
            raise OSError(err, "SetInformationJobObject")
        _job = h
    return _job


def registry_file() -> Path:
    return paths.user_data_dir() / "logs" / "ia_procesos.json"


def _read() -> list[dict]:
    try:
        d = json.loads(registry_file().read_text(encoding="utf-8"))
        return [x for x in d if isinstance(x, dict) and "pid" in x]
    except (OSError, ValueError):
        return []


def _write(items: list[dict]) -> None:
    f = registry_file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as exc:
        log.warning("No se pudo apuntar el proceso de IA: %s", exc)


def _image(pid: int) -> str | None:
    """Ruta del ejecutable de un proceso vivo (None si no existe o ya terminó)."""
    if not IS_WIN:
        try:
            return os.readlink(f"/proc/{pid}/exe")
        except OSError:
            return None
    h = _k32.OpenProcess(_QUERY, False, int(pid))
    if not h:
        return None
    try:
        code = wintypes.DWORD()
        if not _k32.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != _STILL_ACTIVE:
            return None
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(len(buf))
        return buf.value if _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else None
    finally:
        _k32.CloseHandle(h)


def _same(a: str | None, b: str) -> bool:
    return bool(a) and os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _kill(pid: int) -> bool:
    if not IS_WIN:
        try:
            os.kill(pid, 9)
            return True
        except OSError:
            return False
    h = _k32.OpenProcess(_TERMINATE, False, int(pid))
    if not h:
        return False
    try:
        return bool(_k32.TerminateProcess(h, 1))
    finally:
        _k32.CloseHandle(h)


def _linux_pdeathsig() -> None:          # pragma: no cover - solo Linux
    try:
        ctypes.CDLL("libc.so.6").prctl(1, 9)   # PR_SET_PDEATHSIG, SIGKILL
    except Exception:
        pass


def spawn(cmd: list[str], **kw) -> subprocess.Popen:
    """`subprocess.Popen` de un motor de IA, atado a la sesión y apuntado en el registro."""
    if not IS_WIN:
        kw.setdefault("preexec_fn", _linux_pdeathsig)
    p = subprocess.Popen(cmd, **kw)
    if IS_WIN:
        try:
            if not _k32.AssignProcessToJobObject(_job_handle(), int(p._handle)):
                raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")
        except OSError as exc:              # p. ej. ya está en un trabajo que no deja anidar: queda el registro
            log.warning("El motor %s no se pudo atar a la sesión: %s", Path(cmd[0]).name, exc)
    with _lock:
        items = [x for x in _read() if _image(int(x["pid"])) is not None]
        items.append({"pid": p.pid, "exe": str(cmd[0]), "owner": os.getpid(), "ownerExe": _image(os.getpid()) or ""})
        _write(items)
    return p


def reap_orphans() -> list[dict]:
    """Cierra los motores de IA que dejó una sesión anterior que ya no está. Devuelve los cerrados."""
    killed, keep = [], []
    with _lock:
        for x in _read():
            pid = int(x["pid"])
            img = _image(pid)
            if img is None:                                  # ya terminó
                continue
            owner_alive = _same(_image(int(x.get("owner", 0))), x.get("ownerExe") or "\0") if x.get("owner") else False
            if owner_alive:                                  # otro AllForOne abierto: es suyo
                keep.append(x)
            elif _same(img, x["exe"]) and _kill(pid):        # el mismo motor, huérfano
                killed.append(x)
                log.info("Motor de IA huérfano cerrado: %s (pid %s)", Path(x["exe"]).name, pid)
        _write(keep)
    return killed

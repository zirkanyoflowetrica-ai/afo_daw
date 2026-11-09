"""Búsqueda de plugins VST3 en un proceso aparte.

Abrir un plugin para leer sus datos ejecuta su código: si uno se cuelga o cierra el proceso, en el
mismo proceso se llevaría AllForOne entero. Por eso la búsqueda la hace otro AllForOne
(`--scan-plugins LISTA`) que guarda la lista tras cada archivo y deja en un «pedal» el archivo que está
abriendo. Si muere, `PluginScanner` lo relanza: JUCE pone en la lista negra el archivo del pedal y la
búsqueda sigue desde ahí. Al terminar, el motor vuelve a leer la lista (`reload_plugins`).
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from . import paths

log = logging.getLogger("allforone.plugins")
MAX_RESTARTS = 25
HANG_SECONDS = 150                # un archivo que tarda más se da por colgado: se mata y se salta


def list_file(data_dir: Path) -> Path:
    return Path(data_dir) / "plugins_vst3.xml"


def run_child(list_path: str) -> int:
    """Proceso buscador: busca y escribe el resultado junto a la lista."""
    from ._native import afo_audio

    r = afo_audio.scan_plugin_folders(list_path, [])
    out = Path(list_path).with_name("plugins_scan_resultado.json")
    out.write_text(json.dumps({"plugins": len(r["plugins"]), "failed": r["failed"], "folders": r["folders"]},
                              ensure_ascii=False), encoding="utf-8")
    return 0


class PluginScanner(QObject):
    """Lanza el proceso buscador, informa del archivo que abre y lo relanza si un plugin lo tumba."""
    event = Signal(dict)

    def __init__(self, list_path: Path, parent=None):
        super().__init__(parent)
        self.list_path = Path(list_path)
        self.pedal = self.list_path.with_name("plugins_scan_pendiente.txt")
        self.result = self.list_path.with_name("plugins_scan_resultado.json")
        self.proc: QProcess | None = None
        self.restarts = 0
        self.crashed: list[str] = []
        self._last = ""
        self._since = 0.0
        self._poll = QTimer(self)
        self._poll.setInterval(300)
        self._poll.timeout.connect(self._progress)

    @property
    def running(self) -> bool:
        return self.proc is not None

    def command(self) -> tuple[str, list[str]]:
        if paths.is_frozen():                 # AllForOne.exe (Nuitka)
            return sys.executable, ["--scan-plugins", str(self.list_path)]
        return sys.executable, ["-m", "allforone", "--scan-plugins", str(self.list_path)]

    def start(self) -> bool:
        if self.proc is not None:
            return False
        self.restarts = 0
        self.crashed = []
        self.result.unlink(missing_ok=True)
        self._launch()
        return True

    def _launch(self) -> None:
        prog, args = self.command()
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedChannels)
        self.proc.setWorkingDirectory(str(Path(__file__).resolve().parent.parent))
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._error)
        self.proc.start(prog, args)
        self._since = time.monotonic()
        self._poll.start()

    def _current(self) -> str:
        try:                            # JUCE lo escribe en UTF-16 con BOM
            raw = self.pedal.read_bytes()
            text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")
            return text.strip().splitlines()[0]
        except (OSError, IndexError, UnicodeDecodeError):
            return ""

    def _progress(self) -> None:
        f = self._current()
        if self.proc is not None and time.monotonic() - self._since > HANG_SECONDS:
            log.warning("Plugin colgado al abrirlo: %s", f or "?")
            self.proc.kill()                # _finished lo cuenta como caída y sigue sin él
            return
        if f and f != self._last:
            self._last = f
            self._since = time.monotonic()
            self.event.emit({"phase": "progress", "file": f, "name": Path(f).stem, "restarts": self.restarts})

    def _error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self._poll.stop()
            self.proc = None
            self.event.emit({"phase": "done", "ok": False, "error": "No se pudo iniciar el proceso de búsqueda de plugins",
                             "crashed": [], "failed": [], "folders": []})

    def _finished(self, code: int, status) -> None:
        proc, self.proc = self.proc, None
        if proc is not None:
            proc.deleteLater()
        crashed = status == QProcess.ExitStatus.CrashExit or code != 0
        if crashed:
            bad = self._current() or self._last
            if bad:
                self.crashed.append(bad)
            log.warning("La búsqueda de plugins se cayó (código %s) con %s", code, bad or "?")
            if self.restarts < MAX_RESTARTS:
                self.restarts += 1
                self.event.emit({"phase": "progress", "file": bad, "name": Path(bad).stem if bad else "",
                                 "restarts": self.restarts, "skipped": True})
                self._launch()          # el pedal hace que ese archivo quede en la lista negra
                return
        self._poll.stop()
        try:
            res = json.loads(self.result.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            res = {"failed": [], "folders": []}
        self.event.emit({"phase": "done", "ok": not crashed, "crashed": [Path(c).name for c in self.crashed],
                         "failed": res.get("failed", []), "folders": res.get("folders", [])})

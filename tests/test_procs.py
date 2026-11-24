"""Los motores de IA local se cierran con la sesión y no se acumulan (procs.py).

Con procesos de verdad: una «sesión» (otro Python) abre un «motor» con `procs.spawn` y se la mata de
golpe (como una caída o «Finalizar tarea»): el motor tiene que morir con ella. Y `reap_orphans` cierra
un motor apuntado cuya sesión ya no existe, pero nunca uno de una sesión viva ni un proceso cuyo
ejecutable ya no es el apuntado."""
import json
import os
import subprocess
import sys
import textwrap
import time

import pytest

from allforone import procs

# el Python base (el del venv en Windows es un lanzador que abre otro proceso debajo)
PY = getattr(sys, "_base_executable", sys.executable)
SLEEP = [PY, "-c", "import time; time.sleep(120)"]


def _alive(pid: int) -> bool:
    return procs._image(pid) is not None


def _gone(pid: int, timeout: float = 10) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return False


@pytest.fixture
def datos(tmp_path, monkeypatch):
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    return tmp_path / "datos"


def test_el_motor_muere_con_la_sesion(datos, tmp_path):
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    script = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {os.path.abspath(app_dir)!r})
        from allforone import procs
        p = procs.spawn({SLEEP!r})
        print(p.pid, flush=True)
        time.sleep(120)
    """)
    env = {**os.environ, "AFO_DATA_DIR": str(datos)}
    owner = subprocess.Popen([PY, "-c", script], stdout=subprocess.PIPE, text=True, env=env)
    child = int(owner.stdout.readline())
    try:
        assert _alive(child)
        reg = json.loads((datos / "logs" / "ia_procesos.json").read_text(encoding="utf-8"))
        assert [x["pid"] for x in reg] == [child] and reg[0]["owner"] == owner.pid
        owner.kill()                                  # la sesión se cae de golpe
        owner.wait(10)
        assert _gone(child), "el motor siguió vivo tras cerrarse la sesión"
    finally:
        procs._kill(child)


def test_huerfanos_de_otra_sesion(datos):
    orphan = subprocess.Popen(SLEEP)                  # sin trabajo: como uno de antes de este arreglo
    mine = subprocess.Popen(SLEEP)
    other = subprocess.Popen(SLEEP)
    dead_owner = subprocess.Popen([PY, "-c", "pass"]); dead_owner.wait()
    try:
        me = {"owner": os.getpid(), "ownerExe": procs._image(os.getpid())}
        procs._write([
            {"pid": orphan.pid, "exe": PY, "owner": dead_owner.pid, "ownerExe": PY},
            {"pid": mine.pid, "exe": PY, **me},                                    # sesión viva
            {"pid": other.pid, "exe": r"C:\\no\\es\\este\\motor.exe", "owner": dead_owner.pid, "ownerExe": PY},
        ])
        killed = procs.reap_orphans()
        assert [x["pid"] for x in killed] == [orphan.pid]
        assert _gone(orphan.pid)
        assert _alive(mine.pid), "no se cierra lo de una sesión que sigue abierta"
        assert _alive(other.pid), "no se cierra un proceso cuyo ejecutable no es el apuntado"
        assert [x["pid"] for x in procs._read()] == [mine.pid]
    finally:
        for p in (orphan, mine, other):
            p.kill()

"""Biblioteca de proyectos (X10): Artista → Lanzamiento (Álbum o Single) → Canción.

En disco, dentro de `paths.library_dir()`:

    <Artista>/artista.json                       {nombre, creado}
    <Artista>/<Lanzamiento>/lanzamiento.json     {nombre, tipo: album|single, año, creado}
    <Artista>/<Lanzamiento>/<Canción>/<Canción>.afo

Quitar nunca borra: la carpeta pasa a `.papelera` dentro de la biblioteca. Los recientes (últimos 8
.afo abiertos o guardados, estén o no en la biblioteca) se guardan en `.recientes.json`."""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from . import paths

TRASH = ".papelera"
RECENT = ".recientes.json"
RECENT_MAX = 8
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def root() -> Path:
    return paths.library_dir()


def sanitize(name: str) -> str:
    """Nombre válido de carpeta: sin \\ / : * ? " < > |, sin espacios ni puntos en los extremos."""
    n = _BAD.sub("", str(name or "")).strip().strip(".").strip()
    if not n:
        raise ValueError("El nombre está vacío o solo tiene caracteres no permitidos")
    return n[:80]


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _read(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(p: Path, d: dict) -> None:
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _inside(path: str | Path) -> Path:
    """Ruta de la biblioteca (nunca fuera de ella ni la propia raíz)."""
    r = root().resolve()
    p = Path(path).resolve()
    if p == r or r not in p.parents:
        raise ValueError("Esa ruta no está dentro de la biblioteca")
    return p


def _level(p: Path) -> str:
    depth = len(p.relative_to(root().resolve()).parts)
    return {1: "artist", 2: "release", 3: "song"}.get(depth, "")


def _dirs(p: Path) -> list[Path]:
    return sorted((d for d in p.iterdir() if d.is_dir() and not d.name.startswith(".")), key=lambda d: d.name.lower())


def song_file(song_dir: str | Path) -> Path:
    d = Path(song_dir)
    return d / f"{d.name}.afo"


def _song(d: Path) -> dict:
    f = song_file(d)
    has = f.is_file()
    return {"kind": "song", "name": d.name, "path": str(d), "afo": str(f), "hasAfo": has,
            "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime)) if has else ""}


def _release(d: Path) -> dict:
    meta = _read(d / "lanzamiento.json")
    return {"kind": "release", "name": meta.get("nombre", d.name), "path": str(d),
            "type": meta.get("tipo", "album"), "year": meta.get("año", ""), "created": meta.get("creado", ""),
            "songs": [_song(s) for s in _dirs(d)]}


def tree() -> list[dict]:
    """Artistas con sus lanzamientos y canciones (con fechas y si la canción ya tiene .afo)."""
    out = []
    for a in _dirs(root()):
        meta = _read(a / "artista.json")
        out.append({"kind": "artist", "name": meta.get("nombre", a.name), "path": str(a),
                    "created": meta.get("creado", ""), "releases": [_release(r) for r in _dirs(a)]})
    return out


def create(kind: str, parent: str, name: str, extra: dict | None = None) -> dict:
    """Crea un artista (parent vacío), un lanzamiento (parent = artista) o una canción (parent = lanzamiento)."""
    extra = extra or {}
    n = sanitize(name)
    if kind == "artist":
        base = root()
    else:
        base = _inside(parent)
        want = {"release": "artist", "song": "release"}.get(kind)
        if not want:
            raise ValueError(f"Tipo desconocido: {kind}")
        if _level(base) != want:
            raise ValueError("Un lanzamiento va dentro de un artista y una canción dentro de un lanzamiento")
    d = base / n
    if d.exists():
        raise ValueError(f"Ya existe «{n}» aquí")
    if kind == "song" and _read(base / "lanzamiento.json").get("tipo") == "single" and _dirs(base):
        raise ValueError("Un single tiene una sola canción")
    d.mkdir(parents=True)
    if kind == "artist":
        _write(d / "artista.json", {"nombre": n, "creado": _now()})
        return {"kind": "artist", "name": n, "path": str(d)}
    if kind == "release":
        tipo = "single" if str(extra.get("type", "album")).lower() == "single" else "album"
        year = extra.get("year") or time.localtime().tm_year
        _write(d / "lanzamiento.json", {"nombre": n, "tipo": tipo, "año": int(year), "creado": _now()})
        return _release(d)
    return _song(d)


def rename(path: str, name: str) -> dict:
    p = _inside(path)
    if not p.is_dir():
        raise ValueError("No existe")
    lvl = _level(p)
    n = sanitize(name)
    q = p.with_name(n)
    if q.exists() and q != p:
        raise ValueError(f"Ya existe «{n}» aquí")
    old_afo = song_file(p)
    p.rename(q)
    if lvl == "artist":
        meta = _read(q / "artista.json"); meta["nombre"] = n; _write(q / "artista.json", meta)
    elif lvl == "release":
        meta = _read(q / "lanzamiento.json"); meta["nombre"] = n; _write(q / "lanzamiento.json", meta)
    elif lvl == "song":
        moved = q / old_afo.name
        if moved.is_file():
            moved.rename(song_file(q))
    _fix_recent(p, q)
    return {"kind": lvl, "name": n, "path": str(q)}


def remove(path: str) -> dict:
    """A la papelera de la biblioteca (nunca se borra del disco)."""
    p = _inside(path)
    if not p.is_dir() or p.parent.name == TRASH or TRASH in p.relative_to(root().resolve()).parts:
        raise ValueError("No existe")
    trash = root() / TRASH
    trash.mkdir(exist_ok=True)
    dest = trash / f"{time.strftime('%Y%m%d_%H%M%S')}_{p.name}"
    k = 1
    while dest.exists():
        k += 1
        dest = trash / f"{time.strftime('%Y%m%d_%H%M%S')}_{p.name}_{k}"
    shutil.move(str(p), str(dest))
    return {"trash": str(dest)}


def where(afo: str) -> dict:
    """Artista, lanzamiento y canción de un .afo de la biblioteca (vacío si está fuera)."""
    try:
        p = _inside(Path(afo).parent)
    except ValueError:
        return {}
    if _level(p) != "song":
        return {}
    return {"artist": p.parent.parent.name, "release": p.parent.name, "song": p.name}


# --- recientes -------------------------------------------------------------------------------
def _recent_path() -> Path:
    return root() / RECENT


def touch(afo: str) -> None:
    """Apunta un .afo abierto o guardado en los recientes."""
    p = str(Path(afo).resolve())
    lst = [x for x in _read(_recent_path()).get("files", []) if x != p]
    _write(_recent_path(), {"files": [p] + lst[: RECENT_MAX * 2]})


def _fix_recent(old: Path, new: Path) -> None:
    lst = _read(_recent_path()).get("files", [])
    o = str(old.resolve())
    fixed = []
    for x in lst:
        if x == o or x.startswith(o + "\\") or x.startswith(o + "/"):
            x = str(new.resolve()) + x[len(o):]
            if Path(x).name.lower().endswith(".afo") and not Path(x).is_file() and Path(x).parent.name == new.name:
                x = str(song_file(Path(x).parent))
        fixed.append(x)
    if fixed != lst:
        _write(_recent_path(), {"files": fixed})


def recent() -> list[dict]:
    out = []
    for x in _read(_recent_path()).get("files", []):
        p = Path(x)
        if p.is_file():
            out.append({"path": str(p), "name": p.stem, **where(str(p)),
                        "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))})
        if len(out) >= RECENT_MAX:
            break
    return out

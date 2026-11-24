"""Biblioteca (X10): Artista → Lanzamiento (Álbum o Single) → Canción, en disco y por el puente."""
import json
from pathlib import Path

import pytest

from allforone import library


@pytest.fixture(autouse=True)
def datos(tmp_path, monkeypatch):
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    yield tmp_path / "datos" / "biblioteca"


def test_artistas_album_single_renombrar_quitar(datos):
    a1 = library.create("artist", "", "Luna Roja", {})
    a2 = library.create("artist", "", 'Los "Raros"/2', {})
    assert a2["name"] == "Los Raros2"                               # nombre saneado
    assert json.loads((Path(a1["path"]) / "artista.json").read_text(encoding="utf-8"))["nombre"] == "Luna Roja"
    alb = library.create("release", a1["path"], "Noches", {"type": "album", "year": 2026})
    for n in ("Intro", "Fuego", "Final"):
        library.create("song", alb["path"], n, {})
    sg = library.create("release", a2["path"], "Verano", {"type": "single"})
    s1 = library.create("song", sg["path"], "Verano", {})
    with pytest.raises(ValueError, match="single"):
        library.create("song", sg["path"], "Otra", {})
    with pytest.raises(ValueError, match="Ya existe"):
        library.create("song", alb["path"], "Fuego", {})
    with pytest.raises(ValueError):
        library.create("song", a1["path"], "Mal sitio", {})       # una canción va en un lanzamiento
    with pytest.raises(ValueError):
        library.create("artist", "", ' :*? ', {})

    # el .afo de una canción: se guarda en su carpeta y sale en recientes con su sitio
    afo = Path(s1["afo"])
    afo.write_text("{}", encoding="utf-8")
    library.touch(str(afo))
    t = {a["name"]: a for a in library.tree()}
    assert set(t) == {"Luna Roja", "Los Raros2"}
    noches = t["Luna Roja"]["releases"][0]
    assert noches["type"] == "album" and noches["year"] == 2026
    assert [s["name"] for s in noches["songs"]] == ["Final", "Fuego", "Intro"]
    assert t["Los Raros2"]["releases"][0]["songs"][0]["hasAfo"]
    assert library.recent()[0]["song"] == "Verano" and library.recent()[0]["artist"] == "Los Raros2"

    # renombrar una canción mueve su .afo y los recientes la siguen
    r = library.rename(s1["path"], "Verano Eterno")
    assert Path(r["path"]).name == "Verano Eterno" and library.song_file(r["path"]).is_file()
    assert library.recent()[0]["song"] == "Verano Eterno"
    r2 = library.rename(alb["path"], "Noches Largas")
    assert json.loads((Path(r2["path"]) / "lanzamiento.json").read_text(encoding="utf-8"))["nombre"] == "Noches Largas"

    # quitar = a la papelera de la biblioteca, nunca borrado
    gone = library.remove(t["Luna Roja"]["path"])
    assert Path(gone["trash"]).is_dir() and (Path(gone["trash"]) / "Noches Largas" / "Fuego").is_dir()
    assert [a["name"] for a in library.tree()] == ["Los Raros2"]
    with pytest.raises(ValueError):
        library.remove(str(datos.parent))                          # fuera de la biblioteca
    with pytest.raises(ValueError):
        library.rename(str(datos), "x")                            # la raíz no se toca


def test_slots_del_puente(datos):
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.instance() or QCoreApplication([])
    from allforone.bridge import Bridge

    class _Host:                                                   # los slots de la biblioteca no usan el motor
        ok = False
        engine = None
        tracks = {}
    b = Bridge(_Host())
    a = json.loads(b.libraryCreate("artist", "", "Neón", "{}"))
    assert a["ok"], a
    rel = json.loads(b.libraryCreate("release", a["item"]["path"], "Uno", json.dumps({"type": "single"})))
    song = json.loads(b.libraryCreate("song", rel["item"]["path"], "Uno", "{}"))
    assert song["ok"] and not song["item"]["hasAfo"]
    bad = json.loads(b.libraryCreate("song", rel["item"]["path"], "Dos", "{}"))
    assert not bad["ok"] and "single" in bad["error"]
    tree = json.loads(b.libraryTree())["tree"]
    assert tree[0]["releases"][0]["type"] == "single"
    assert json.loads(b.libraryRename(a["item"]["path"], "Neón 2"))["ok"]
    assert json.loads(b.libraryRecent())["recent"] == []
    assert json.loads(b.libraryRemove(str(datos / "Neón 2")))["ok"]
    assert not json.loads(b.libraryRemove(str(datos / "no existe")))["ok"]

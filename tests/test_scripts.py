"""F8: scripts del usuario (scripts/*.py con la API afo) sobre proyectos completos de `song_factory`.

Cada script de ejemplo corre en un proceso aparte (`python -m allforone --run-script`) con la copia
del proyecto que manda la interfaz y devuelve sus órdenes; aquí se comprueba lo que piden. Que la
ventana las aplique y que Ctrl+Z las deshaga de una vez lo mide la autoprueba (`_f8_checks`).
"""
import json
import threading
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import song_factory as F
from allforone import script_host as S

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TIPO = {"Voz": "voz"}


def _snapshot(song: dict) -> dict:
    """La copia del proyecto tal como la arma la interfaz más lo que añade el puente (archivo y clips)."""
    g = song["genre"]
    tracks = []
    for i, p in enumerate(song["paths"]):
        name = Path(p).stem.split("_", 1)[1]
        dur = sf.info(p).duration
        # la voz principal en dos clips (estrofa y resto) para ver que cada clip se normaliza por su cuenta
        clips = ([{"id": 1, "start": 0.0, "length": dur / 2, "offset": 0.0, "speed": 1.0, "gain_db": 0.0},
                  {"id": 2, "start": dur / 2, "length": dur / 2, "offset": dur / 2, "speed": 1.0, "gain_db": -6.0}]
                 if name == "Voz_Lead" else
                 [{"id": 1, "start": 0.0, "length": dur, "offset": 0.0, "speed": 1.0, "gain_db": 0.0}])
        tracks.append({"uid": f"a{i}", "id": i, "type": "audio", "name": name, "vol_db": 0.0, "pan": 0.0,
                       "mute": False, "solo": False, "color": "", "path": p, "clips": clips})
    return {"bpm": g.bpm, "key": {"key": "", "scale": ""}, "chords": [], "markers": [], "tracks": tracks,
            "effects": ["eq", "compressor", "space"]}


def _run(file: str, snap: dict, folder: Path = SCRIPTS) -> dict:
    """Lanza el script como lo hace la app: proceso aparte, resultado por el evento «scriptDone»."""
    done, got = threading.Event(), {}
    r = S.ScriptRunner(lambda ev: (got.update(ev), done.set())).run(file, snap, folder)
    assert r["ok"], r
    assert done.wait(240), "el script no terminó"
    assert got["type"] == "scriptDone"
    return got


@pytest.fixture(scope="module")
def trap(tmp_path_factory):
    return F.write_song("trap", tmp_path_factory.mktemp("trap"))


def test_lista_de_scripts():
    s = {x["file"]: x for x in S.list_scripts(SCRIPTS)}
    assert {"normalizar_voces.py", "colorear_por_tipo.py", "exportar_stems.py", "marcadores_por_seccion.py"} <= set(s)
    assert s["normalizar_voces.py"]["name"] == "Normalizar las voces" and s["normalizar_voces.py"]["id"] == "script.normalizar_voces"
    assert all(x["tip"] for x in s.values())
    from allforone import actions
    ids = {a["id"]: a for a in actions.actions()}
    assert ids["script.normalizar_voces"]["menu"] == "Scripts" and "script.folder" in ids


def test_normalizar_voces(trap):
    snap = _snapshot(trap)
    r = _run("normalizar_voces.py", snap)
    assert r["ok"], r
    cmds = r["commands"]
    voces = {t["uid"]: t for t in snap["tracks"] if "Voz" in t["name"]}
    assert cmds and all(c["op"] == "clip_gain" and c["uid"] in voces for c in cmds)
    assert len(cmds) == sum(len(t["clips"]) for t in voces.values())         # 3 clips: 2 de la principal y el doble
    for c in cmds:                                                          # el pico del clip queda en −3 dBFS
        t = voces[c["uid"]]
        k = next(x for x in t["clips"] if x["id"] == c["clip"])
        x, sr = sf.read(t["path"], dtype="float32", always_2d=True)
        seg = x[int(k["offset"] * sr):int((k["offset"] + k["length"]) * sr)].mean(axis=1)
        assert abs(20 * np.log10(np.max(np.abs(seg))) + c["db"] - (-3.0)) < 0.05, c
    assert "3 clip(s)" in r["log"][-1]


def test_colorear_por_tipo(trap):
    snap = _snapshot(trap)
    r = _run("colorear_por_tipo.py", snap)
    assert r["ok"], r
    by = {next(t["name"] for t in snap["tracks"] if t["uid"] == c["uid"]): c["color"] for c in r["commands"]}
    assert by["Kick"] == by["Clap"] == by["HiHat"] == by["808"] == "drums"
    assert by["Voz_Lead"] == by["Voz_Doble"] == "cinta"
    assert all(c["op"] == "track" and c["color"] in S.COLORS for c in r["commands"])
    assert len(r["commands"]) == len(snap["tracks"])


def test_marcadores_por_seccion(tmp_path):
    """Canción A-B-A-B (A sin batería ni bajo): un marcador por sección, con su letra y su número."""
    from test_analisis_proyecto import _con_secciones
    y, g, truth = _con_secciones("rock", [(4, "A"), (8, "B"), (4, "A"), (8, "B")])
    p = tmp_path / "rock_secciones.wav"
    sf.write(str(p), y, 22050)
    snap = {"bpm": g.bpm, "tracks": [{"uid": "a1", "id": 1, "type": "audio", "name": "Mezcla", "path": str(p),
                                       "clips": [{"id": 1, "start": 0.0, "length": y.size / 22050, "offset": 0.0}]}]}
    r = _run("marcadores_por_seccion.py", snap)
    assert r["ok"], r
    (c,) = r["commands"]
    assert c["op"] == "markers" and [m["label"] for m in c["markers"]] == ["A1", "B1", "A2", "B2"]
    for (t0, _), m in zip(truth, c["markers"]):
        assert abs(t0 - m["start"]) < 60 / g.bpm / 2


def test_exportar_stems(trap):
    snap = _snapshot(trap)
    snap["tracks"][0]["mute"] = True                    # la silenciada no se exporta
    r = _run("exportar_stems.py", snap)
    assert r["ok"], r
    (c,) = r["commands"]
    assert c["op"] == "export_stems" and c["uids"] == [t["uid"] for t in snap["tracks"][1:]]


def test_script_que_falla_no_cambia_nada(trap, tmp_path):
    """Un error a medias no deja órdenes sueltas (todo o nada) y dice la línea; tampoco puede salirse
    de la carpeta de scripts."""
    (tmp_path / "a_medias.py").write_text(
        "afo.tracks()[0].set_volume(-6)\nafo.tracks()[1].rename('X')\n1 / 0\n", encoding="utf-8")
    (tmp_path / "mal_color.py").write_text("afo.tracks()[0].set_color('#ff0000')\n", encoding="utf-8")
    r = _run("a_medias.py", _snapshot(trap), tmp_path)
    assert not r["ok"] and r["commands"] == [] and "ZeroDivisionError" in r["error"] and "línea 3" in r["error"]
    r = _run("mal_color.py", _snapshot(trap), tmp_path)
    assert not r["ok"] and "#ff0000" in r["error"] and r["commands"] == []
    bad = S.ScriptRunner(lambda ev: None).run("../tests/conftest.py", {}, SCRIPTS)
    assert not bad["ok"]


def test_api_completa(trap, tmp_path):
    """Pistas, volumen, paneo, mute, nombre, efectos, canción y transporte: cada llamada deja su orden."""
    (tmp_path / "todo.py").write_text("""
v = afo.track('Voz_Lead')
v.set_volume(-4.5); v.set_pan(-0.3); v.rename('Voz principal'); v.add_effect('compressor')
afo.track('Kick').set_mute(True)
afo.set_key('F', 'Menor'); afo.seek(12); afo.play(); afo.stop()
afo.log('hecho', len(afo.tracks()))
""", encoding="utf-8")
    snap = _snapshot(trap)
    r = _run("todo.py", snap, tmp_path)
    assert r["ok"], r
    ops = [(c["op"], {k: v for k, v in c.items() if k not in ("op", "uid")}) for c in r["commands"]]
    assert ops == [("track", {"vol_db": -4.5}), ("track", {"pan": -0.3}), ("track", {"name": "Voz principal"}),
                   ("fx", {"key": "compressor"}), ("track", {"mute": True}), ("key", {"key": "F", "scale": "Menor"}),
                   ("seek", {"t": 12.0}), ("play", {}), ("stop", {})]
    assert r["log"] == [f"hecho {len(snap['tracks'])}"]

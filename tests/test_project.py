"""Presets de efectos y proyecto recuperable (.afo): el criterio del Hito 1 — «una mezcla sencilla
con efectos reales, A/B, automatización y proyecto recuperable» — medido con renders del motor."""
import json

import numpy as np
import pytest
import soundfile as sf

from allforone import fx_presets, project
from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
SR = 48000


@pytest.fixture()
def bridge(qapp):
    from allforone.bridge import Bridge
    h = EngineHost.create()
    assert h.ok, h.error
    b = Bridge(h)
    yield b
    b._timer.stop()
    b._mixer_timer.stop()
    h.engine = None


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtCore import QCoreApplication
    return QCoreApplication.instance() or QCoreApplication([])


def call(b, name, *args):
    r = json.loads(getattr(b, name)(*args))
    assert r["ok"], r.get("error")
    return r


def tone(path, amp_db=-18.0, seconds=4.0, hz=440.0):
    t = np.arange(int(seconds * SR)) / SR
    y = 10 ** (amp_db / 20) * np.sin(2 * np.pi * hz * t)
    sf.write(str(path), np.stack([y, y], 1), SR, subtype="FLOAT")
    return str(path)


def levels(eng, tmp_path, name):
    out = tmp_path / name
    assert eng.render_to_wav(str(out))
    y, _ = sf.read(str(out))
    y = y[:, 0]
    return [20 * np.log10(np.sqrt(np.mean(y[a * SR:(a + 1) * SR] ** 2)) + 1e-12) for a in range(4)]


def test_presets_de_fabrica_validos():
    """Cada preset de fábrica nombra parámetros que existen y valores dentro de su rango."""
    cat = {d["key"]: d for d in afo_audio.effect_catalog()}
    assert set(fx_presets.FACTORY) == set(cat), "cada módulo del Hito 1 tiene presets"
    for key, presets in fx_presets.FACTORY.items():
        params = {p["id"]: p for p in cat[key]["params"]}
        assert len(presets) >= 3
        for name, vals in presets.items():
            for pid, v in vals.items():
                assert pid in params, (key, name, pid)
                assert params[pid]["min"] <= v <= params[pid]["max"], (key, name, pid, v)


def test_preset_aplica_y_se_guarda(bridge, tmp_path):
    b = bridge
    tid = b.host.add_audio(tone(tmp_path / "t.wav"), "t")["id"]
    fx = call(b, "fxAdd", tid, "delay", -1)["effect"]["id"]
    eff = call(b, "fxApplyPreset", fx, "Ping-pong")["effect"]
    desc = {p["id"]: i for i, p in enumerate(next(d for d in afo_audio.effect_catalog() if d["key"] == "delay")["params"])}
    assert eff["values"][desc["pingpong"]] == 1 and eff["values"][desc["sync"]] == 2
    assert eff["values"][desc["hp"]] == pytest.approx(120)          # no nombrado: vuelve al defecto
    call(b, "fxParam", fx, "feedback", 61.0)
    names = [p["name"] for p in call(b, "fxSavePreset", fx, "Mío")["presets"]]
    assert "Mío" in names
    call(b, "fxApplyPreset", fx, "Corchea")
    eff = call(b, "fxApplyPreset", fx, "Mío")["effect"]
    assert eff["values"][desc["feedback"]] == pytest.approx(61.0)
    assert json.loads(b.fxSavePreset(fx, "Corchea"))["ok"] is False   # no pisa uno de fábrica
    assert "Mío" not in [p["name"] for p in call(b, "fxDeletePreset", "delay", "Mío")["presets"]]


def test_proyecto_recupera_efectos_y_automatizacion(bridge, tmp_path):
    """Guardar → sesión nueva → abrir → el render es el mismo (efectos, puenteo y automatización)."""
    b = bridge
    eng = b.host.engine
    src = tone(tmp_path / "voz.wav")
    tid = b.host.add_audio(src, "Voz")["id"]
    g = call(b, "fxAdd", tid, "gain", -1)["effect"]["id"]
    call(b, "fxSetAutomation", g, "output", json.dumps([[0, -24], [2, -24], [2.0001, 0], [4, 0]]))
    off = call(b, "fxAdd", tid, "saturator", -1)["effect"]["id"]
    call(b, "fxEnable", off, False)                                   # puenteado: no cambia el render
    m = call(b, "fxAdd", 0, "gain", -1)["effect"]["id"]               # efecto en el master
    call(b, "fxParam", m, "output", -3.0)
    before = levels(eng, tmp_path, "a.wav")
    assert before[0] == pytest.approx(-21.01 - 24 - 3, abs=0.2)
    assert before[3] == pytest.approx(-21.01 - 3, abs=0.2)

    ui = {"bpm": 100, "tracks": [{"uid": "a1", "id": tid, "type": "audio", "name": "Voz", "vol": 70, "pan": 50}]}
    saved = call(b, "projectSave", json.dumps(ui), str(tmp_path / "sesion"))["path"]
    assert saved.endswith("sesion.afo")

    # Sesión nueva: se borra todo y se reconstruye solo con el archivo
    for e in eng.effects(0):
        eng.remove_effect(e["id"])
    b.host.remove(tid)
    doc = call(b, "projectOpen", saved)["doc"]
    assert doc["bpm"] == 100 and doc["missing"] == []
    t = doc["tracks"][0]
    assert t["path"] and [f["key"] for f in t["fx"]] == ["gain", "saturator"]
    assert t["fx"][0]["automation"]["output"][2][1] == 0
    nid = call(b, "addAudioPath", t["path"], t["name"])["track"]["id"]
    call(b, "fxRestore", nid, json.dumps(t["fx"]))
    call(b, "fxRestore", 0, json.dumps(doc["master_fx"]))
    chain = eng.effects(nid)
    assert [e["enabled"] for e in chain] == [True, False]
    assert chain[0]["automated"] == ["output"]
    after = levels(eng, tmp_path, "b.wav")
    assert np.allclose(before, after, atol=0.05), (before, after)


def test_proyecto_rutas_relativas(tmp_path):
    """Si se mueve la carpeta del proyecto con sus audios, se encuentran por la ruta relativa."""
    d = tmp_path / "p"
    d.mkdir()
    wav = tone(d / "toma.wav", seconds=0.2)
    doc = {"format": project.FORMAT, "version": 1, "tracks": [{"type": "voz", "name": "Voz 1", "path": wav}]}
    project.save(d / "x.afo", doc)
    moved = tmp_path / "movida"
    d.rename(moved)
    got = project.load(moved / "x.afo")
    assert got["missing"] == [] and got["tracks"][0]["path"] == str((moved / "toma.wav").resolve())
    (moved / "toma.wav").unlink()
    assert project.load(moved / "x.afo")["missing"] == ["Voz 1"]
    (moved / "y.afo").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        project.load(moved / "y.afo")

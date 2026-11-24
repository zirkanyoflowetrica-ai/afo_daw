"""Instrumental Lab (lab.py) con PROYECTOS COMPLETOS de hip-hop, trap, lo-fi, house y cinematográfica.

Cada prueba hace lo que haría el usuario desde la interfaz, por el puente:
  sesión nueva con el contexto del género → guía = la canción entera → Demucs da la V1 de cada
  familia → 2 variantes con ACE-Step «lego» → se bloquea una y se regenera → se reabre del disco.
Se mide lo que importa: longitud exacta (compases × compás × 60 / BPM), variantes distintas entre sí,
la batería generada sigue el tempo del contexto (ataques en la rejilla), la bloqueada se conserva y el historial guarda las
demás. Las pruebas con motores se saltan si faltan ACE-Step, el modelo base o Demucs."""
import json
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import song_factory as F
from allforone import lab as L
from allforone.engine_host import EngineHost, afo_audio

_ST = L.Lab(lambda e: None).status()
engines = pytest.mark.skipif(not (afo_audio and _ST["engineOk"] and _ST["legoOk"] and _ST["demucsOk"]),
                             reason="sin ACE-Step (modelo base) o sin Demucs")


# ---------------- sin motores ----------------------------------------------------------------
def test_contexto_y_longitud_exacta():
    c = L.make_context({"style": "House", "bpm": 124, "key": "G minor", "bars": 8})
    assert c["seconds"] == pytest.approx(8 * 4 * 60 / 124, abs=1e-3) and c["variants"] == 4
    assert L.n_samples(c) == round(8 * 4 * 60 / 124 * 44100)
    for bad in ({"bpm": 20}, {"bars": 1, "bpm": 200}, {"style": "Polka"}, {"key": "H major"}, {"beats": 5}):
        with pytest.raises(ValueError):
            L.make_context(bad)
    x = np.ones((1000, 2), dtype="float32")
    assert L.fit(x, 1500).shape == (1500, 2) and L.fit(x, 700).shape == (700, 2)
    assert float(np.abs(L.fit(x, 1500)[1200:]).max()) == 0.0, "lo que falta se completa con silencio"


def test_sesion_elegir_bloquear_quitar_y_reabrir(tmp_path, monkeypatch):
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    events = []
    lab = L.Lab(events.append)
    st = lab.new({"style": "Trap", "bpm": 140, "key": "F minor", "bars": 4, "variants": 2})
    assert [f["name"] for f in st["families"]] == L.DEFAULT_FAMILIES["Trap"]
    n = L.n_samples(st["context"])
    rng = np.random.default_rng(3)
    a = lab._add_variant("Batería", rng.standard_normal((n, 2)).astype("float32") * 0.1, "prueba", 1, None)
    b = lab._add_variant("Batería", rng.standard_normal((n, 2)).astype("float32") * 0.1, "prueba", 2, None)
    st = lab.public()
    fam = st["families"][0]
    assert fam["chosen"] == a["id"] and [v["label"] for v in fam["variants"]] == ["V1", "V2"]
    assert set(fam["variants"][0]["parts"]) == set(L.S.DRUM_PARTS), "la batería trae Bombo, Caja / Clap y Platos"
    assert len(fam["variants"][0]["disc"]["env"]) == 48 and fam["variants"][0]["disc"]["env"] != fam["variants"][1]["disc"]["env"]
    lab.set_flag("Batería", b["id"], "chosen", True)
    lab.set_flag("Batería", b["id"], "locked", True)
    lab.set_flag("Batería", a["id"], "favorite", True)
    assert [f["id"] for f in L.Lab.favorites()] == [a["id"]]
    lab.remove("Batería", a["id"])
    assert (Path(st["folder"]) / ".papelera" / f"bateria_{a['id']}.wav").is_file()
    assert any(e["type"] == "labState" for e in events)
    again = L.Lab(lambda e: None).open(st["folder"])
    fam = again["families"][0]
    assert [v["id"] for v in fam["variants"]] == [b["id"]] and fam["chosen"] == b["id"] and fam["variants"][0]["locked"]
    assert L.Lab.sessions()[0]["folder"] == st["folder"]
    other = L.Lab(lambda e: None)
    other.new({"style": "Trap", "bars": 4, "bpm": 140})
    with pytest.raises(RuntimeError):            # sin guía ni otras familias no hay contexto
        other.context_mix("Bajo")
    ctx = lab.context_mix("Bajo")                # con la batería elegida, el contexto es esa batería
    assert ctx.shape == (n, 2) and L.S.rms_db(ctx) > -40


# ---------------- con motores, proyectos completos ---------------------------------------------
def _wait(app, h, events, start, timeout=900):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        app.processEvents()
        h.pump()
        done = [e for e in events[start:] if e.get("type") == "labJob" and e.get("phase") == "done"]
        if done:
            return done[0]
        time.sleep(0.05)
    raise TimeoutError("el laboratorio no terminó")


GENEROS = [("hiphop", "Hip hop", "Batería"), ("trap", "Trap", "Batería"), ("lofi", "Lo-fi", "Batería"),
           ("house", "House", "Batería"), ("cinematico", "Cinemático", "Cuerdas")]


@engines
@pytest.mark.parametrize("genre,style,family", GENEROS)
def test_laboratorio_proyecto_completo(genre, style, family, tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    from allforone.bridge import Bridge
    g = F.TODOS[genre]
    song = F.write_song(genre, tmp_path / "stems")
    mix = sum(sf.read(p, always_2d=True, dtype="float32")[0] for p in song["paths"])
    mpath = tmp_path / f"{genre}.wav"
    sf.write(str(mpath), mix / np.max(np.abs(mix)) * 0.9, 44100)
    h = EngineHost.create()
    assert h.ok, h.error
    b = Bridge(h)
    events = []
    b.aiEvent.connect(lambda s: events.append(json.loads(s)))
    try:
        key = f"{g.key} {'minor' if g.minor else 'major'}"
        r = json.loads(b.labNew(json.dumps({"style": style, "bpm": g.bpm, "key": key, "bars": 4, "variants": 2,
                                            "name": f"Prueba {genre}"})))
        assert r["ok"], r
        n = L.n_samples(r["state"]["context"])
        # 1) guía = la canción completa → V1 por familia con Demucs
        i = len(events)
        assert json.loads(b.labGuideFile(str(mpath)))["ok"]
        assert json.loads(b.aiGenerate("{}"))["ok"] is False, "un motor de IA a la vez"
        done = _wait(app, h, events, i)
        assert done["ok"], done
        st = b.lab.public()
        v1 = {f["name"]: f["variants"] for f in st["families"] if f["variants"]}
        assert v1, "la guía da al menos una V1"
        for vs in v1.values():
            assert sf.info(vs[0]["path"]).frames == n
        # 2) dos variantes nuevas de la familia con «lego» sobre el contexto
        i = len(events)
        assert json.loads(b.labGenerate(family, 2))["ok"]
        done = _wait(app, h, events, i)
        assert done["ok"], done
        fam = next(f for f in b.lab.public()["families"] if f["name"] == family)
        new = [v for v in fam["variants"] if v["task"] == "lego"]
        assert len(new) == 2 and new[0]["seed"] != new[1]["seed"]
        ys = [sf.read(v["path"], always_2d=True, dtype="float32")[0] for v in new]
        assert all(y.shape[0] == n for y in ys), "longitud exacta"
        assert all(L.S.rms_db(y) > -45 for y in ys), [L.S.rms_db(y) for y in ys]
        corr = float(np.corrcoef(ys[0].mean(axis=1), ys[1].mean(axis=1))[0, 1])
        grids = [L.grid_score(y, g.bpm) for y in ys]
        assert grids == [v["grid"] for v in new] and [v["onGrid"] for v in new] == [x >= L.ON_GRID for x in grids]
        v1 = next((v for v in fam["variants"] if v["task"] == "guia"), None)
        print(f"{genre} · {family}: correlación entre variantes {corr:.2f}; a tempo ({g.bpm:g} BPM) "
              f"{', '.join(f'{x:.2f}' for x in grids)} (guía {v1['grid'] if v1 else '—'}, azar ≈ 1,3); "
              f"intentos {[v['tries'] for v in new]}; {done['message']}")
        assert abs(corr) < 0.5, corr
        if family == "Batería":
            assert set(new[0]["parts"]) <= set(L.S.DRUM_PARTS) and new[0]["parts"]
            assert max(grids) >= L.ON_GRID, grids        # al menos una sigue el tempo del contexto
        # 3) bloquear una y regenerar: la bloqueada queda, las demás pasan al historial
        locked = new[0]["id"]
        assert json.loads(b.labSet(family, locked, "locked", True))["ok"]
        before = {v["id"] for v in fam["variants"]}
        i = len(events)
        assert json.loads(b.labRegenerate(family))["ok"]
        done = _wait(app, h, events, i)
        assert done["ok"], done
        st = b.lab.public()
        fam = next(f for f in st["families"] if f["name"] == family)
        ids = [v["id"] for v in fam["variants"]]
        assert locked in ids and len(ids) == 2, ids
        assert {v["id"] for v in st["history"]} == before - {locked}
        assert all(Path(v["path"]).is_file() for v in st["history"]), "el historial no borra el audio"
        # 4) reabrir desde el disco
        again = L.Lab(lambda e: None).open(st["folder"])
        assert json.dumps(again["families"]) == json.dumps(st["families"])
    finally:
        b.lab.cancel()
        b._timer.stop()
        b._mixer_timer.stop()
        h.engine = None


@engines
@pytest.mark.skipif(not _ST["textOk"], reason="sin los modelos del compositor")
def test_guia_compuesta_y_parecida(tmp_path, monkeypatch):
    """Kit completo desde texto (hip-hop) y «parecida a esta» con la tarea cover."""
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    events = []
    lab = L.Lab(events.append)
    st = lab.new({"style": "Hip hop", "bpm": 90, "key": "D minor", "bars": 4, "variants": 2,
                  "prompt": "dusty boom bap, warm rhodes"})
    n = L.n_samples(st["context"])
    lab.guide_text()
    t0 = time.monotonic()
    while not any(e.get("type") == "labJob" and e.get("phase") == "done" for e in events):
        assert time.monotonic() - t0 < 900
        time.sleep(0.2)
    done = next(e for e in events if e.get("type") == "labJob" and e.get("phase") == "done")
    assert done["ok"], done
    st = lab.public()
    assert sf.info(st["guide"]["path"]).frames == n
    have = [f for f in st["families"] if f["variants"]]
    print("Guía compuesta:", done["message"])
    assert have, "la guía compuesta da al menos una V1"
    fam = have[0]
    src = fam["variants"][0]
    events.clear()
    lab.similar(fam["name"], src["id"], 0.5)
    t0 = time.monotonic()
    while not any(e.get("type") == "labJob" and e.get("phase") == "done" for e in events):
        assert time.monotonic() - t0 < 900
        time.sleep(0.2)
    done = next(e for e in events if e.get("type") == "labJob" and e.get("phase") == "done")
    assert done["ok"], done
    st = lab.public()
    fam = next(f for f in st["families"] if f["name"] == fam["name"])
    cov = next(v for v in fam["variants"] if v["task"] == "cover")
    y0 = sf.read(src["path"], always_2d=True, dtype="float32")[0]
    y1 = sf.read(cov["path"], always_2d=True, dtype="float32")[0]
    assert y1.shape[0] == n
    b0, b1 = np.array(src["disc"]["bands"]), np.array(cov["disc"]["bands"])
    sim = float(np.dot(b0, b1) / (np.linalg.norm(b0) * np.linalg.norm(b1) + 1e-12))
    print(f"Parecida ({fam['name']}): similitud del espectro {sim:.2f}, correlación {np.corrcoef(y0.mean(1), y1.mean(1))[0, 1]:.2f}")
    assert sim > 0.8 and L.S.rms_db(y1) > -45

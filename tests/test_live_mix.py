"""Mezcla y mastering automáticos EN VIVO: las decisiones del V4.2 quedan como fader, paneo y cadenas
de efectos reales del motor, el master se decide midiendo la sesión en memoria y no se escribe audio."""
import json
import time

import pytest

from allforone import mixer_service, project
from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
PLATAFORMAS = "Plataformas (-14 LUFS, -2 dBTP)"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtCore import QCoreApplication
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture()
def mixed(qapp, tmp_path, monkeypatch):
    """Los 3 stems de demostración en el motor, mezclados en vivo desde el puente."""
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    from allforone.bridge import Bridge
    from allforone.selftest import _write_demo_stems
    h = EngineHost.create()
    assert h.ok, h.error
    b = Bridge(h)
    events = []
    b.mixerEvent.connect(lambda s: events.append(json.loads(s)))
    m = mixer_service.load()
    stems = []
    for p in _write_demo_stems(tmp_path / "stems"):
        d = mixer_service.describe(m, p)
        d["trackId"] = h.add_audio(p)["id"]
        stems.append(d)
    r = json.loads(b.mixer("mix", json.dumps({"stems": stems, "space": 45})))
    assert r["ok"], r
    t0 = time.monotonic()
    while not any(e["type"] in ("done", "error") for e in events) and time.monotonic() - t0 < 120:
        qapp.processEvents()
        h.pump()
    yield b, h, stems, events
    b._timer.stop()
    b._mixer_timer.stop()
    h.engine = None


def test_decisiones_como_faders_y_cadenas_reales(mixed):
    b, h, stems, events = mixed
    done = next(e for e in events if e["type"] in ("done", "error"))
    assert done["type"] == "done" and done["applied"] == 3, done
    voz = next(s for s in stems if s["kind"] == "Voz principal")["trackId"]
    keys = [e["key"] for e in h.engine.effects(voz)]
    assert keys[:2] == ["eq", "deesser"] and {"saturator", "space", "delay"} <= set(keys)
    chain = json.loads(b.fxList(voz))["chain"]
    assert all(e["auto"] and e["label"] for e in chain)
    strips = [e for e in events if e["type"] == "strip" and e.get("phase") == "done"]
    assert len(strips) == 3 and all(e["chain"] for e in strips)
    # El fader decidido es real: la pista suena con esa ganancia (misma toma, fader a 0 dB y al decidido)
    kick = next(e for e in strips if e["kind"] == "Kick")
    with_gain = h.engine.measure_mix()["tracks"][kick["trackId"]]["lufs_i"]
    h.engine.set_track_gain_db(kick["trackId"], 0.0)
    unity = h.engine.measure_mix()["tracks"][kick["trackId"]]["lufs_i"]
    assert with_gain - unity == pytest.approx(kick["gain_db"], abs=0.3)
    assert done["skipped"], "lo que no se reproduce en vivo se informa"


def test_master_en_vivo_sin_archivos(mixed, tmp_path):
    b, h, stems, _ = mixed
    before = set(tmp_path.rglob("*.wav"))
    r = json.loads(b.mixer("master", json.dumps({"preset": PLATAFORMAS})))
    assert r["ok"], r
    st = r["stats"]
    assert abs(st["lufs_i"] + 14) < 1.0 and st["max_peak_db"] <= -1.9, st
    assert h.engine.master_ceiling() == pytest.approx(-2.0)
    assert [e["key"] for e in h.engine.effects(0)][:2] == ["gain", "eq"]
    assert set(tmp_path.rglob("*.wav")) == before, "masterizar no escribe audio"
    # A/B: puentear la cadena del master y volver
    json.loads(b.mixer("bypass", json.dumps({"bypass": True, "track": 0})))
    assert not any(e["enabled"] for e in h.engine.effects(0))
    json.loads(b.mixer("bypass", json.dumps({"bypass": False, "track": 0})))
    assert all(e["enabled"] for e in h.engine.effects(0))
    # Quitar el master IA deja el master como estaba
    json.loads(b.mixer("unmaster", "{}"))
    assert h.engine.effects(0) == [] and h.engine.master_ceiling() == pytest.approx(-1.0)


def test_proyecto_conserva_la_mezcla_automatica(mixed):
    b, h, stems, _ = mixed
    voz = next(s for s in stems if s["kind"] == "Voz principal")["trackId"]
    doc = project.collect({"tracks": [{"id": voz, "type": "audio"}]}, h.engine, h.effect_catalog(), {}, b._fx_labels, b._auto)
    saved = doc["tracks"][0]["fx"]
    assert saved[0]["label"] == "EQ (V4.2)" and all(fx.get("auto") for fx in saved)
    r = json.loads(b.fxRestore(voz, json.dumps(saved)))
    assert r["ok"] and [e["label"] for e in r["chain"]] == [fx["label"] for fx in saved]
    assert all(e["auto"] for e in r["chain"])

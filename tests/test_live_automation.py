"""Mezcla en vivo con automatizaciones: rides de la voz, ecos/reverbs lanzados, ducking de la música y
barridos de filtro, escritos como curvas del motor que suenan al reproducir y se guardan en el proyecto."""
import json
import time

import numpy as np
import pytest
import soundfile as sf

from allforone import live_mix, mixer_service, project
from allforone.engine_host import EngineHost, afo_audio

SR = 48000
# (inicio, fin, nivel de pico en dBFS): intro de 8 s, frases fuerte/suave y un puente de 7 s
PHRASES = [(8.0, 11.0, -10.0), (12.0, 15.0, -20.0), (17.5, 20.5, -10.0), (27.5, 30.5, -15.0)]
LENGTH = 32.0


def voice(phrases=PHRASES, length=LENGTH):
    """Una «voz» sintética: armónicos con vibrato, a niveles distintos por frase y silencio entre ellas."""
    t = np.arange(int(length * SR)) / SR
    f0 = 220 * (1 + 0.01 * np.sin(2 * np.pi * 5 * t))
    ph = 2 * np.pi * np.cumsum(f0) / SR
    y = sum(np.sin(k * ph) / k for k in range(1, 6))
    y /= np.max(np.abs(y))
    amp = np.zeros_like(t)
    for a, b, lv in phrases:
        i, j = int(a * SR), int(b * SR)
        fade = np.minimum(1, np.minimum(np.arange(j - i), np.arange(j - i)[::-1]) / (0.02 * SR))
        amp[i:j] = 10 ** (lv / 20) * fade
    return y * amp


def write(path, y):
    sf.write(str(path), np.stack([y, y], 1), SR, subtype="FLOAT")
    return str(path)


def test_frases_rides_lanzamientos_ducking_y_barridos():
    mixer_service.load()                       # pone el V4.2 (vocal_dsp…) al alcance
    y = voice()
    lv, segs = live_mix.vocal_activity(np.stack([y, y]), SR)
    assert len(segs) == 4
    for (a, b), (pa, pb, _) in zip(segs, PHRASES):
        assert a == pytest.approx(pa, abs=0.3) and b == pytest.approx(pb, abs=0.3)
    # Ride: baja las frases fuertes y sube la suave, ±4 dB como máximo, sin moverse en los silencios
    ride = live_mix.ride_curve(lv, segs)
    at = lambda s: float(np.interp(s, [p[0] for p in ride], [p[1] for p in ride]))
    assert at(9.5) < -1.5 and at(13.5) > 1.5 and at(19) < -1.5
    assert max(abs(v) for _, v in ride) <= 4.0
    assert at(24) == pytest.approx(at(21.5), abs=0.6), "en el puente mantiene el último valor"
    assert len(ride) < 120, "curva aligerada"
    # Ecos al final de frase seguida de hueco (como mucho uno cada 6 s) y reverb antes de huecos largos
    delay = live_mix.throw_points(segs, 10.0, 38.0, 0.6, 1.0, 6.0, LENGTH)
    peaks = [t for t, v in delay if v == 38.0][::2]
    assert peaks == pytest.approx([segs[0][1], segs[2][1], segs[3][1]], abs=0.1)
    assert all(v in (10.0, 38.0) for _, v in delay) and delay[-1][1] == 10.0
    reverb = live_mix.throw_points(segs, 12.0, 34.0, 1.8, 1.2, 8.0, LENGTH)
    assert [t for t, v in reverb if v == 34.0][::2] == pytest.approx([segs[1][1]], abs=0.1)
    # Ducking: −1,5 dB mientras canta la voz, 0 dB en la intro y el puente
    duck = live_mix.duck_points(segs, 1.5, LENGTH)
    dat = lambda s: float(np.interp(s, [p[0] for p in duck], [p[1] for p in duck]))
    assert dat(4) == 0 and dat(9.5) == -1.5 and dat(11.6) == -1.5 and dat(24) == 0 and dat(29) == -1.5
    # Barrido: antes de la entrada tras la intro y tras el puente; se abre al entrar la voz
    sweep = live_mix.sweep_points(segs, 0.0)
    tops = [t for t, v in sweep if v >= 600]
    assert len(tops) == 2 and tops[0] == pytest.approx(segs[0][0], abs=0.1) and tops[1] == pytest.approx(segs[3][0], abs=0.1)
    hz = [v for _, v in sweep]
    assert min(hz) == 20.0 and max(hz) <= 650.0 and sweep[-1][1] == 20.0


needs_engine = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")


@pytest.fixture()
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    d = h.engine.device_info()
    if d["sample_rate"] != SR:
        err = h.engine.set_audio_device(d["type"], d["output"], d["input"], float(SR), d["buffer_size"])
        if err:
            pytest.skip(f"el dispositivo de audio no abre a {SR} Hz: {err}")
    yield h
    h.engine = None


def _db(x):
    return 20 * np.log10(max(1e-9, float(np.sqrt(np.mean(np.square(x))))))


@needs_engine
def test_el_ride_suena_en_el_render(host, tmp_path):
    """La curva del ride la sigue el motor: la diferencia entre la frase fuerte y la suave se reduce."""
    eng = host.engine
    mixer_service.load()
    y = voice()
    tid = eng.add_audio_track(write(tmp_path / "voz.wav", y), "voz")["id"]
    lv, segs = live_mix.vocal_activity(np.stack([y, y]), SR)
    chain = [live_mix._fx("gain", "Ride de voz (automático)", input=0, output=0)]
    chain[0]["auto"] = {"input": live_mix.ride_curve(lv, segs)}
    ids = live_mix.apply_chain(eng, tid, chain, [])
    assert eng.effect_info(ids[0])["automated"] == ["input"]
    out = tmp_path / "out.wav"
    assert eng.render_to_wav(str(out))
    z, sr = sf.read(str(out))
    z = z[:, 0]
    seg = lambda s, a, b: _db(s[int(a * SR):int(b * SR)])
    before = seg(y, 9, 10.5) - seg(y, 13, 14.5)
    after = seg(z, 9, 10.5) - seg(z, 13, 14.5)
    assert before == pytest.approx(10, abs=0.5)
    assert after < before - 4, (before, after)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtCore import QCoreApplication
    return QCoreApplication.instance() or QCoreApplication([])


@needs_engine
def test_mezcla_en_vivo_escribe_y_guarda_automatizaciones(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    from allforone.bridge import Bridge
    h = EngineHost.create()
    assert h.ok, h.error
    b = Bridge(h)
    events = []
    b.mixerEvent.connect(lambda s: events.append(json.loads(s)))
    try:
        m = mixer_service.load()
        t = np.arange(int(LENGTH * SR)) / SR
        piano = 0.2 * np.sin(2 * np.pi * 261.6 * t) + 0.1 * np.sin(2 * np.pi * 392 * t)
        stems = []
        for name, y, kind in (("voz.wav", voice(), "Voz principal"), ("piano.wav", piano, "Piano")):
            p = write(tmp_path / name, y)
            d = dict(mixer_service.describe(m, p), kind=kind)
            d["trackId"] = h.add_audio(p)["id"]
            stems.append(d)
        r = json.loads(b.mixer("mix", json.dumps({"stems": stems, "space": 45})))
        assert r["ok"], r
        t0 = time.monotonic()
        while not any(e["type"] in ("done", "error") for e in events) and time.monotonic() - t0 < 120:
            qapp.processEvents()
            h.pump()
        done = next(e for e in events if e["type"] in ("done", "error"))
        assert done["type"] == "done", done
        auto = done["automation"]
        assert auto["phrases"] == 4 and auto["ride_points"] > 2 and auto["delay_throws"] >= 2
        assert auto["reverb_throws"] >= 1 and auto["ducked"] == 1 and auto["sweeps"] == 2
        voz, pia = (s["trackId"] for s in stems)
        fx = {e["label"]: e for e in (dict(e, label=b._fx_labels.get(e["id"], "")) for e in h.engine.effects(voz))}
        keys = [e["key"] for e in h.engine.effects(voz)]
        assert keys[:3] == ["eq", "deesser", "gain"], keys
        assert fx["Ride de voz (automático)"]["automated"] == ["input"]
        assert any(e["key"] == "delay" and e["automated"] == ["mix"] for e in h.engine.effects(voz))
        piano_fx = [(b._fx_labels.get(e["id"]), e["automated"]) for e in h.engine.effects(pia)]
        assert piano_fx[0] == ("Barrido de filtro (automático)", ["hpf"])
        assert piano_fx[-1] == ("Ducking bajo la voz (automático)", ["input"])
        strip = next(e for e in events if e["type"] == "strip" and e.get("phase") == "done" and e["trackId"] == voz)
        assert "Ride de voz (automático)" in strip["automated"] and "ride de voz" in strip["note"]
        assert "nivelado de frases de la voz" not in done["skipped"]
        # Las curvas viven en la línea de tiempo y se guardan con el proyecto
        doc = project.collect({"tracks": [{"id": pia, "type": "audio"}]}, h.engine, h.effect_catalog(), {}, b._fx_labels, b._auto)
        saved = doc["tracks"][0]["fx"]
        assert saved[0]["automation"]["hpf"] and saved[-1]["automation"]["input"]
        r = json.loads(b.fxRestore(pia, json.dumps(saved)))
        assert r["ok"]
        again = h.engine.effects(pia)
        assert again[0]["automated"] == ["hpf"]
        flat = lambda pts: [x for p in pts for x in p]
        assert flat(h.engine.effect_automation(again[0]["id"], "hpf")) == pytest.approx(
            flat(saved[0]["automation"]["hpf"]), abs=1e-3)
    finally:
        b._timer.stop()
        b._mixer_timer.stop()
        h.engine = None

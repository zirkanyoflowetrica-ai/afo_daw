"""Hito 3 · Diseño sonoro (docs/BIBLIOTECA_NATIVA.md): AF-55 Trance Gate y AF-43 MultiTap.

Se mide el render real del motor: el Trance Gate abre y cierra justo en la rejilla de la canción (la
saca de la posición del transporte y del tempo) y el MultiTap pone cada eco a su distancia, con su
nivel y su lado. Al final, un house completo con el sinte cortado al tempo y la voz con ecos.
"""
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
SR = 48000


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


def db(x):
    return 20 * np.log10(max(1e-9, float(x)))


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


def _wav(tmp_path, y, name):
    p = tmp_path / name
    sf.write(str(p), np.stack([y, y], 1) if y.ndim == 1 else y, SR, subtype="FLOAT")
    return str(p)


def _tone(tmp_path, seconds=4.0, hz=220.0, amp_db=-12.0):
    t = np.arange(int(seconds * SR)) / SR
    return _wav(tmp_path, 10 ** (amp_db / 20) * np.sin(2 * np.pi * hz * t), "tono.wav")


def _render(eng, tmp_path, name="out.wav"):
    out = tmp_path / name
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    assert sr == SR
    return y


def _fx(eng, tid, key, **params):
    fx = eng.add_effect(tid, key)["id"]
    for k, v in params.items():
        assert eng.set_effect_param(fx, k, float(v)), k
    return fx


def _steps(y, bpm, per_beat=4, n=16, guard=0.15):
    """RMS (dB) de la primera y la última parte de cada paso: [(abierto, cerrado)…]."""
    step = 60.0 / bpm / per_beat
    out = []
    for s in range(n):
        a = int((s + guard) * step * SR)
        out.append((db(rms(y[a: a + int(0.3 * step * SR)])),
                    db(rms(y[int((s + 0.7) * step * SR): int((s + 1 - guard / 3) * step * SR)]))))
    return out


def test_catalogo_tiene_los_dos():
    cat = {c["key"]: c for c in afo_audio.effect_catalog()}
    assert cat["trancegate"]["af"] == "AF-55" and cat["multitap"]["af"] == "AF-43"
    assert cat["trancegate"]["family"] == "Ritmo y glitch" and cat["multitap"]["family"] == "Delays y ecos"


def test_trance_gate_corta_en_la_rejilla(host, tmp_path):
    """Todos los pasos, 1/16 a 120 BPM (125 ms), largo 50 %: abierto en la primera mitad de cada paso
    y 60 dB más bajo en la segunda; con profundidad 50 % baja solo 6 dB."""
    eng = host.engine
    eng.set_tempo(120.0)
    tid = eng.add_audio_track(_tone(tmp_path), "pad")["id"]
    fx = _fx(eng, tid, "trancegate", pattern=0, rate=1, length=50, attack=0.5, release=1)
    y = _render(eng, tmp_path)[:, 0]
    st = _steps(y, 120.0)
    print("abierto / cerrado (dB):", [(round(o, 1), round(c, 1)) for o, c in st[:4]])
    assert all(abs(o - (-15.05)) < 0.3 for o, c in st), "abierto deja el tono intacto (−12 dBFS de pico)"
    assert all(c < -70 for o, c in st)
    eng.set_effect_param(fx, "depth", 50)
    st = _steps(_render(eng, tmp_path, "d50.wav")[:, 0], 120.0)
    assert all(abs(c - o - db(0.5)) < 0.3 for o, c in st)


def test_trance_gate_patron_y_tempo(host, tmp_path):
    """«Contratiempo» a 1/16 deja sonar solo los pasos 3, 7, 11 y 15; a 90 BPM la rejilla se estira."""
    eng = host.engine
    eng.set_tempo(90.0)
    tid = eng.add_audio_track(_tone(tmp_path, seconds=4.0), "pad")["id"]
    _fx(eng, tid, "trancegate", pattern=5, rate=1, length=90, attack=0.5, release=1)
    st = _steps(_render(eng, tmp_path)[:, 0], 90.0)
    sounding = [s for s, (o, c) in enumerate(st) if o > -30]
    print("pasos que suenan a 90 BPM:", sounding)
    assert sounding == [2, 6, 10, 14]


def test_trance_gate_alterno_lr(host, tmp_path):
    eng = host.engine
    eng.set_tempo(120.0)
    tid = eng.add_audio_track(_tone(tmp_path), "pad")["id"]
    _fx(eng, tid, "trancegate", pattern=0, rate=1, length=90, stereo=1, attack=0.5, release=1)
    y = _render(eng, tmp_path)
    left = [s for s, (o, c) in enumerate(_steps(y[:, 0], 120.0, n=8)) if o > -30]
    right = [s for s, (o, c) in enumerate(_steps(y[:, 1], 120.0, n=8)) if o > -30]
    assert left == [0, 2, 4, 6] and right == [1, 3, 5, 7]


def test_multitap_distancias_niveles_y_lados(host, tmp_path):
    """Un golpe a 0,5 s; 4 ecos a corcheas de 120 BPM (250 ms), caída 50 %, apertura total: el 1.º y el
    3.º a la izquierda, el 2.º y el 4.º a la derecha, cada uno 6 dB por debajo del anterior."""
    eng = host.engine
    eng.set_tempo(120.0)
    y0 = np.zeros(int(3 * SR)); y0[int(0.5 * SR)] = 0.8
    tid = eng.add_audio_track(_wav(tmp_path, y0, "click.wav"), "golpe")["id"]
    fx = _fx(eng, tid, "multitap", sync=3, taps=3, shape=0, decay=50, spread=100, feedback=0, hp=20, lp=20000, mix=100)
    y = _render(eng, tmp_path)
    found = []
    for k in range(4):
        t = 0.5 + 0.25 * (k + 1)
        w = slice(int((t - 0.01) * SR), int((t + 0.01) * SR))
        l, r = np.abs(y[w, 0]).max(), np.abs(y[w, 1]).max()
        pos = (np.argmax(np.abs(y[w, 0] if l > r else y[w, 1])) + w.start) / SR
        found.append((round(pos, 4), "L" if l > r else "R", db(max(l, r)), db(min(l, r) + 1e-9)))
    print("ecos:", [(p, s, round(a, 1)) for p, s, a, _ in found])
    assert [p for p, *_ in found] == pytest.approx([0.75, 1.0, 1.25, 1.5], abs=0.0005)
    assert [s for _, s, *_ in found] == ["L", "R", "L", "R"]
    lv = [a for _, _, a, _ in found]
    assert np.diff(lv) == pytest.approx([db(0.5)] * 3, abs=0.3)
    assert all(other < a - 60 for _, _, a, other in found), "apertura total: nada al otro lado"
    assert abs(np.abs(y[int(1.6 * SR):, :]).max()) < 1e-4, "sin realimentación no hay quinto eco"
    assert eng.effect_meters(fx)[2] == pytest.approx(250.0, abs=0.5)


def test_multitap_crecida(host, tmp_path):
    eng = host.engine
    eng.set_tempo(120.0)
    y0 = np.zeros(int(3 * SR)); y0[int(0.5 * SR)] = 0.8
    tid = eng.add_audio_track(_wav(tmp_path, y0, "click.wav"), "golpe")["id"]
    _fx(eng, tid, "multitap", sync=4, taps=3, shape=1, decay=50, spread=0, hp=20, lp=20000, mix=100)
    y = _render(eng, tmp_path)[:, 0]
    lv = [db(np.abs(y[int((0.5 + 0.125 * (k + 1) - 0.005) * SR): int((0.5 + 0.125 * (k + 1) + 0.005) * SR)]).max())
          for k in range(4)]
    assert np.diff(lv) == pytest.approx([-db(0.5)] * 3, abs=0.3), "crecida: cada eco 6 dB más fuerte"


def test_house_completo_con_trance_gate_y_multitap(host, tmp_path):
    """House de 124 BPM: el sinte pasa por el Trance Gate («Trance», 1/16) y la voz por el MultiTap
    (corcheas). El sinte solo suena en los pasos del patrón, en la rejilla de la canción, y la mezcla
    entera sale limpia."""
    from song_factory import write_song
    song = write_song("house", tmp_path / "house")
    g = song["genre"]
    eng = host.engine
    eng.set_tempo(g.bpm)
    ids = {Path(p).stem.split("_", 1)[1]: eng.add_audio_track(p, Path(p).stem)["id"] for p in song["paths"]}
    synth = next(k for k in ids if "ynth" in k or "Sinte" in k)
    _fx(eng, ids[synth], "trancegate", pattern=3, rate=1, length=60, attack=1, release=3)
    _fx(eng, ids["Voz_Lead"], "multitap", sync=3, taps=3, mix=30)
    y = _render(eng, tmp_path, "mix.wav")
    assert 0.05 < np.abs(y).max() <= 1.0 and np.isfinite(y).all()

    for k, t in ids.items():
        eng.set_track_mute(t, k != synth)
    s = _render(eng, tmp_path, "synth.wav")[:, 0]
    step = 60.0 / g.bpm / 4
    pattern = "1011011010110110"
    bars = int(len(s) / SR / (16 * step)) - 1
    on, off = [], []
    for st in range(bars * 16):
        a = int((st + 0.1) * step * SR)
        lvl = rms(s[a: a + int(0.4 * step * SR)])
        (on if pattern[st % 16] == "1" else off).append(lvl)
    on_db = db(np.median([x for x in on if x > 0] or [1e-9]))
    loud_off = sum(db(x) > on_db - 40 for x in off)
    print(f"{bars} compases: sinte en los pasos del patrón {on_db:.1f} dB; fuera del patrón, "
          f"{loud_off} de {len(off)} pasos a menos de 40 dB")
    assert on_db > -40 and loud_off == 0

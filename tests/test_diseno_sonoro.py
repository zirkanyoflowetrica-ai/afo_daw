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


# ---------------------------------------------------------------- reverbs del Hito 3 (AF-37, AF-38, AF-40)
def _burst(tmp_path, hz=440.0, on=1.0, seconds=6.0, amp_db=-12.0, name="burst.wav"):
    t = np.arange(int(seconds * SR)) / SR
    y = 10 ** (amp_db / 20) * np.sin(2 * np.pi * hz * t) * (t < on)
    return _wav(tmp_path, y, name)


def _band_db(x, f0, half=15.0):
    """Energía (dB) de x alrededor de f0 ± half Hz (FFT con ventana de Hann)."""
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return 10 * np.log10(X[(f > f0 - half) & (f < f0 + half)].sum() + 1e-20)


def test_catalogo_reverbs_del_hito_3():
    cat = {c["key"]: c for c in afo_audio.effect_catalog()}
    assert {cat[k]["af"] for k in ("shimmer", "textureverb", "infinity")} == {"AF-37", "AF-38", "AF-40"}
    assert {cat[k]["family"] for k in ("shimmer", "textureverb", "infinity")} == {"Reverberación y espacios"}


def test_shimmer_sube_la_cola_una_octava(host, tmp_path):
    """Un La 440 de 1 s: con Brillo 0 la cola es una reverb normal (casi nada en 880 Hz); con Brillo 60
    la cola trae la octava (880) y la doble octava (1760) muy por encima."""
    eng = host.engine
    tid = eng.add_audio_track(_burst(tmp_path), "la")["id"]
    fx = _fx(eng, tid, "shimmer", shift=0, amount=0, decay=4, predelay=0, lowcut=20, damping=20000, mix=100)
    tail = lambda y: y[int(1.5 * SR): int(4.5 * SR), 0]                   # noqa: E731
    y0 = tail(_render(eng, tmp_path, "a0.wav"))
    eng.set_effect_param(fx, "amount", 60)
    y1 = _render(eng, tmp_path, "a60.wav")
    assert np.isfinite(y1).all() and np.abs(y1).max() < 1.0
    y1 = tail(y1)
    oct0, oct1 = _band_db(y0, 880) - _band_db(y0, 440), _band_db(y1, 880) - _band_db(y1, 440)
    two1 = _band_db(y1, 1760) - _band_db(y1, 440)
    print(f"cola: octava frente al La {oct0:.1f} dB sin brillo, {oct1:.1f} dB con brillo 60; doble octava {two1:.1f} dB")
    assert oct0 < -40 and oct1 > oct0 + 30 and two1 > -30
    eng.set_effect_param(fx, "shift", 1)                                   # quinta: 660 Hz
    y2 = tail(_render(eng, tmp_path, "q.wav"))
    assert _band_db(y2, 660) - _band_db(y2, 880) > 10


def test_texture_verb_seda_grano_y_cinta(host, tmp_path):
    """Un tono de 1 kHz sostenido: Seda con Movimiento abre bandas laterales (la cola ya no es un solo
    tono); Grano trocea la cola (su nivel salta de un tramo de 10 ms a otro); Cinta oscurece y desafina
    un poco. Sin movimiento la cola de Seda es el tono puro y cae con su RT60."""
    eng = host.engine
    tid = eng.add_audio_track(_burst(tmp_path, hz=1000.0, on=3.0, seconds=7.0), "tono")["id"]
    fx = _fx(eng, tid, "textureverb", texture=0, depth=0, decay=2, lowcut=20, damping=20000, mix=100)

    def side_ratio(y):                     # energía de 500–1500 Hz fuera de 1 kHz ± 6 Hz frente a la del tono (dB)
        seg = y[int(1.5 * SR): int(2.9 * SR), 0]
        wide, core = 10 ** (_band_db(seg, 1000, 500) / 10), 10 ** (_band_db(seg, 1000, 6) / 10)
        return 10 * np.log10(max(wide - core, 1e-20) / core)

    def wobble(y):                         # variación del nivel en tramos de 10 ms (desviación / media)
        seg = y[int(1.5 * SR): int(2.9 * SR), 0]
        fr = np.sqrt(np.mean(seg[: len(seg) // 480 * 480].reshape(-1, 480) ** 2, axis=1))
        return float(np.std(fr) / np.mean(fr))

    still = _render(eng, tmp_path, "still.wav")
    tail = still[int(3.2 * SR):, 0]
    edc = 10 * np.log10(np.cumsum(tail[::-1] ** 2)[::-1] / np.sum(tail ** 2) + 1e-20)
    rt60 = 3 * (np.argmax(edc < -25) - np.argmax(edc < -5)) / SR
    eng.set_effect_param(fx, "depth", 100)
    silk = _render(eng, tmp_path, "silk.wav")
    eng.set_effect_param(fx, "texture", 1)                                # Grano sin movimiento: solo los granos
    eng.set_effect_param(fx, "depth", 0)
    eng.set_effect_param(fx, "density", 8)
    grain = _render(eng, tmp_path, "grain.wav")
    eng.set_effect_param(fx, "texture", 2)
    eng.set_effect_param(fx, "depth", 60)
    tape = _render(eng, tmp_path, "tape.wav")
    print(f"RT60 {rt60:.2f} s; bandas laterales: quieta {side_ratio(still):.1f} dB, seda {side_ratio(silk):.1f} dB; "
          f"cinta {side_ratio(tape):.1f} dB; vaivén del nivel: quieta {wobble(still):.2f}, grano {wobble(grain):.2f}")
    assert rt60 == pytest.approx(2.0, rel=0.3)
    assert side_ratio(still) < -30 and side_ratio(silk) > side_ratio(still) + 15
    assert wobble(grain) > 5 * wobble(still) and wobble(grain) > 0.3
    assert all(np.isfinite(y).all() and np.abs(y).max() < 1.0 for y in (silk, grain, tape))
    assert side_ratio(tape) > side_ratio(still) + 10


def test_infinity_congela_la_cola(host, tmp_path):
    """Un La de 1,5 s. Sin congelar, con caída de 20 s, la cola baja ≈ 9 dB en 3 s. Congelando en el
    segundo 1 (automatización), la cola queda fija: no cae y no deja entrar nada más."""
    eng = host.engine
    tid = eng.add_audio_track(_burst(tmp_path, on=1.5, seconds=7.0), "la")["id"]
    fx = _fx(eng, tid, "infinity", freeze=0, decay=20, lowcut=20, mix=100)
    lvl = lambda y, a, b: db(rms(y[int(a * SR): int(b * SR), 0]))         # noqa: E731
    y = _render(eng, tmp_path, "free.wav")
    drop = lvl(y, 2.5, 3.0) - lvl(y, 5.5, 6.0)
    assert eng.set_effect_automation(fx, "freeze", [(0.0, 0.0), (1.0, 0.0), (1.0001, 1.0), (7.0, 1.0)])
    z = _render(eng, tmp_path, "frozen.wav")
    held = lvl(z, 2.5, 3.0) - lvl(z, 5.5, 6.0)
    print(f"sin congelar cae {drop:.1f} dB en 3 s; congelada {held:.2f} dB (nivel {lvl(z, 5.5, 6.0):.1f} dB)")
    assert drop == pytest.approx(9.0, abs=2.0)
    assert abs(held) < 0.5 and lvl(z, 5.5, 6.0) > -40
    assert np.isfinite(z).all() and np.abs(z).max() < 1.0


def test_cinematico_completo_con_las_reverbs(host, tmp_path):
    """Una pieza cinematográfica entera: coros con Shimmer, piano con Texture Verb (Seda) y pad con
    Infinity. La mezcla sale limpia y el Shimmer añade agudos a los coros (su octava)."""
    from song_factory import write_song
    song = write_song("cinematico", tmp_path / "cine")
    g = song["genre"]
    eng = host.engine
    eng.set_tempo(g.bpm)
    ids = {Path(p).stem.split("_", 1)[1]: eng.add_audio_track(p, Path(p).stem)["id"] for p in song["paths"]}
    sh = _fx(eng, ids["Coros"], "shimmer", amount=50, mix=40)
    _fx(eng, ids["Piano"], "textureverb", texture=0, depth=50, mix=30)
    _fx(eng, ids["Pad_Cuerdas"], "infinity", decay=15, mix=35)
    y = _render(eng, tmp_path, "mix.wav")
    assert np.isfinite(y).all() and 0.05 < np.abs(y).max() <= 1.0

    for k, t in ids.items():
        eng.set_track_mute(t, k != "Coros")
    def hi(x):                             # energía de 2–8 kHz frente a la de 100 Hz – 2 kHz (dB)
        X = np.abs(np.fft.rfft(x[:, 0])) ** 2
        f = np.fft.rfftfreq(len(x), 1 / SR)
        return 10 * np.log10(X[(f > 2000) & (f < 8000)].sum() / X[(f > 100) & (f < 2000)].sum())
    eng.set_effect_param(sh, "mix", 100)                                   # solo la reverb: con y sin octava
    with_sh = _render(eng, tmp_path, "coros.wav")
    eng.set_effect_param(sh, "amount", 0)
    without = _render(eng, tmp_path, "coros0.wav")
    gain = hi(with_sh) - hi(without)
    print(f"coros: agudos +{gain:.1f} dB con Shimmer")
    assert gain > 6

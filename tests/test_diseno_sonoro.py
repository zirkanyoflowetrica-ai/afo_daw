"""Hito 3 · Diseño sonoro (docs/BIBLIOTECA_NATIVA.md): Trance Gate, MultiTap, reverbs, Granular y Spectral.

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


# ---------------------------------------------------------------- granular y espectral (AF-57, AF-58)
def _peak_hz(x, lo=50.0, hi=5000.0):
    X = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    f = np.fft.rfftfreq(len(x), 1 / SR)
    m = (f > lo) & (f < hi)
    return float(f[m][np.argmax(X[m])])


def test_catalogo_granular_y_espectral():
    cat = {c["key"]: c for c in afo_audio.effect_catalog()}
    assert cat["granular"]["af"] == "AF-57" and cat["spectral"]["af"] == "AF-58"
    assert {cat[k]["family"] for k in ("granular", "spectral")} == {"Granular y espectral"}


def test_granular_transporta_una_octava(host, tmp_path):
    """Un La 440 con granos a +12 st: la energía pasa a 880 Hz (más de 20 dB sobre los 440)."""
    eng = host.engine
    tid = eng.add_audio_track(_tone(tmp_path, seconds=4.0, hz=440.0), "la")["id"]
    _fx(eng, tid, "granular", size=80, density=30, pitch=12, pitchRand=0, distance=100, spray=0,
        reverse=0, spread=0, mix=100)
    y = _render(eng, tmp_path)[int(1.0 * SR): int(3.5 * SR), 0]
    up, base = _band_db(y, 880.0), _band_db(y, 440.0)
    print(f"granos +12 st: 880 Hz {up:.1f} dB, 440 Hz {base:.1f} dB")
    assert up - base > 20 and np.isfinite(y).all()


def _saw(tmp_path, hz=100.0, seconds=4.0):
    t = np.arange(int(seconds * SR)) / SR
    return _wav(tmp_path, 0.25 * (2 * ((t * hz) % 1.0) - 1), "sierra.wav")


def test_granular_reversa_da_la_vuelta(host, tmp_path):
    """Una sierra que sube (y cae de golpe): granos hacia delante la dejan subiendo; con Reversa
    100 % casi todas las muestras bajan."""
    eng = host.engine
    tid = eng.add_audio_track(_saw(tmp_path), "sierra")["id"]
    fx = _fx(eng, tid, "granular", size=200, density=10, pitch=0, distance=300, spray=0, reverse=0, spread=0, mix=100)

    def falling(y):
        d = np.diff(y[int(1.0 * SR): int(3.5 * SR), 0])
        d = d[np.abs(d) > 1e-6]
        return float(np.mean(d < 0))
    fwd = falling(_render(eng, tmp_path, "fwd.wav"))
    eng.set_effect_param(fx, "reverse", 100)
    rev = falling(_render(eng, tmp_path, "rev.wav"))
    print(f"muestras que bajan: hacia delante {fwd:.2f}, en reversa {rev:.2f}")
    assert fwd < 0.25 and rev > 0.75


def test_granular_congelar_sigue_sonando(host, tmp_path):
    """Un La de 1 s. Sin congelar, a los 2,5–4,5 s ya no queda nada; congelando a los 0,9 s
    (automatización), los granos siguen sonando con lo último que entró, en 440 Hz."""
    eng = host.engine
    tid = eng.add_audio_track(_burst(tmp_path, on=1.0, seconds=5.0), "la")["id"]
    fx = _fx(eng, tid, "granular", size=100, density=30, distance=100, spray=200, spread=50, mix=100)
    tail = lambda y: y[int(2.5 * SR): int(4.5 * SR), 0]                 # noqa: E731
    free = db(rms(tail(_render(eng, tmp_path, "free.wav"))))
    assert eng.set_effect_automation(fx, "freeze", [(0.0, 0.0), (0.9, 0.0), (0.9001, 1.0), (5.0, 1.0)])
    z = tail(_render(eng, tmp_path, "frozen.wav"))
    print(f"cola sin congelar {free:.1f} dB; congelada {db(rms(z)):.1f} dB, pico en {_peak_hz(z):.0f} Hz")
    assert free < -80 and db(rms(z)) > -40 and abs(_peak_hz(z) - 440) < 5


def _noisy_tone(tmp_path, seconds=4.0, hz=440.0, noise_db=-50.0):
    rng = np.random.default_rng(58)
    t = np.arange(int(seconds * SR)) / SR
    y = 0.25 * np.sin(2 * np.pi * hz * t) + 10 ** (noise_db / 20) * rng.standard_normal(len(t))
    return _wav(tmp_path, y, "tono_ruido.wav")


def test_spectral_neutro_y_alineado(host, tmp_path):
    """Desenfoque 0 % sin desplazar = el mismo sonido, en su sitio: el motor compensa los 2048
    puntos de latencia (resta con el original < −60 dB)."""
    eng = host.engine
    tid = eng.add_audio_track(_noisy_tone(tmp_path, noise_db=-30.0), "x")["id"]
    a = _render(eng, tmp_path, "seco.wav")
    _fx(eng, tid, "spectral", mode=0, amount=0, shift=0, mix=100)
    b = _render(eng, tmp_path, "fx.wav")
    n = min(len(a), len(b))
    seg = slice(int(0.5 * SR), n - int(0.5 * SR))
    res = db(rms(b[seg] - a[seg])) - db(rms(a[seg]))
    print(f"Spectral neutro: diferencia {res:.1f} dB")
    assert res < -60


def test_spectral_puerta_quita_el_ruido(host, tmp_path):
    """La 440 a −12 dB con ruido a −50 dB. Puerta a −40 dB: el ruido de 2–10 kHz baja más de 20 dB y
    el La se queda (±1 dB)."""
    eng = host.engine
    tid = eng.add_audio_track(_noisy_tone(tmp_path), "x")["id"]
    a = _render(eng, tmp_path, "seco.wav")[int(1 * SR): int(3.5 * SR), 0]
    _fx(eng, tid, "spectral", mode=3, threshold=-40, mix=100)
    b = _render(eng, tmp_path, "gate.wav")[int(1 * SR): int(3.5 * SR), 0]

    def hiss(x):
        X = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
        f = np.fft.rfftfreq(len(x), 1 / SR)
        return 10 * np.log10(X[(f > 2000) & (f < 10000)].sum() + 1e-20)
    cut, tone = hiss(a) - hiss(b), _band_db(b, 440.0) - _band_db(a, 440.0)
    print(f"Puerta: ruido −{cut:.1f} dB, La {tone:+.2f} dB")
    assert cut > 20 and abs(tone) < 1


def test_spectral_desplaza_y_robot(host, tmp_path):
    """Desplazar +500 Hz lleva el La 440 a ≈ 932 Hz (21 franjas de 23,4 Hz); Robot fija la fase y
    deja solo armónicos de 48000/512 = 93,75 Hz."""
    eng = host.engine
    tid = eng.add_audio_track(_tone(tmp_path, seconds=4.0, hz=440.0), "la")["id"]
    fx = _fx(eng, tid, "spectral", mode=0, amount=0, shift=500, mix=100)
    y = _render(eng, tmp_path, "shift.wav")[int(1 * SR): int(3.5 * SR), 0]
    pk = _peak_hz(y)
    left = _band_db(y, 440.0) - _band_db(y, pk)
    eng.set_effect_param(fx, "shift", 0)
    eng.set_effect_param(fx, "mode", 1)
    eng.set_effect_param(fx, "amount", 100)
    r = _render(eng, tmp_path, "robot.wav")[int(1 * SR): int(3.5 * SR), 0]
    rk = _peak_hz(r)
    print(f"desplazado: pico {pk:.1f} Hz (440 Hz a {left:.1f} dB); robot: pico {rk:.2f} Hz")
    assert 920 < pk < 945 and left < -30
    assert abs(rk / 93.75 - round(rk / 93.75)) * 93.75 < 1.0 and abs(rk - 440) > 5


def test_spectral_congelar(host, tmp_path):
    """Un La de 1 s; el modo pasa a Congelar a los 0,8 s (automatización): el La sigue sonando,
    estable, cuando la entrada ya calló."""
    eng = host.engine
    tid = eng.add_audio_track(_burst(tmp_path, on=1.0, seconds=5.0), "la")["id"]
    fx = _fx(eng, tid, "spectral", mode=0, amount=0, mix=100)
    assert eng.set_effect_automation(fx, "mode", [(0.0, 0.0), (0.8, 0.0), (0.8001, 4.0), (5.0, 4.0)])
    y = _render(eng, tmp_path, "freeze.wav")[:, 0]
    a, b = y[int(2.0 * SR): int(2.8 * SR)], y[int(3.8 * SR): int(4.6 * SR)]
    print(f"congelado: {db(rms(a)):.1f} dB y {db(rms(b)):.1f} dB, pico en {_peak_hz(b):.0f} Hz")
    assert db(rms(a)) > -30 and abs(db(rms(a)) - db(rms(b))) < 3 and abs(_peak_hz(b) - 440) < 15


def test_lofi_completo_con_granular_y_spectral(host, tmp_path):
    """Un lo-fi entero: voz con granos una octava arriba, pad desenfocado y batería por el Spectral.
    La mezcla sale limpia; la batería por el Spectral neutro sigue en su sitio (latencia compensada)
    y desenfocada pierde pegada; la voz granulada sube su brillo."""
    from song_factory import write_song
    song = write_song("lofi", tmp_path / "lofi")
    g = song["genre"]
    eng = host.engine
    eng.set_tempo(g.bpm)
    ids = {Path(p).stem.split("_", 1)[1]: eng.add_audio_track(p, Path(p).stem)["id"] for p in song["paths"]}
    for k, t in ids.items():
        eng.set_track_mute(t, k != "Drums")
    dry = _render(eng, tmp_path, "drums0.wav")[:, 0]
    sp = _fx(eng, ids["Drums"], "spectral", mode=0, amount=0, mix=100)
    neutral = _render(eng, tmp_path, "drums1.wav")[:, 0]
    # Desde 0,5 s: el primer bloque de un render con latencia no se compensa bien con bloques que no
    # dividen la latencia (pasa igual con Limiter, Saturator y Tune; pendiente en docs/TAREAS.md)
    n = min(len(dry), len(neutral))
    seg = slice(int(0.5 * SR), n)
    res = db(rms(neutral[seg] - dry[seg])) - db(rms(dry[seg]))
    eng.set_effect_param(sp, "amount", 95)
    blur = _render(eng, tmp_path, "drums2.wav")[:, 0]
    crest = lambda x: db(np.abs(x).max()) - db(rms(x))                  # noqa: E731
    punch = crest(dry) - crest(blur)

    for k, t in ids.items():
        eng.set_track_mute(t, k != "Voz_Lead")

    def centroid(x):
        X = np.abs(np.fft.rfft(x)) ** 2
        f = np.fft.rfftfreq(len(x), 1 / SR)
        return float((X * f).sum() / X.sum())
    v0 = centroid(_render(eng, tmp_path, "voz0.wav")[:, 0])
    _fx(eng, ids["Voz_Lead"], "granular", size=120, density=25, pitch=12, distance=100, spray=50, mix=100)
    v1 = centroid(_render(eng, tmp_path, "voz1.wav")[:, 0])

    for t in ids.values():
        eng.set_track_mute(t, False)
    eng.set_effect_param(sp, "amount", 50)
    _fx(eng, ids["Pad_Cuerdas"], "spectral", mode=0, amount=80, mix=60)
    y = _render(eng, tmp_path, "mix.wav")
    print(f"batería: neutro {res:.1f} dB, pegada −{punch:.1f} dB con desenfoque; voz: centroide "
          f"{v0:.0f} → {v1:.0f} Hz; mezcla pico {np.abs(y).max():.2f}")
    assert res < -50 and punch > 3 and v1 > 1.4 * v0
    assert np.isfinite(y).all() and 0.05 < np.abs(y).max() <= 1.0

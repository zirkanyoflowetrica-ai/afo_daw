"""Voz profesional (Hito 4) en el motor C++: Harmonizer (AF-65), Doubler (AF-66), Dynamic EQ (AF-08)
y Noise Reducer (AF-68).

Se mide el render real. Harmonizer: cada intervalo cae en la nota que toca de la escala (o a semitonos
fijos), sigue una melodía grado a grado, sale afinado aunque la voz no lo esté y con las voces
apagadas deja la voz igual que sin efecto (su latencia la compensa Tracktion). Doubler: con la mezcla
a 0 no cambia nada, la copia sale a la separación pedida y desafinada los cents pedidos, y abre el
estéreo. Dynamic EQ: solo corta lo que pasa del umbral en su banda. Noise Reducer: baja el ruido de
fondo y deja el tono. Con proyectos enteros: una balada con la voz armonizada y los coros doblados, y
la misma voz con soplido limpiada y ecualizada.
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
    return 20 * np.log10(max(1e-12, float(x)))


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


def cents(a, b):
    return 1200 * np.log2(a / b)


def peak_hz(y, lo=60, hi=2000):
    """Frecuencia del pico más alto (interpolación parabólica sobre el espectro con ventana de Hann)."""
    n = 1 << 18
    s = np.abs(np.fft.rfft(y * np.hanning(len(y)), n))
    f = np.fft.rfftfreq(n, 1 / SR)
    i = int(np.argmax(s * ((f > lo) & (f < hi))))
    a, b, c = np.log(s[i - 1:i + 2] + 1e-12)
    return (i + 0.5 * (a - c) / (a - 2 * b + c)) * SR / n


def note_hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def _render(eng, tmp_path, name):
    out = tmp_path / name
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    assert sr == SR
    return y


def _track(host, tmp_path, y, name):
    p = tmp_path / f"{name}.wav"
    sf.write(str(p), np.stack([y, y], 1) if y.ndim == 1 else y, SR, subtype="FLOAT")
    return host.add_audio(str(p), name)["id"]


def _fx(eng, tid, fx_key, **params):
    e = eng.add_effect(tid, fx_key)["id"]
    for k, v in params.items():
        assert eng.set_effect_param(e, k, float(v)), k
    return e


def _sine(hz, secs=2.0, amp=0.3):
    return amp * np.sin(2 * np.pi * hz * np.arange(int(secs * SR)) / SR)


# Intervalos de la lista: 1 = 3ª arriba, 6 = 5ª abajo, 10 = octava abajo
@pytest.mark.parametrize("sung,key,scale,mode,iv,want", [
    (440.0, 0, 1, 0, 1, note_hz(72)),       # La en Do mayor, 3ª arriba en la escala → Do (3ª menor)
    (440.0, 0, 1, 1, 1, note_hz(73)),       # la misma 3ª fija → Do# (4 semitonos)
    (440.0, 0, 1, 0, 6, note_hz(62)),       # 5ª abajo en la escala → Re
    (445.0, 0, 1, 0, 1, note_hz(72)),       # cantada 20 cents alta: la armonía sale afinada igual
    (392.0, 0, 1, 0, 1, note_hz(71)),       # Sol en Do mayor, 3ª arriba → Si (3ª mayor)
    (493.88, 9, 2, 0, 1, note_hz(74)),      # Si en La menor, 3ª arriba → Re
    (440.0, 0, 1, 0, 10, note_hz(57)),      # octava abajo
])
def test_harmonizer_intervalos(host, tmp_path, sung, key, scale, mode, iv, want):
    eng = host.engine
    tid = _track(host, tmp_path, _sine(sung), "voz")
    _fx(eng, tid, "harmonizer", key=key, scale=scale, mode=mode, voice1=iv, pan1=0, dry=0)
    y = _render(eng, tmp_path, "h.wav")
    got = peak_hz(y[int(0.6 * SR):int(1.8 * SR), 0])
    print(f"{sung} Hz, intervalo {iv}: {got:.2f} Hz (esperado {want:.2f})")
    assert abs(cents(got, want)) < 5


def test_harmonizer_sigue_la_melodia(host, tmp_path):
    """Do Re Mi Fa Sol en Do mayor, cada nota 0,5 s: la 3ª arriba en la escala es Mi Fa Sol La Si."""
    eng = host.engine
    notes, d = [60, 62, 64, 65, 67], int(0.5 * SR)
    t = np.arange(d) / SR
    fade = np.minimum(1, np.minimum(t, t[::-1]) / 0.01)
    y = np.concatenate([0.3 * fade * np.sin(2 * np.pi * note_hz(m) * t) for m in notes])
    tid = _track(host, tmp_path, y, "melodia")
    _fx(eng, tid, "harmonizer", voice1=1, pan1=0, dry=0, glide=10)
    z = _render(eng, tmp_path, "m.wav")[:, 0]
    want = [64, 65, 67, 69, 71]
    for k, m in enumerate(want):
        got = peak_hz(z[k * d + int(0.2 * SR):(k + 1) * d - int(0.03 * SR)], 150, 1200)
        assert abs(cents(got, note_hz(m))) < 10, (k, got, note_hz(m))


def test_harmonizer_apagado_deja_la_voz_igual(host, tmp_path):
    """Sin voces de armonía y con la voz original al 100 %, el render es el mismo que sin el efecto:
    la media ventana de retardo la informa y Tracktion la compensa."""
    eng = host.engine
    tid = _track(host, tmp_path, _sine(330.0), "voz")
    ref = _render(eng, tmp_path, "ref.wav")
    e = _fx(eng, tid, "harmonizer", voice1=0, voice2=0, dry=100)
    out = _render(eng, tmp_path, "h.wav")
    seg = slice(SR // 4, SR + SR // 2)
    assert db(rms(out[seg] - ref[seg])) - db(rms(ref[seg])) < -100
    assert eng.effect_info(e)["latency_seconds"] == pytest.approx(0.025, abs=1e-4)


def test_doubler_mezcla_cero_no_cambia_nada(host, tmp_path):
    eng = host.engine
    tid = _track(host, tmp_path, _sine(330.0), "voz")
    ref = _render(eng, tmp_path, "ref.wav")
    _fx(eng, tid, "doubler", voices=4, mix=0)
    out = _render(eng, tmp_path, "d.wav")
    assert db(rms(out - ref)) < -120


def test_doubler_separacion_y_desafinacion(host, tmp_path):
    """Una copia a la izquierda del todo: el canal izquierdo menos el derecho es solo la copia.
    Con un impulso sale a la separación pedida; con un tono, desafinada los cents pedidos."""
    eng = host.engine
    x = np.zeros(SR)
    x[SR // 4] = 0.5
    tid = _track(host, tmp_path, x, "imp")
    ref = _render(eng, tmp_path, "ref.wav")[:, 0]
    _fx(eng, tid, "doubler", voices=1, separation=30, variation=0, detune=0, spread=100, mix=100)
    y = _render(eng, tmp_path, "imp_d.wav")
    side = y[:, 0] - y[:, 1]
    at = int(np.argmax(np.abs(side))) - int(np.argmax(np.abs(ref)))
    assert abs(at - int(0.030 * SR)) <= 2, at
    host.remove(tid)

    tid = _track(host, tmp_path, _sine(440.0, 3.0), "tono")
    _fx(eng, tid, "doubler", voices=1, variation=0, detune=20, spread=100, mix=100)
    y = _render(eng, tmp_path, "tono_d.wav")
    got = peak_hz((y[:, 0] - y[:, 1])[SR // 2:int(2.8 * SR)])
    assert abs(cents(got, 440.0) - 20) < 2, cents(got, 440.0)


def test_doubler_abre_el_estereo(host, tmp_path):
    """Dos copias con variación y desafinación, abiertas del todo: izquierda y derecha dejan de ser la
    misma señal (correlación < 0,95) sin perder la voz (sigue > 0,3) ni subir de más el nivel."""
    eng = host.engine
    rng = np.random.default_rng(3)
    y = np.convolve(rng.standard_normal(2 * SR), np.ones(8) / 8, "same") * 0.2      # ruido rosado-ish
    tid = _track(host, tmp_path, y, "ruido")
    ref = _render(eng, tmp_path, "ref.wav")
    _fx(eng, tid, "doubler", voices=2, spread=100, mix=60)
    out = _render(eng, tmp_path, "d.wav")
    seg = slice(SR // 4, 2 * SR - SR // 4)
    c = np.corrcoef(out[seg, 0], out[seg, 1])[0, 1]
    print(f"doubler: correlación L/R {c:.2f}, nivel {db(rms(ref[seg])):.1f} → {db(rms(out[seg])):.1f} dB")
    assert 0.3 < c < 0.95
    assert 0 < db(rms(out[seg])) - db(rms(ref[seg])) < 4


def test_balada_con_armonia_y_coros_doblados(host, tmp_path):
    """Una balada entera (Do mayor, voz desafinada de 15 a 45 cents por nota): la 3ª del Harmonizer
    sale en la escala y más afinada que la voz, una 3ª por encima; con los coros por el Doubler la
    mezcla entera sale limpia."""
    import librosa
    from song_factory import pitch_error_cents, write_song
    song = write_song("balada", tmp_path / "balada")
    g = song["genre"]
    eng = host.engine
    eng.set_tempo(g.bpm)
    ids = {Path(p).stem.split("_", 1)[1]: eng.add_audio_track(p, Path(p).stem)["id"] for p in song["paths"]}
    for k, t in ids.items():
        eng.set_track_mute(t, k != "Voz_Lead")
    lead = _render(eng, tmp_path, "lead.wav")[:, 0]
    h = _fx(eng, ids["Voz_Lead"], "harmonizer", key=g.tonic, scale=2 if g.minor else 1, voice1=1, pan1=0, dry=0)
    harm = _render(eng, tmp_path, "harm.wav")[:, 0]
    e_lead, e_harm = pitch_error_cents(lead, g, SR), pitch_error_cents(harm, g, SR)

    def f0(y):
        f, v, p = librosa.pyin(y[: 40 * SR].astype(np.float32), fmin=70, fmax=1000, sr=SR, frame_length=2048, hop_length=512)
        return np.where(v & (p > 0.5), f, np.nan)
    fl, fh = f0(lead), f0(harm)
    ok = np.isfinite(fl) & np.isfinite(fh)
    gap = np.median(12 * np.log2(fh[ok] / fl[ok]))
    print(f"balada: voz {e_lead:.1f} c de la escala, armonía {e_harm:.1f} c; la armonía va {gap:.2f} st por encima")
    assert e_harm < 15 and e_harm < e_lead and 2.8 < gap < 4.2

    eng.set_effect_param(h, "dry", 100)
    coros = next(k for k in ids if "Coros" in k)
    _fx(eng, ids[coros], "doubler", voices=2)
    for t in ids.values():
        eng.set_track_mute(t, False)
    mix = _render(eng, tmp_path, "mix.wav")
    print(f"balada: mezcla con armonía y coros doblados, pico {np.abs(mix).max():.2f}")
    assert np.isfinite(mix).all() and 0.05 < np.abs(mix).max() <= 1.0


# ---------------------------------------------------------------- Dynamic EQ (AF-08)
_DYN = {"type1": 0, "type2": 1, "freq2": 3000, "q2": 2, "thr2": -30, "range2": -12, "type3": 0}


@pytest.mark.parametrize("amp_db,hz,lo,hi", [
    (-12, 3000, -12.5, -10.5),   # fuerte en la banda: hasta el rango
    (-24, 3000, -5.0, -2.0),     # 6 dB sobre el umbral: 2/3 dB por dB
    (-40, 3000, -0.2, 0.2),      # bajo el umbral: nada
    (-12, 300, -0.2, 0.2),       # fuera de la banda: nada
    (-12, 1000, -0.3, 0.2),
])
def test_dyneq_corta_solo_lo_fuerte_en_su_banda(host, tmp_path, amp_db, hz, lo, hi):
    y = _sine(hz, amp=10 ** (amp_db / 20))
    tid = _track(host, tmp_path, y, "t")
    _fx(host.engine, tid, "dyneq", **_DYN)
    z = _render(host.engine, tmp_path, "o.wav")[:, 0]
    d = db(rms(z[SR:2 * SR])) - db(rms(y[SR:]))
    print(f"dyneq {amp_db} dBFS {hz} Hz: {d:+.2f} dB")
    assert lo < d < hi


def test_dyneq_apagado_deja_la_senal_igual(host, tmp_path):
    rng = np.random.default_rng(3)
    y = 0.1 * rng.standard_normal(2 * SR)
    tid = _track(host, tmp_path, y, "t")
    ref = _render(host.engine, tmp_path, "ref.wav")
    _fx(host.engine, tid, "dyneq", type1=0, type2=0, type3=0)
    z = _render(host.engine, tmp_path, "o.wav")
    assert db(rms(z - ref)) < -120


# ---------------------------------------------------------------- Noise Reducer (AF-68)
def _ruido_y_tono():
    rng = np.random.default_rng(1)
    y = 10 ** (-50 / 20) * rng.standard_normal(4 * SR)
    y[SR:] += 10 ** (-20 / 20) * np.sin(2 * np.pi * 440 * np.arange(3 * SR) / SR)
    return y


def _banda(x, f0=2000, f1=8000):
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(4, [f0, f1], "band", fs=SR, output="sos"), x)


def test_denoise_quita_el_ruido_y_deja_el_tono(host, tmp_path):
    """Soplido a −50 dBFS y un La a −20: en la pausa el ruido baja ≥ 15 dB, con el tono el ruido de
    2–8 kHz también, y el tono no cambia (±0,2 dB)."""
    y = _ruido_y_tono()
    tid = _track(host, tmp_path, y, "t")
    ref = _render(host.engine, tmp_path, "ref.wav")[:, 0]
    _fx(host.engine, tid, "denoise", reduction=24)
    z = _render(host.engine, tmp_path, "o.wav")[:, 0]
    seg, pausa = slice(2 * SR, 4 * SR - SR // 4), slice(SR // 2, SR)
    d_pausa = db(rms(z[pausa])) - db(rms(ref[pausa]))
    d_banda = db(rms(_banda(z)[seg])) - db(rms(_banda(ref)[seg]))
    d_tono = db(rms(z[seg])) - db(rms(ref[seg]))
    print(f"denoise: pausa {d_pausa:+.1f} dB, ruido 2–8 kHz con tono {d_banda:+.1f} dB, tono {d_tono:+.2f} dB")
    assert d_pausa < -15 and d_banda < -12 and abs(d_tono) < 0.2


def test_denoise_escuchar_lo_que_quita(host, tmp_path):
    """En «Lo que quita» sale el ruido (casi al mismo nivel en la pausa) y el tono no."""
    y = _ruido_y_tono()
    tid = _track(host, tmp_path, y, "t")
    _fx(host.engine, tid, "denoise", reduction=24, listen=1)
    z = _render(host.engine, tmp_path, "o.wav")[:, 0]
    pausa = db(rms(z[SR // 2:SR])) - (-50)
    tono = db(rms(z[2 * SR:3 * SR])) - (-23)
    print(f"denoise escuchar: ruido {pausa:+.1f} dB, tono {tono:+.1f} dB")
    assert abs(pausa) < 1.5 and tono < -15


def test_denoise_mezcla_cero_no_cambia_nada(host, tmp_path):
    y = _ruido_y_tono()
    tid = _track(host, tmp_path, y, "t")
    ref = _render(host.engine, tmp_path, "ref.wav")
    _fx(host.engine, tid, "denoise", mix=0)
    z = _render(host.engine, tmp_path, "o.wav")
    assert db(rms(z - ref)) < -100


def test_balada_con_soplido_limpia_y_ecualizada(host, tmp_path):
    """La voz de la balada con un soplido de −55 dBFS: el Noise Reducer baja el ruido de las pausas
    ≥ 10 dB y deja la voz cantada a ±1 dB; con el Dynamic EQ en la voz la mezcla entera sale limpia."""
    from song_factory import write_song
    song = write_song("balada", tmp_path / "balada")
    eng = host.engine
    eng.set_tempo(song["genre"].bpm)
    paths = {Path(p).stem.split("_", 1)[1]: p for p in song["paths"]}
    voz, vsr = sf.read(paths["Voz_Lead"], always_2d=True)
    rng = np.random.default_rng(7)
    sucia = voz + 10 ** (-55 / 20) * rng.standard_normal(voz.shape)
    p = tmp_path / "voz_sucia.wav"
    sf.write(str(p), sucia, vsr, subtype="FLOAT")
    tid = eng.add_audio_track(str(p), "Voz sucia")["id"]
    ref = _render(eng, tmp_path, "ref.wav")[:, 0]
    _fx(eng, tid, "denoise", reduction=20)
    z = _render(eng, tmp_path, "limpia.wav")[:, 0]
    # tramos de 0,1 s: la voz limpia (a su frecuencia) dice si es pausa o canto; el render va a SR
    secs = min(len(ref), len(z)) / SR
    tramos = [(k, rms(voz[int(k * 0.1 * vsr):int((k + 1) * 0.1 * vsr), 0])) for k in range(int(secs / 0.1) - 1)]
    pausas = [k for k, r in tramos if r < 1e-4]
    canto = [k for k, r in tramos if r > 0.03]
    assert len(pausas) > 20 and len(canto) > 20
    hop = SR // 10
    sel = lambda x, idx: np.concatenate([x[k * hop:(k + 1) * hop] for k in idx])
    d_pausa = db(rms(sel(z, pausas))) - db(rms(sel(ref, pausas)))
    d_canto = db(rms(sel(z, canto))) - db(rms(sel(ref, canto)))
    print(f"balada con soplido: pausas {d_pausa:+.1f} dB, voz {d_canto:+.2f} dB")
    assert d_pausa < -10 and abs(d_canto) < 1.0

    _fx(eng, tid, "dyneq", type1=1, freq1=350, q1=1.2, thr1=-28, range1=-5,
        type2=1, freq2=3200, q2=2.0, thr2=-30, range2=-6, type3=0)
    for k, path in paths.items():
        if k != "Voz_Lead":
            eng.add_audio_track(path, k)
    mix = _render(eng, tmp_path, "mix.wav")
    print(f"balada limpia y ecualizada: pico de la mezcla {np.abs(mix).max():.2f}")
    assert np.isfinite(mix).all() and 0.05 < np.abs(mix).max() <= 1.0

"""Sinte de tablas (preset 10 del Instrumento, motor C++): cuatro tablas de 8 ondas cada una, sin aliasing
(una tabla por octava), posición, barrido, movimiento, ataque y liberación. Medido en el render real; y un
reguetón completo con los acordes y la melodía del sinte de tablas, en tono compás a compás."""
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import WAVE_KNOBS, EngineHost, afo_audio, synth_settings

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")

WAVE = 10
A3 = 57                                         # 220 Hz
STILL = dict(wtEnv=0, wtLfo=0, wtAtk=0)


@pytest.fixture()
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    yield h
    h.engine = None


def _knobs(**kw):
    d = dict(WAVE_KNOBS)
    d.update(kw)
    return [float(d[k]) for k, _ in WAVE_KNOBS]


def _play(eng, tmp_path, notes, name="wt.wav", **kw):
    """notes = [(inicio, duración en negras, nota)] a 120 BPM en una pista nueva del sinte de tablas."""
    eng.set_tempo(120.0)
    for t in eng.tracks():
        eng.remove_track(t["id"])
    tid = eng.add_synth_track("Tablas", 0)["id"]
    eng.set_synth_settings(tid, mode=0, wave=WAVE, vel=100, wavetable=_knobs(**kw))
    eng.set_synth_midi(tid, [(s, d, n, 100) for s, d, n in notes], max(s + d for s, d, _ in notes) + 4.0)
    out = tmp_path / name
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    return y[:, 0], sr


def _spec(x, sr, pad=4):
    s = np.abs(np.fft.rfft(x * np.hanning(len(x)), pad * len(x)))
    return np.fft.rfftfreq(pad * len(x), 1 / sr), s


def _harm_db(x, sr, f0, hs):
    """Nivel de los armónicos `hs` frente a la fundamental, en dB."""
    f, s = _spec(x, sr)
    lvl = lambda fr: s[np.abs(f - fr) < 3].max()
    ref = lvl(f0)
    return [20 * np.log10(lvl(h * f0) / ref + 1e-12) for h in hs]


def _centroid(x, sr):
    f, s = _spec(x, sr, 1)
    return float((f * s).sum() / s.sum())


def test_basica_de_seno_a_cuadrada(host, tmp_path):
    eng = host.engine
    y, sr = _play(eng, tmp_path, [(0.0, 4.0, A3)], wtTab=0, wtPos=0, **STILL)
    sine = _harm_db(y[int(0.3 * sr): int(1.5 * sr)], sr, 220, range(2, 9))
    y, sr = _play(eng, tmp_path, [(0.0, 4.0, A3)], wtTab=0, wtPos=100, **STILL)
    h2, h3, h4, h5 = _harm_db(y[int(0.3 * sr): int(1.5 * sr)], sr, 220, (2, 3, 4, 5))
    print(f"posición 0: armónicos 2..8 a {max(sine):.1f} dB como mucho · posición 100: "
          f"h2 {h2:.1f}, h3 {h3:.1f}, h4 {h4:.1f}, h5 {h5:.1f} dB (cuadrada: h3 −9,5, h5 −14,0)")
    assert max(sine) < -50, "en posición 0 suena un seno puro"
    assert h3 == pytest.approx(-9.54, abs=1.0) and h5 == pytest.approx(-13.98, abs=1.0)
    assert h2 < -40 and h4 < -40, "la cuadrada no tiene armónicos pares"


def test_vocal_y_digital(host, tmp_path):
    eng = host.engine
    C3 = 48                                     # 130,8 Hz: las formantes se dibujaron sobre un do3
    def bands(pos):
        y, sr = _play(eng, tmp_path, [(0.0, 4.0, C3)], wtTab=1, wtPos=pos, **STILL)
        f, s = _spec(y[int(0.3 * sr): int(1.5 * sr)], sr)
        e = lambda lo, hi: (s[(f > lo) & (f < hi)] ** 2).sum()
        return 10 * np.log10(e(1900, 2700) / e(500, 950))
    u, i = bands(0), bands(100)
    print(f"Vocal: energía 1,9–2,7 kHz frente a 0,5–0,95 kHz: «u» {u:+.1f} dB → «i» {i:+.1f} dB")
    assert i > u + 15, "la «i» tiene su segunda formante arriba; la «u», abajo"

    y, sr = _play(eng, tmp_path, [(0.0, 4.0, A3)], wtTab=3, wtPos=0, **STILL)
    sq = _harm_db(y[int(0.3 * sr): int(1.5 * sr)], sr, 220, (2,))[0]
    y, sr = _play(eng, tmp_path, [(0.0, 4.0, A3)], wtTab=3, wtPos=100, **STILL)
    thin = _harm_db(y[int(0.3 * sr): int(1.5 * sr)], sr, 220, (2,))[0]
    print(f"Digital: segundo armónico {sq:.1f} dB (pulso 50 %) → {thin:.1f} dB (pulso 5 %)")
    assert sq < -40 and thin > -3


def test_sin_aliasing_en_notas_agudas(host, tmp_path):
    """La cuadrada en un do7 y un do8: todo lo que suena son armónicos de la nota (nada reflejado)."""
    eng = host.engine
    for note in (96, 108):
        f0 = 440 * 2 ** ((note - 69) / 12)
        y, sr = _play(eng, tmp_path, [(0.0, 4.0, note)], wtTab=0, wtPos=100, **STILL)
        f, s = _spec(y[int(0.3 * sr): int(1.5 * sr)], sr)
        harm = np.abs(f / f0 - np.round(f / f0)) * f0 < 15
        stray = 20 * np.log10(s[~harm & (f > 20)].max() / s.max())
        print(f"nota {note} ({f0:.0f} Hz): lo que no es armónico queda a {stray:.1f} dB")
        assert stray < -60


def test_barrido_movimiento_ataque_y_liberacion(host, tmp_path):
    eng = host.engine
    y, sr = _play(eng, tmp_path, [(0.0, 4.0, A3)], wtTab=0, wtPos=0, wtEnv=100, wtLfo=0, wtAtk=0)
    start, later = _centroid(y[int(0.01 * sr): int(0.08 * sr)], sr), _centroid(y[int(1.2 * sr): int(1.5 * sr)], sr)
    print(f"barrido 100: centroide {start:.0f} Hz al empezar → {later:.0f} Hz después")
    assert start > 2 * later

    y, sr = _play(eng, tmp_path, [(0.0, 4.0, A3)], wtTab=0, wtPos=50, wtEnv=0, wtLfo=100, wtAtk=0)
    up, down = _centroid(y[int(1.2 * sr): int(1.3 * sr)], sr), _centroid(y[int(1.7 * sr): int(1.8 * sr)], sr)
    print(f"movimiento 100 (1 Hz): centroide {up:.0f} Hz → {down:.0f} Hz medio segundo después")
    assert up > 1.5 * down

    def rms(y, sr):
        return np.sqrt(np.convolve(y ** 2, np.ones(int(0.005 * sr)) / int(0.005 * sr), "same"))
    times = []
    for atk in (0, 60):
        y, sr = _play(eng, tmp_path, [(0.0, 2.0, A3)], wtAtk=atk, wtEnv=0)
        e = rms(y, sr)
        times.append(np.flatnonzero(e > 0.5 * e.max())[0] / sr)
    tails = []
    for rel in (0, 70):
        y, sr = _play(eng, tmp_path, [(0.0, 2.0, A3)], wtRel=rel, wtEnv=0, wtAtk=0)
        e = rms(y, sr)
        tails.append(np.flatnonzero(e > e[int(0.9 * sr)] * 10 ** (-40 / 20))[-1] / sr - 1.0)
    print(f"ataque 0 → 60: mitad del nivel a {1000 * times[0]:.0f} → {1000 * times[1]:.0f} ms · "
          f"liberación 0 → 70: {1000 * tails[0]:.0f} → {1000 * tails[1]:.0f} ms tras soltarla")
    assert times[0] < 0.01 and 0.03 < times[1] < 0.09
    assert tails[0] < 0.03 and 0.25 < tails[1] < 0.6

    assert eng.audition_synth(A3, 0.4, mode=0, wave=WAVE, wavetable=_knobs(wtTab=2))
    eng.preview_stop()


def test_ajustes_desde_la_pista():
    s = synth_settings({"type": "inst", "sus": False, "cfg": {"v": WAVE, "wtTab": 3, "wtPos": 80}})
    assert s["wave"] == WAVE and s["wavetable"] == [3.0, 80.0, 30.0, 0.0, 5.0, 30.0]


def test_regueton_completo_con_acordes_y_melodia_de_tablas(host, tmp_path):
    """Un reguetón entero (dembow, bajo, voces) con los acordes (tabla Vocal) y una melodía (tabla
    Digital) del sinte de tablas: en cada compás, las notas que más suenan son las de su acorde."""
    from song_factory import _chord, write_song
    song = write_song("regueton", tmp_path / "regueton")
    g = song["genre"]
    eng = host.engine
    eng.set_tempo(g.bpm)
    others = [eng.add_audio_track(p, Path(p).stem)["id"] for p in song["paths"] if not Path(p).stem.endswith("_synth")]
    bars = int(g.seconds * g.bpm / 60 // 4)
    chords = [_chord(g, g.progression[b % len(g.progression)], 4) for b in range(bars)]
    pad = eng.add_synth_track("Acordes de tablas", 0)["id"]
    eng.set_synth_settings(pad, mode=0, wave=WAVE, vel=70, wavetable=_knobs(wtTab=1, wtPos=50, wtLfo=30, wtAtk=30, wtRel=50))
    eng.set_synth_midi(pad, [(b * 4.0, 3.8, n, 80) for b, c in enumerate(chords) for n in c], bars * 4.0)
    lead = eng.add_synth_track("Melodía de tablas", 0)["id"]
    eng.set_synth_settings(lead, mode=0, wave=WAVE, vel=80, wavetable=_knobs(wtTab=3, wtPos=30, wtEnv=60))
    eng.set_synth_midi(lead, [(b * 4.0 + k, 0.45, c[k % 3] + 12, 90) for b, c in enumerate(chords) for k in (0, 1, 2, 3)],
                       bars * 4.0)
    assert eng.render_to_wav(str(tmp_path / "mix.wav"))
    y, sr = sf.read(str(tmp_path / "mix.wav"))
    assert 0.05 < np.abs(y).max() <= 1.0

    for o in others + [lead]:
        eng.set_track_mute(o, True)
    beat = 60 / g.bpm

    def render(name):
        assert eng.render_to_wav(str(tmp_path / name))
        return sf.read(str(tmp_path / name))

    def fund(w, sr, notes):
        """Energía en la fundamental de cada nota candidata (la tabla Vocal realza armónicos como el 7.º,
        que caen en otras notas: por eso se mira la fundamental y no un cromagrama)."""
        f, s = _spec(w, sr, 2)
        return {n: s[np.abs(f / (440 * 2 ** ((n - 69) / 12)) - 1) < 0.012].max() for n in notes}

    y, sr = render("pad.wav")
    y = y[:, 0]
    misses = []
    for b, c in enumerate(chords):
        t0 = b * 4 * beat
        e = fund(y[int((t0 + 0.2 * beat) * sr): int((t0 + 3.6 * beat) * sr)], sr, range(min(c) - 5, max(c) + 3))
        top = sorted(e, key=e.get)[::-1][:3]
        print(f"acordes, compás {b + 1}: {sorted(c)} → fundamentales más fuertes {sorted(top)}")
        if {n % 12 for n in top} - {n % 12 for n in c}:
            misses.append(b + 1)
    assert not misses, f"acordes fuera de tono en los compases {misses}"

    eng.set_track_mute(pad, True)
    eng.set_track_mute(lead, False)
    y, sr = render("lead.wav")
    y = y[:, 0]
    wrong = []
    for b, c in enumerate(chords):
        for k in range(4):
            t0 = (b * 4 + k) * beat
            want = c[k % 3] + 12
            e = fund(y[int((t0 + 0.05 * beat) * sr): int((t0 + 0.45 * beat) * sr)], sr, range(want - 6, want + 7))
            if max(e, key=e.get) != want:
                wrong.append((b + 1, k + 1))
    print(f"melodía: {4 * len(chords)} notas, fuera de tono {wrong}")
    assert not wrong

"""Sinte analógico (preset 9 del Instrumento, motor C++): dos dientes de sierra desafinados, filtro paso
bajo resonante con envolvente, ataque y liberación. Medido en el render real; y un house completo con
bajo y acordes del sinte analógico, en tono compás a compás."""
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import ANALOG_KNOBS, EngineHost, afo_audio, synth_settings

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")

ANALOG = 9
A3 = 57                                         # 220 Hz


@pytest.fixture()
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    yield h
    h.engine = None


def _knobs(**kw):
    d = dict(ANALOG_KNOBS)
    d.update(kw)
    return [float(d[k]) for k, _ in ANALOG_KNOBS]


def _play(eng, tmp_path, notes, name="an.wav", **kw):
    """notes = [(inicio, duración en negras, nota)] a 120 BPM en una pista nueva del sinte analógico."""
    eng.set_tempo(120.0)
    for t in eng.tracks():
        eng.remove_track(t["id"])
    tid = eng.add_synth_track("Analógico", 0)["id"]
    eng.set_synth_settings(tid, mode=0, wave=ANALOG, vel=100, bri=50, analog=_knobs(**kw))
    eng.set_synth_midi(tid, [(s, d, n, 100) for s, d, n in notes], max(s + d for s, d, _ in notes) + 4.0)
    out = tmp_path / name
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    return y[:, 0], sr


def _spec(x, sr, pad=8):
    s = np.abs(np.fft.rfft(x * np.hanning(len(x)), pad * len(x)))
    return np.fft.rfftfreq(pad * len(x), 1 / sr), s


def _centroid(x, sr):
    f, s = _spec(x, sr, 1)
    return float((f * s).sum() / s.sum())


def _peaks(x, sr, lo, hi, n=2):
    f, s = _spec(x, sr)
    m = (f >= lo) & (f <= hi)
    f, s = f[m], s[m]
    loc = np.flatnonzero((s[1:-1] > s[:-2]) & (s[1:-1] > s[2:])) + 1
    best = loc[np.argsort(s[loc])[::-1][:n]]
    return sorted(f[best]), s[best]


def test_dos_osciladores_desafinados(host, tmp_path):
    eng = host.engine
    common = dict(anCut=100, anEnv=0, anRes=0, anAtk=0)
    y, sr = _play(eng, tmp_path, [(0.0, 8.0, A3)], anDet=100, **common)
    (lo, hi), _ = _peaks(y[int(0.5 * sr): int(3.5 * sr)], sr, 205, 235)
    want = 220 * 2 ** (25 / 1200), 220 * 2 ** (-25 / 1200)
    print(f"desafinar 100: {lo:.2f} Hz y {hi:.2f} Hz (esperado {want[1]:.2f} y {want[0]:.2f})")
    assert lo == pytest.approx(want[1], abs=0.5) and hi == pytest.approx(want[0], abs=0.5)

    y, sr = _play(eng, tmp_path, [(0.0, 8.0, A3)], anDet=0, **common)
    f, s = _spec(y[int(0.5 * sr): int(3.5 * sr)], sr)
    m = (f > 200) & (f < 240)
    assert f[m][s[m].argmax()] == pytest.approx(220, abs=0.3), "al unísono: una sola nota en 220 Hz"


def test_corte_resonancia_y_envolvente_del_filtro(host, tmp_path):
    eng = host.engine
    c = []
    for cut in (25, 50, 75):
        y, sr = _play(eng, tmp_path, [(0.0, 2.0, A3)], anCut=cut, anEnv=0, anRes=0, anDet=0)
        c.append(_centroid(y[int(0.3 * sr): int(0.9 * sr)], sr))
    print("corte 25 / 50 / 75 → centroide (Hz):", [round(v) for v in c])
    assert c[0] < c[1] < c[2] and c[2] > 2 * c[0]

    # Resonancia: con el corte cerca de 830 Hz, los armónicos de esa zona suben frente a la fundamental
    def zone_db(res):
        y, sr = _play(eng, tmp_path, [(0.0, 2.0, A3)], anCut=50, anEnv=0, anRes=res, anDet=0)
        f, s = _spec(y[int(0.3 * sr): int(0.9 * sr)], sr)
        zone = s[(f > 600) & (f < 1100)].max()
        return 20 * np.log10(zone / s[np.abs(f - 220) < 5].max())
    flat, peaky = zone_db(0), zone_db(90)
    print(f"resonancia 0 → 90: zona del corte {flat:+.1f} dB → {peaky:+.1f} dB frente a la fundamental")
    assert peaky > flat + 8

    # Envolvente: abre el filtro al empezar la nota y se cierra en 0,3 s
    y, sr = _play(eng, tmp_path, [(0.0, 2.0, A3)], anCut=35, anEnv=100, anRes=20, anDet=0)
    start, later = _centroid(y[int(0.01 * sr): int(0.06 * sr)], sr), _centroid(y[int(0.6 * sr): int(0.9 * sr)], sr)
    print(f"envolvente 100: centroide {start:.0f} Hz al empezar → {later:.0f} Hz después")
    assert start > 2 * later


def test_ataque_y_liberacion(host, tmp_path):
    eng = host.engine
    def rms(y, sr):
        return np.sqrt(np.convolve(y ** 2, np.ones(int(0.005 * sr)) / int(0.005 * sr), "same"))
    y, sr = _play(eng, tmp_path, [(0.0, 2.0, A3)], anAtk=0, anCut=80, anEnv=0)
    e = rms(y, sr)
    t_fast = np.flatnonzero(e > 0.5 * e.max())[0] / sr
    y, sr = _play(eng, tmp_path, [(0.0, 2.0, A3)], anAtk=60, anCut=80, anEnv=0)      # 1 ms · 2^6,6 ≈ 97 ms
    e = rms(y, sr)
    t_slow = np.flatnonzero(e > 0.5 * e.max())[0] / sr
    print(f"ataque 0 → 60: mitad del nivel a {1000 * t_fast:.0f} ms → {1000 * t_slow:.0f} ms")
    assert t_fast < 0.01 and 0.03 < t_slow < 0.09

    tails = []
    for rel in (0, 70):                                                         # 10 ms y ≈ 0,53 s
        y, sr = _play(eng, tmp_path, [(0.0, 2.0, A3)], anRel=rel, anCut=80, anEnv=0)
        e = rms(y, sr)
        tails.append(np.flatnonzero(e > e[int(0.9 * sr)] * 10 ** (-40 / 20))[-1] / sr - 1.0)
    print(f"liberación 0 → 70: la nota se oye {1000 * tails[0]:.0f} ms → {1000 * tails[1]:.0f} ms tras soltarla")
    assert tails[0] < 0.03 and 0.25 < tails[1] < 0.6

    # Al pulsar una tecla del piano roll también suena (nota corta de la rejilla, con su liberación)
    assert eng.audition_synth(A3, 0.4, mode=0, wave=ANALOG, analog=_knobs())
    eng.preview_stop()


def test_ajustes_desde_la_pista():
    s = synth_settings({"type": "inst", "sus": False, "cfg": {"v": ANALOG, "anCut": 80, "anRel": 10}})
    assert s["wave"] == ANALOG and s["analog"] == [30.0, 80.0, 30.0, 50.0, 5.0, 10.0]


def test_house_completo_con_bajo_y_acordes_analogicos(host, tmp_path):
    """Un house entero (bombo, palmas, charles, voz) con el bajo y los acordes del sinte analógico:
    cada compás, el bajo suena en la tónica de su acorde y la mezcla no satura."""
    from song_factory import _chord, hz, write_song
    song = write_song("house", tmp_path / "house")
    g = song["genre"]
    eng = host.engine
    eng.set_tempo(g.bpm)
    others = [eng.add_audio_track(p, Path(p).stem)["id"] for p in song["paths"]
              if not any(Path(p).stem.endswith(s) for s in ("_bass", "_synth"))]
    bars = int(g.seconds * g.bpm / 60 // 4)
    chords = [_chord(g, g.progression[b % len(g.progression)], 4) for b in range(bars)]
    bass = eng.add_synth_track("Bajo analógico", 0)["id"]
    eng.set_synth_settings(bass, mode=0, wave=ANALOG, vel=100, analog=_knobs(anDet=15, anCut=35, anRes=45, anEnv=60, anRel=10))
    eng.set_synth_midi(bass, [(b * 4.0 + k, 0.9, c[0] - 24, 100) for b, c in enumerate(chords) for k in range(4)], bars * 4.0)
    pad = eng.add_synth_track("Acordes analógicos", 0)["id"]
    eng.set_synth_settings(pad, mode=0, wave=ANALOG, vel=60, analog=_knobs(anDet=40, anCut=55, anAtk=40, anRel=60))
    eng.set_synth_midi(pad, [(b * 4.0, 3.8, n, 80) for b, c in enumerate(chords) for n in c], bars * 4.0)
    assert eng.render_to_wav(str(tmp_path / "mix.wav"))
    y, sr = sf.read(str(tmp_path / "mix.wav"))
    assert 0.05 < np.abs(y).max() <= 1.0

    for o in others + [pad]:
        eng.set_track_mute(o, True)
    assert eng.render_to_wav(str(tmp_path / "bass.wav"))
    y, sr = sf.read(str(tmp_path / "bass.wav"))
    y = y[:, 0]
    beat = 60 / g.bpm
    misses = []
    for b, c in enumerate(chords):
        t0 = b * 4 * beat
        w = y[int((t0 + 0.1 * beat) * sr): int((t0 + 0.85 * beat) * sr)]
        f, s = _spec(w, sr, 16)
        m = (f > 30) & (f < 200)
        got = f[m][s[m].argmax()]
        want = float(hz(c[0] - 24))
        print(f"compás {b + 1}: tónica {want:.1f} Hz → {got:.1f} Hz")
        if abs(got / want - 1) > 0.03:
            misses.append(b + 1)
    assert not misses, f"compases fuera de tono: {misses}"

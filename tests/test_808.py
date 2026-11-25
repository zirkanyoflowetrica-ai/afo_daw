"""808 Lab (preset «Bajo 808» del Instrumento): golpe de afinación, saturación, deslizamiento entre notas
que se pisan y monofonía, medidos en el render real del motor; y un trap completo con su 808 en tono."""
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")

BASS_808 = 8


@pytest.fixture()
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    yield h
    h.engine = None


def _render(eng, tmp_path, name="808.wav"):
    out = tmp_path / name
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    return y[:, 0], sr


def _cross_hz(x, sr):
    """Frecuencia por cruces por cero ascendentes (sirve para tramos cortos de un seno grave)."""
    s = np.signbit(x)
    ups = np.flatnonzero(s[:-1] & ~s[1:])
    if len(ups) < 2:
        return 0.0
    return (len(ups) - 1) / ((ups[-1] - ups[0]) / sr)


def _band_peak_hz(x, sr, lo, hi):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), 8 * len(x)))
    f = np.fft.rfftfreq(8 * len(x), 1 / sr)
    m = (f >= lo) & (f <= hi)
    return f[m][spec[m].argmax()]


def _level_db(x, sr, hz):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    f = np.fft.rfftfreq(len(x), 1 / sr)
    return 20 * np.log10(spec[np.abs(f - hz) < 3].max() + 1e-12)


def _track(eng, **kw):
    eng.set_tempo(120.0)                                         # negra = 0,5 s
    tid = eng.add_synth_track("808", 0)["id"]
    eng.set_synth_settings(tid, mode=0, wave=BASS_808, vel=100, bri=100, **kw)
    return tid


def test_golpe_y_saturacion(host, tmp_path):
    eng = host.engine
    tid = _track(eng, glide=0, drive=0, punch=0)
    eng.set_synth_midi(tid, [(0.0, 2.0, 33, 100)], 4.0)          # La1 = 55 Hz durante 1 s
    y, sr = _render(eng, tmp_path)
    assert 0.1 < np.abs(y).max() <= 1.0
    body = y[int(0.2 * sr): int(0.9 * sr)]
    assert _band_peak_hz(body, sr, 30, 200) == pytest.approx(55, abs=1.5)
    plain_onset = _cross_hz(y[: int(0.03 * sr)], sr)
    clean_h3 = _level_db(body, sr, 165) - _level_db(body, sr, 55)

    eng.set_synth_settings(tid, mode=0, wave=BASS_808, vel=100, bri=100, glide=0, drive=0, punch=100)
    y, sr = _render(eng, tmp_path)
    punch_onset = _cross_hz(y[: int(0.03 * sr)], sr)
    assert _band_peak_hz(y[int(0.2 * sr): int(0.9 * sr)], sr, 30, 200) == pytest.approx(55, abs=1.5)  # luego, en su nota
    print(f"golpe: {plain_onset:.0f} Hz → {punch_onset:.0f} Hz en los primeros 30 ms")
    assert punch_onset > 2 * max(plain_onset, 55)

    eng.set_synth_settings(tid, mode=0, wave=BASS_808, vel=100, bri=100, glide=0, drive=100, punch=0)
    y, sr = _render(eng, tmp_path)
    body = y[int(0.2 * sr): int(0.9 * sr)]
    driven_h3 = _level_db(body, sr, 165) - _level_db(body, sr, 55)
    print(f"tercer armónico: {clean_h3:.0f} dB → {driven_h3:.0f} dB con saturación")
    assert clean_h3 < -40 and driven_h3 > -20
    assert np.abs(y).max() <= 1.0


def test_deslizamiento_entre_notas_que_se_pisan(host, tmp_path):
    eng = host.engine
    # La1 (55 Hz) de 0 a 1 s; La2 (110 Hz) entra a 0,75 s, pisándola: con glide se desliza en 300 ms
    notes = [(0.0, 2.0, 33, 100), (1.5, 1.5, 45, 100)]
    tid = _track(eng, glide=100, drive=0, punch=0)
    eng.set_synth_midi(tid, notes, 4.0)
    y, sr = _render(eng, tmp_path)
    mid = _cross_hz(y[int(0.80 * sr): int(0.95 * sr)], sr)
    end = _band_peak_hz(y[int(1.1 * sr): int(1.45 * sr)], sr, 30, 200)
    env = np.abs(y)
    before, during = env[int(0.6 * sr): int(0.75 * sr)].max(), env[int(0.75 * sr): int(0.85 * sr)].max()
    print(f"glide: a mitad {mid:.0f} Hz, al final {end:.0f} Hz; nivel {before:.3f} → {during:.3f}")
    assert 62 < mid < 105, "a mitad del deslizamiento, entre las dos notas"
    assert end == pytest.approx(110, abs=3)
    assert during < before * 1.15, "no vuelve a atacar: sigue la misma nota"

    # Sin glide: la nota nueva corta la anterior (monofónico) y suena ya en su altura
    eng.set_synth_settings(tid, mode=0, wave=BASS_808, vel=100, bri=100, glide=0, drive=0, punch=0)
    y, sr = _render(eng, tmp_path)
    w = y[int(0.78 * sr): int(0.98 * sr)]
    assert _band_peak_hz(w, sr, 30, 200) == pytest.approx(110, abs=3)
    left = _level_db(w, sr, 55) - _level_db(w, sr, 110)
    print(f"sin glide: la nota anterior queda a {left:.0f} dB")
    assert left < -25, "la nota anterior se cortó (una sola voz de 808)"


def test_trap_completo_con_su_808(host, tmp_path):
    """Un trap entero (batería, pad, dos voces) con el 808 del motor en lugar del bajo de fábrica:
    cada compás suena en la tónica de su acorde y el deslizamiento de final de compás sube una octava."""
    from song_factory import _chord, hz, write_song
    song = write_song("trap", tmp_path / "trap")
    g = song["genre"]
    eng = host.engine
    eng.set_tempo(g.bpm)
    for p in song["paths"]:
        if not Path(p).stem.endswith("_808"):
            eng.add_audio_track(p, Path(p).stem)
    tid = eng.add_synth_track("808", 0)["id"]
    eng.set_synth_settings(tid, mode=0, wave=BASS_808, vel=90, bri=60, glide=30, drive=40, punch=50)
    bars = int(g.seconds * g.bpm / 60 // 4)
    roots = [_chord(g, g.progression[b % len(g.progression)], 1)[0] for b in range(bars)]
    notes = []
    for b, r in enumerate(roots):
        notes.append((b * 4.0, 3.5, r, 100))                    # tónica del compás
        notes.append((b * 4.0 + 3.0, 0.9, r + 12, 100))         # pisa a la tónica: sube deslizándose
    eng.set_synth_midi(tid, notes, bars * 4.0)
    y, sr = _render(eng, tmp_path, "trap.wav")
    assert np.abs(y).max() <= 1.0
    beat = 60.0 / g.bpm
    misses = []
    for b, r in enumerate(roots[:-1]):
        t0 = b * 4 * beat
        got = _band_peak_hz(y[int((t0 + 0.4 * beat) * sr): int((t0 + 2.8 * beat) * sr)], sr, 30, 100)
        up = _band_peak_hz(y[int((t0 + 3.45 * beat) * sr): int((t0 + 3.85 * beat) * sr)], sr, 60, 200)
        print(f"compás {b + 1}: tónica {hz(r):.1f} Hz → {got:.1f} Hz; octava {2 * hz(r):.1f} → {up:.1f} Hz")
        if abs(got / hz(r) - 1) > 0.04 or abs(up / (2 * hz(r)) - 1) > 0.05:
            misses.append(b + 1)
    assert not misses, f"compases fuera de tono: {misses}"

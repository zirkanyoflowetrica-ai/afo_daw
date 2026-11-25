"""Arpegiador del Instrumento (motor C++): las notas pulsadas suenan de una en una en la rejilla del
tempo, arriba / abajo / arriba y abajo / al azar repetible, en 1..4 octavas, con la duración de nota
elegida. Medido en el render real; y un house completo con su acorde arpegiado compás a compás."""
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import EngineHost, afo_audio, synth_settings

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")

PIANO = 0
DO_MAYOR = [60, 64, 67]


@pytest.fixture()
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    yield h
    h.engine = None


def _render(eng, tmp_path, name="arp.wav"):
    out = tmp_path / name
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    return y[:, 0], sr


def _midi_of(x, sr):
    """Nota MIDI más fuerte de un tramo corto (pico del espectro con relleno de ceros)."""
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), 16 * len(x)))
    f = np.fft.rfftfreq(16 * len(x), 1 / sr)
    m = (f > 80) & (f < 2000)
    return int(round(69 + 12 * np.log2(f[m][spec[m].argmax()] / 440)))


def _steps(y, sr, step, count, t0=0.0):
    """Nota de cada paso de la rejilla, escuchando del 15 % al 45 % del paso."""
    return [_midi_of(y[int((t0 + k * step + 0.15 * step) * sr): int((t0 + k * step + 0.45 * step) * sr)], sr)
            for k in range(count)]


def _chord_track(eng, notes, beats, bpm=120.0, **kw):
    eng.set_tempo(bpm)
    tid = eng.add_synth_track("Arpegio", 0)["id"]
    eng.set_synth_settings(tid, mode=0, wave=PIANO, vel=100, bri=100, **kw)
    eng.set_synth_midi(tid, [(0.0, beats, n, 100) for n in notes], beats + 1.0)
    return tid


def test_patrones_arriba_abajo_y_octavas(host, tmp_path):
    eng = host.engine
    tid = _chord_track(eng, DO_MAYOR, 2.0, arp=1, arp_rate=2, arp_gate=50)     # semicorcheas a 120 = 0,125 s
    y, sr = _render(eng, tmp_path)
    got = _steps(y, sr, 0.125, 8)
    print("arriba:", got)
    assert got == [60, 64, 67, 60, 64, 67, 60, 64]

    eng.set_synth_settings(tid, mode=0, wave=PIANO, vel=100, bri=100, arp=2, arp_rate=2)
    assert _steps(*_render(eng, tmp_path), 0.125, 6) == [67, 64, 60, 67, 64, 60]

    eng.set_synth_settings(tid, mode=0, wave=PIANO, vel=100, bri=100, arp=3, arp_rate=2)
    assert _steps(*_render(eng, tmp_path), 0.125, 8) == [60, 64, 67, 64, 60, 64, 67, 64]

    eng.set_synth_settings(tid, mode=0, wave=PIANO, vel=100, bri=100, arp=1, arp_rate=2, arp_oct=2)
    assert _steps(*_render(eng, tmp_path), 0.125, 8) == [60, 64, 67, 72, 76, 79, 60, 64]

    # Apagado: el acorde suena entero a la vez y dura lo que el clip
    eng.set_synth_settings(tid, mode=0, wave=PIANO, vel=100, bri=100, arp=0)
    y, sr = _render(eng, tmp_path)
    w = y[int(0.3 * sr): int(0.6 * sr)]
    spec = np.abs(np.fft.rfft(w * np.hanning(len(w))))
    f = np.fft.rfftfreq(len(w), 1 / sr)
    lv = [spec[np.abs(f - 440 * 2 ** ((m - 69) / 12)) < 4].max() for m in DO_MAYOR]
    assert min(lv) > 0.2 * max(lv), "sin arpegiador suenan las tres notas juntas"


def test_rejilla_del_tempo_velocidad_y_duracion(host, tmp_path):
    eng = host.engine
    tid = _chord_track(eng, DO_MAYOR, 4.0, bpm=90.0, arp=1, arp_rate=1, arp_gate=30)   # corcheas a 90 = 0,333 s
    y, sr = _render(eng, tmp_path)
    step = 60 / 90 / 2
    assert _steps(y, sr, step, 6) == [60, 64, 67, 60, 64, 67]
    env = np.convolve(np.abs(y), np.ones(int(0.005 * sr)) / int(0.005 * sr), "same")
    on = [env[int((k * step + 0.1 * step) * sr): int((k * step + 0.25 * step) * sr)].mean() for k in range(6)]
    off = [env[int((k * step + 0.6 * step) * sr): int((k * step + 0.95 * step) * sr)].mean() for k in range(6)]
    print(f"duración 30 %: suena {np.mean(on):.4f}, calla {np.mean(off):.4f}")
    assert max(off) < 0.1 * min(on), "con 30 % cada nota se apaga antes de mitad de paso"
    # Cada nota empieza en su paso de la rejilla (±3 ms)
    rise = np.flatnonzero((env[1:] > 0.3 * max(on)) & (env[:-1] <= 0.3 * max(on))) / sr
    for k in range(6):
        assert np.min(np.abs(rise - k * step)) < 0.006, f"paso {k} fuera de la rejilla"

    eng.set_synth_settings(tid, mode=0, wave=PIANO, vel=100, bri=100, arp=1, arp_rate=1, arp_gate=100)
    y, sr = _render(eng, tmp_path)
    env = np.convolve(np.abs(y), np.ones(int(0.005 * sr)) / int(0.005 * sr), "same")
    legato = [env[int((k * step + 0.6 * step) * sr): int((k * step + 0.95 * step) * sr)].mean() for k in range(6)]
    assert min(legato) > 0.3 * np.mean(on), "con 100 % la nota llena su paso"

    eng.set_tempo(150.0)                                            # cambia el tempo: la rejilla le sigue
    eng.set_synth_settings(tid, mode=0, wave=PIANO, vel=100, bri=100, arp=1, arp_rate=3, arp_gate=50)
    y, sr = _render(eng, tmp_path)
    assert _steps(y, sr, 60 / 150 / 8, 6) == [60, 64, 67, 60, 64, 67], "fusas a 150"


def test_al_azar_es_repetible_y_solo_toca_el_acorde(host, tmp_path):
    eng = host.engine
    _chord_track(eng, DO_MAYOR, 4.0, arp=4, arp_rate=2, arp_oct=2)
    y1, sr = _render(eng, tmp_path, "a.wav")
    y2, _ = _render(eng, tmp_path, "b.wav")
    assert np.array_equal(y1, y2), "el mismo render da las mismas notas"
    got = _steps(y1, sr, 0.125, 16)
    print("al azar:", got)
    assert set(got) <= set(DO_MAYOR + [n + 12 for n in DO_MAYOR]) and len(set(got)) >= 4


def test_ajustes_desde_la_pista():
    s = synth_settings({"type": "inst", "cfg": {"v": 0, "arp": 3, "arpRate": 1, "arpOct": 2, "arpGate": 80}})
    assert (s["arp"], s["arp_rate"], s["arp_oct"], s["arp_gate"]) == (3, 1, 2, 80.0)
    assert synth_settings({"type": "inst", "cfg": {"v": 0}})["arp"] == 0, "apagado por defecto"


def test_house_completo_con_acordes_arpegiados(host, tmp_path):
    """Un house entero (bombo, palmas, charles, bajo y voz) con los acordes del sinte arpegiados en el
    motor: cada paso suena una nota del acorde de su compás, en la rejilla de 124 BPM."""
    from song_factory import _chord, write_song
    song = write_song("house", tmp_path / "house")
    g = song["genre"]
    eng = host.engine
    eng.set_tempo(g.bpm)
    others = [eng.add_audio_track(p, Path(p).stem)["id"] for p in song["paths"] if not Path(p).stem.endswith("_synth")]
    tid = eng.add_synth_track("Arpegio", 0)["id"]
    eng.set_synth_settings(tid, mode=0, wave=PIANO, vel=80, bri=70, arp=3, arp_rate=2, arp_oct=2, arp_gate=60)
    bars = int(g.seconds * g.bpm / 60 // 4)
    chords = [_chord(g, g.progression[b % len(g.progression)], 4) for b in range(bars)]
    eng.set_synth_midi(tid, [(b * 4.0, 4.0, n, 90) for b, c in enumerate(chords) for n in c], bars * 4.0)
    y, sr = _render(eng, tmp_path, "house.wav")
    assert 0.05 < np.abs(y).max() <= 1.0

    for o in others:                                               # el arpegio solo, para leer sus notas
        eng.set_track_mute(o, True)
    y, sr = _render(eng, tmp_path, "solo.wav")
    step = 60 / g.bpm / 4
    misses = []
    for b, c in enumerate(chords):
        allowed = {n % 12 for n in c}
        got = _steps(y, sr, step, 16, t0=b * 16 * step)
        if any(n % 12 not in allowed for n in got) or len(set(got)) < 4:
            misses.append((b + 1, got))
    print(f"{bars} compases, {bars * 16} pasos; fallos: {misses}")
    assert not misses, f"notas fuera del acorde: {misses}"

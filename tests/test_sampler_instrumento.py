"""Sampler Pro del Instrumento (preset 11, motor C++): toca el sonido cargado en la pista, afinado nota a nota
desde su nota raíz, con inicio, bucle (fundido en la unión), ataque y liberación. Medido en el render real;
y una balada completa (batería, bajo y voces de la canción) con el piano y las cuerdas tocados por el Sampler."""
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import SAMPLER, SAMPLER_KNOBS, EngineHost, afo_audio, synth_settings

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
SR = 48000


@pytest.fixture()
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    yield h
    h.engine = None


def _knobs(**kw):
    d = dict(SAMPLER_KNOBS)
    d.update(kw)
    return [float(d[k]) for k, _ in SAMPLER_KNOBS]


def _tone(path, f0=440.0, seconds=1.0, decay=0.0, sr=SR, harmonics=(1.0,)):
    t = np.arange(int(seconds * sr)) / sr
    y = sum(a * np.sin(2 * np.pi * f0 * (k + 1) * t) for k, a in enumerate(harmonics))
    y = 0.5 * y / np.abs(y).max() * np.exp(-decay * t)
    sf.write(str(path), y.astype(np.float32), sr)
    return path


def _play(eng, tmp_path, sound, notes, name="sm.wav", **kw):
    """notes = [(inicio, duración en negras, nota)] a 120 BPM con `sound` cargado en el Sampler."""
    eng.set_tempo(120.0)
    for t in eng.tracks():
        eng.remove_track(t["id"])
    tid = eng.add_synth_track("Sampler", 0)["id"]
    assert eng.set_instrument_sample(tid, str(sound))
    eng.set_synth_settings(tid, mode=0, wave=SAMPLER, vel=100, sampler=_knobs(**kw))
    eng.set_synth_midi(tid, [(s, d, n, 100) for s, d, n in notes], max(s + d for s, d, _ in notes) + 4.0)
    out = tmp_path / name
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    return y[:, 0], sr


def _pitch(x, sr, lo=50, hi=4000):
    s = np.abs(np.fft.rfft(x * np.hanning(len(x)), 8 * len(x)))
    f = np.fft.rfftfreq(8 * len(x), 1 / sr)
    m = (f > lo) & (f < hi)
    return float(f[m][s[m].argmax()])


def _rms(y, sr, win=0.005):
    n = int(win * sr)
    return np.sqrt(np.convolve(y ** 2, np.ones(n) / n, "same"))


def test_afinado_desde_la_nota_raiz(host, tmp_path):
    eng = host.engine
    snd = _tone(tmp_path / "la.wav", 440.0, 2.0)
    got = {}
    for note in (57, 64, 69, 76, 81):
        y, sr = _play(eng, tmp_path, snd, [(0.0, 1.0, note)], smRoot=69, smAtk=0)
        got[note] = _pitch(y[int(0.05 * sr): int(0.45 * sr)], sr)
    print("raíz la4: " + ", ".join(f"nota {n} → {f:.1f} Hz" for n, f in got.items()))
    for n, f in got.items():
        assert f == pytest.approx(440 * 2 ** ((n - 69) / 12), rel=0.003)

    # Otra raíz: el mismo sonido con raíz do4 suena una sexta mayor más arriba en la misma tecla
    y, sr = _play(eng, tmp_path, snd, [(0.0, 1.0, 69)], smRoot=60, smAtk=0)
    assert _pitch(y[int(0.05 * sr): int(0.45 * sr)], sr) == pytest.approx(440 * 2 ** (9 / 12), rel=0.003)

    # Un sonido grabado a 44,1 kHz suena a su altura en el motor a otra frecuencia de muestreo
    snd44 = _tone(tmp_path / "la44.wav", 440.0, 1.0, sr=44100)
    y, sr = _play(eng, tmp_path, snd44, [(0.0, 1.0, 69)], smRoot=69, smAtk=0)
    assert _pitch(y[int(0.05 * sr): int(0.45 * sr)], sr) == pytest.approx(440, rel=0.003)


def test_inicio_bucle_y_fin_del_sonido(host, tmp_path):
    eng = host.engine
    # Sonido de 0,5 s que cae: sin bucle se acaba aunque la nota siga pulsada; con bucle sigue sonando
    snd = _tone(tmp_path / "corto.wav", 330.0, 0.5, decay=2.0)
    y, sr = _play(eng, tmp_path, snd, [(0.0, 4.0, 64)], smRoot=64, smAtk=0, smLoop=0)
    e = _rms(y, sr)
    tail_off = e[int(1.0 * sr): int(1.8 * sr)].max()
    y, sr = _play(eng, tmp_path, snd, [(0.0, 4.0, 64)], smRoot=64, smAtk=0, smLoop=1, smLoopAt=40)
    e2 = _rms(y, sr)
    tail_on = e2[int(1.0 * sr): int(1.8 * sr)]
    print(f"nota de 2 s con un sonido de 0,5 s: sin bucle {tail_off:.5f} · con bucle {tail_on.min():.4f}–{tail_on.max():.4f}")
    # el sonido cae dentro del bucle (×0,55) y el fundido de la unión baja algo el nivel: nunca se apaga
    assert tail_off < 1e-4 and tail_on.min() > 0.03 and tail_on.min() > 0.3 * tail_on.max()
    # La unión del bucle no hace clic: ningún salto entre muestras mayor que los del propio sonido
    seg = y[int(0.3 * sr): int(1.8 * sr)]
    assert np.abs(np.diff(seg)).max() < 1.5 * 0.5 * 2 * np.pi * 330 / SR + 1e-3
    # Al soltar la nota, el bucle deja de repetirse y la liberación la apaga
    assert e2[int(2.4 * sr):].max() < 1e-3

    # Inicio: con 50 % la nota arranca a media caída (más baja que desde el principio)
    y0, sr = _play(eng, tmp_path, snd, [(0.0, 0.5, 64)], smRoot=64, smAtk=0, smStart=0)
    y5, sr = _play(eng, tmp_path, snd, [(0.0, 0.5, 64)], smRoot=64, smAtk=0, smStart=50)
    a0, a5 = _rms(y0, sr)[int(0.01 * sr)], _rms(y5, sr)[int(0.01 * sr)]
    print(f"inicio 0 → 50 %: nivel al empezar {a0:.3f} → {a5:.3f} (el sonido cae ×{np.exp(-2 * 0.25):.2f} en 0,25 s)")
    assert a5 / a0 == pytest.approx(np.exp(-2 * 0.25), rel=0.1)


def test_ataque_liberacion_y_sin_sonido(host, tmp_path):
    eng = host.engine
    snd = _tone(tmp_path / "largo.wav", 220.0, 3.0)
    times = []
    for atk in (0, 60):
        y, sr = _play(eng, tmp_path, snd, [(0.0, 2.0, 57)], smRoot=57, smAtk=atk)
        e = _rms(y, sr)
        times.append(np.flatnonzero(e > 0.5 * e.max())[0] / sr)
    tails = []
    for rel in (0, 70):
        y, sr = _play(eng, tmp_path, snd, [(0.0, 2.0, 57)], smRoot=57, smAtk=0, smRel=rel)
        e = _rms(y, sr)
        tails.append(np.flatnonzero(e > e[int(0.9 * sr)] * 10 ** (-40 / 20))[-1] / sr - 1.0)
    print(f"ataque 0 → 60: mitad del nivel a {1000 * times[0]:.0f} → {1000 * times[1]:.0f} ms · "
          f"liberación 0 → 70: {1000 * tails[0]:.0f} → {1000 * tails[1]:.0f} ms tras soltarla")
    assert times[0] < 0.01 and 0.03 < times[1] < 0.09
    assert tails[0] < 0.03 and 0.25 < tails[1] < 0.6

    # Sin sonido cargado la pista no suena (no inventa uno) y escuchar una nota lo dice (False)
    eng.set_tempo(120.0)
    for t in eng.tracks():
        eng.remove_track(t["id"])
    tid = eng.add_synth_track("Vacío", 0)["id"]
    assert not eng.set_instrument_sample(tid, "")
    eng.set_synth_settings(tid, mode=0, wave=SAMPLER, vel=100, sampler=_knobs())
    eng.set_synth_midi(tid, [(0.0, 1.0, 60, 100)], 4.0)
    assert eng.render_to_wav(str(tmp_path / "vacio.wav"))
    assert np.abs(sf.read(str(tmp_path / "vacio.wav"))[0]).max() < 1e-6
    assert not eng.audition_synth(60, 0.4, mode=0, wave=SAMPLER, sampler=_knobs(), track_id=tid)
    # Con su sonido, escuchar la tecla sí suena
    assert eng.set_instrument_sample(tid, str(snd))
    assert eng.audition_synth(60, 0.4, mode=0, wave=SAMPLER, sampler=_knobs(smRoot=57), track_id=tid)
    eng.preview_stop()
    with pytest.raises(Exception):
        eng.set_instrument_sample(tid, str(tmp_path / "no_existe.wav"))


def test_ajustes_y_archivo_desde_la_pista(host, tmp_path):
    s = synth_settings({"type": "inst", "sus": False, "cfg": {"v": SAMPLER, "smRoot": 57, "smLoop": 1}})
    assert s["wave"] == SAMPLER and s["sampler"] == [57.0, 0.0, 1.0, 50.0, 2.0, 25.0]
    snd = _tone(tmp_path / "x.wav")
    tid = host.add_synth("Sampler", 0)["id"]
    track = {"type": "inst", "cfg": {"v": SAMPLER, "smpFile": str(snd)}}
    assert host.inst_sample(tid, track) == ""
    assert host.audition({**track, "id": tid, "note": 69, "seconds": 0.3})
    host.engine.preview_stop()
    gone = {"type": "inst", "cfg": {"v": SAMPLER, "smpFile": str(tmp_path / "borrado.wav")}}
    assert host.inst_sample(tid, gone) == str(tmp_path / "borrado.wav")     # se avisa, y la pista calla


def test_balada_completa_con_piano_y_cuerdas_sampleados(host, tmp_path):
    """Una balada entera (batería, bajo y voces de la canción) en la que el piano y las cuerdas son dos
    notas sueltas sampleadas: un do4 de piano (cae) y un sol3 de cuerdas en bucle. En cada compás el
    acorde suena con sus fundamentales, y las cuerdas aguantan el compás entero gracias al bucle."""
    from song_factory import _chord, write_song
    song = write_song("balada", tmp_path / "balada")
    g = song["genre"]
    eng = host.engine
    eng.set_tempo(g.bpm)
    others = [eng.add_audio_track(p, Path(p).stem)["id"] for p in song["paths"]
              if not any(Path(p).stem.endswith(s) for s in ("_piano", "_pad"))]
    bars = int(g.seconds * g.bpm / 60 // 4)
    chords = [_chord(g, g.progression[b % len(g.progression)], 4) for b in range(bars)]
    piano_snd = _tone(tmp_path / "piano_do4.wav", 261.63, 2.5, decay=1.5, harmonics=(1, 0.5, 0.3, 0.15, 0.1))
    str_snd = _tone(tmp_path / "cuerdas_sol3.wav", 196.0, 0.8, harmonics=(1, 0.6, 0.4, 0.3, 0.2, 0.1))
    piano = eng.add_synth_track("Piano sampleado", 0)["id"]
    assert eng.set_instrument_sample(piano, str(piano_snd))
    eng.set_synth_settings(piano, mode=0, wave=SAMPLER, vel=90, sampler=_knobs(smRoot=60, smRel=30))
    eng.set_synth_midi(piano, [(b * 4.0 + k * 2.0, 1.9, n, 90) for b, c in enumerate(chords) for k in (0, 1) for n in c],
                       bars * 4.0)
    strings = eng.add_synth_track("Cuerdas sampleadas", 0)["id"]
    assert eng.set_instrument_sample(strings, str(str_snd))
    eng.set_synth_settings(strings, mode=0, wave=SAMPLER, vel=60,
                           sampler=_knobs(smRoot=55, smLoop=1, smLoopAt=30, smAtk=45, smRel=55))
    eng.set_synth_midi(strings, [(b * 4.0, 3.9, n - 12, 70) for b, c in enumerate(chords) for n in c], bars * 4.0)
    assert eng.render_to_wav(str(tmp_path / "mix.wav"))
    y, sr = sf.read(str(tmp_path / "mix.wav"))
    assert 0.05 < np.abs(y).max() <= 1.0

    beat = 60 / g.bpm

    def fund(w, notes):
        s = np.abs(np.fft.rfft(w * np.hanning(len(w)), 2 * len(w)))
        f = np.fft.rfftfreq(2 * len(w), 1 / sr)
        return {n: s[np.abs(f / (440 * 2 ** ((n - 69) / 12)) - 1) < 0.012].max() for n in notes}

    for o in others + [strings]:
        eng.set_track_mute(o, True)
    assert eng.render_to_wav(str(tmp_path / "piano.wav"))
    y = sf.read(str(tmp_path / "piano.wav"))[0][:, 0]
    misses = []
    for b, c in enumerate(chords):
        t0 = b * 4 * beat
        e = fund(y[int((t0 + 0.1 * beat) * sr): int((t0 + 1.8 * beat) * sr)], range(min(c) - 5, max(c) + 3))
        top = sorted(e, key=e.get)[::-1][:3]
        print(f"piano, compás {b + 1}: {sorted(c)} → {sorted(top)}")
        if {n % 12 for n in top} - {n % 12 for n in c}:
            misses.append(b + 1)
    assert not misses, f"piano fuera de tono en los compases {misses}"

    eng.set_track_mute(piano, True)
    eng.set_track_mute(strings, False)
    assert eng.render_to_wav(str(tmp_path / "cuerdas.wav"))
    y = sf.read(str(tmp_path / "cuerdas.wav"))[0][:, 0]
    e = _rms(y, sr, 0.05)
    short = []
    for b, c in enumerate(chords):
        t0 = b * 4 * beat
        late = e[int((t0 + 3.5 * beat) * sr)]            # el sonido dura 0,8 s; el compás, más de 3 s
        top = fund(y[int((t0 + 1.0 * beat) * sr): int((t0 + 3.6 * beat) * sr)], [n - 12 for n in c] + [n - 13 for n in c])
        best = sorted(top, key=top.get)[::-1][:3]
        print(f"cuerdas, compás {b + 1}: nivel al final del compás {late:.3f}; notas {sorted(best)} (acorde {sorted(n - 12 for n in c)})")
        if late < 0.02 or set(best) != {n - 12 for n in c}:
            short.append(b + 1)
    assert not short, f"cuerdas cortadas o fuera de tono en los compases {short}"

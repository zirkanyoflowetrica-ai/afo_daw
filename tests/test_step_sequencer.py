"""Step Sequencer de la Batería (motor C++, `synth::expandSteps`): fuerza, probabilidad y repeticiones
por paso, largo propio de cada pad (polimetría) y semilla de la variación. Un patrón de pasos sin
nada de eso suena igual que antes; lo demás se mide en el render real, y con un house completo."""
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import FIRST_DRUM_NOTE, STEPS, EngineHost, afo_audio, pattern_notes, step_pattern

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")

KICK, SNARE, HAT, OPEN, CLAP, TOM, CYM, BELL = range(8)


@pytest.fixture()
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    yield h
    h.engine = None


def _track(pat, clips=None, **cfg):
    return {"type": "drum", "clips": clips or [[0, 100]], "pat": pat, "cfg": {"vol": 70, "tun": 50, **cfg}}


def _expand(track):
    return afo_audio.expand_steps(**step_pattern(track))


def _render(host, tmp_path, track, name="steps.wav", bpm=120.0):
    eng = host.engine
    eng.set_tempo(bpm)
    for t in eng.tracks():
        eng.remove_track(t["id"])
    host.tracks.clear()
    tid = host.add_synth("Batería", 1)["id"]
    host.update_synth(tid, track)
    out = tmp_path / name
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    return y[:, 0], sr


def _band(x, sr, f, kind):
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(4, f, kind, fs=sr, output="sos"), x)


def test_un_patron_normal_suena_igual_que_antes():
    """Pasos encendidos «1», swing y clips: las mismas notas que la rejilla de siempre (pattern_notes)."""
    pat = {f"{l}-{s}": 1 for l, s in [(0, 0), (0, 6), (0, 8), (1, 4), (1, 12), (2, 3), (2, 7), (2, 15), (7, 9)]}
    for sw, clips in [(0, [[0, 100]]), (60, [[0, 25], [50, 31.25]])]:
        t = _track(pat, clips, sw=sw)
        old = sorted(pattern_notes(t))
        new = sorted((round(b, 9), n) for b, d, n, v in _expand(t))
        assert new == [(round(b, 9), n) for b, n in old] and len(new) > 0
        assert all(v == 100 and d == 0.25 for b, d, n, v in _expand(t))


def test_fuerza_del_paso(host, tmp_path):
    peaks = {}
    for vel in (100, 127, 60):
        v = 1 if vel == 100 else [vel, 100, 1]
        y, sr = _render(host, tmp_path, _track({"0-0": v}, [[0, 6.25]], vol=40))
        peaks[vel] = np.abs(y).max()
    print(f"bombo: fuerte ×{peaks[127] / peaks[100]:.3f} (1,27), suave ×{peaks[60] / peaks[100]:.3f} (0,60)")
    assert peaks[127] / peaks[100] == pytest.approx(1.27, rel=0.02)
    assert peaks[60] / peaks[100] == pytest.approx(0.60, rel=0.02)


def test_repeticiones_dentro_del_paso(host, tmp_path):
    t = _track({"2-4": [100, 100, 3]}, [[0, 6.25]])
    notes = _expand(t)
    assert [(round(b, 6), round(d, 6)) for b, d, n, v in notes] == [(1.0, 0.083333), (1.083333, 0.083333), (1.166667, 0.083333)]
    y, sr = _render(host, tmp_path, t)
    env = np.abs(_band(y, sr, 4000, "highpass"))
    beat = 0.5                                                   # 120 BPM
    hits = []
    for k in range(3):
        t0 = int((1.0 + k / 12) * beat * sr)
        hits.append(env[t0:t0 + int(0.006 * sr)].max())
    gap = env[int((1.0 + 3 / 12) * beat * sr) + int(0.06 * sr): int(2.0 * beat * sr)].max()
    print(f"hi-hat ×3 en una semicorchea: golpes {[round(h, 3) for h in hits]}, después {gap:.4f}")
    assert all(h > 0.05 for h in hits) and gap < 0.2 * min(hits)


def test_probabilidad_con_semilla():
    pat = {f"2-{s}": [100, 50, 1] for s in range(16)}
    a = _expand(_track(pat, seed=0))
    b = _expand(_track(pat, seed=0))
    c = _expand(_track(pat, seed=1))
    full = _expand(_track({f"2-{s}": 1 for s in range(16)}))
    print(f"hi-hat al 50 %: {len(a)} de {len(full)} semicorcheas; otra semilla {len(c)}, "
          f"{sum(x != y for x, y in zip(a, c))} cambian de sitio")
    assert a == b, "la misma semilla da las mismas notas"
    assert a != c, "otra variación cambia dónde suenan"
    assert len(full) == STEPS and 0.4 < len(a) / STEPS < 0.6 and 0.4 < len(c) / STEPS < 0.6
    assert _expand(_track({"2-3": [100, 25, 1]}, [[0, 100]])) and not _expand(_track({"2-3": [100, 0, 1]}))


def test_largo_por_pad_polimetria():
    """Bombo de 16 pasos, cencerro de 3: el cencerro cae en otra semicorchea en cada compás."""
    t = _track({"0-0": 1, "7-0": 1, "7-5": 1}, len=[16, 16, 16, 16, 16, 16, 16, 3])
    bell = [round(b * 4) for b, d, n, v in _expand(t) if n == FIRST_DRUM_NOTE + BELL]
    kick = [round(b * 4) for b, d, n, v in _expand(t) if n == FIRST_DRUM_NOTE + KICK]
    assert bell == list(range(0, STEPS, 3)), "el paso 5 cae fuera del largo (3) y no suena"
    assert kick == list(range(0, STEPS, 16))
    print(f"cencerro de 3 pasos: primer golpe de cada compás en {[next(s % 16 for s in bell if s >= 16 * b) for b in range(4)]}")


def test_house_completo_con_step_sequencer(host, tmp_path):
    """Un house entero (bajo, acordes, voces) con la batería del Step Sequencer: bombo a negras con el
    primero de cada compás fuerte, caja en 2 y 4 con un redoble suave ×4 justo antes de la del 4,
    hi-hats en las semicorcheas impares al 50 % y cencerro con su propio largo de 3 pasos."""
    from song_factory import write_song
    song = write_song("house", tmp_path / "house")
    g = song["genre"]
    eng = host.engine
    eng.set_tempo(g.bpm)
    for t in eng.tracks():
        eng.remove_track(t["id"])
    host.tracks.clear()
    others = [eng.add_audio_track(p, Path(p).stem)["id"] for p in song["paths"]
              if Path(p).stem.split("_", 1)[1] not in ("Kick", "Clap", "HiHat", "Snare", "Drums")]
    pat = {"0-0": [127, 100, 1], "0-4": 1, "0-8": 1, "0-12": 1, "1-4": 1, "1-12": 1, "1-11": [60, 100, 4]}
    pat.update({f"2-{s}": [100, 50, 1] for s in range(1, 16, 2)})
    pat["7-0"] = [60, 100, 1]
    bars = int(g.seconds * g.bpm / 60 // 4)
    track = _track(pat, [[0, 6.25 * bars]], seed=7, len=[16, 16, 16, 16, 16, 16, 16, 3])
    tid = host.add_synth("Step Sequencer", 1)["id"]
    host.update_synth(tid, track)
    assert eng.render_to_wav(str(tmp_path / "mix.wav"))
    y, sr = sf.read(str(tmp_path / "mix.wav"))
    assert 0.05 < np.abs(y).max() <= 1.0

    for o in others:
        eng.set_track_mute(o, True)
    assert eng.render_to_wav(str(tmp_path / "drums.wav"))
    d, sr = sf.read(str(tmp_path / "drums.wav"))
    d = d[:, 0]
    notes = _expand(track)
    beat = 60 / g.bpm
    step = beat / 4
    hat_on = {round(b * 4) for b, _, n, _ in notes if n == FIRST_DRUM_NOTE + HAT}
    hf = np.abs(_band(d, sr, 7000, "highpass"))
    on_lvl, off_lvl = [], []
    for st in range(bars * 16):
        if st % 2 == 0 or st % 16 == 11:                     # hi-hats solo en las impares (la 11 lleva el redoble)
            continue
        w = hf[int(st * step * sr): int((st * step + 0.02) * sr)].max()
        (on_lvl if st in hat_on else off_lvl).append(w)
    thr = 0.5 * np.median(on_lvl)
    wrong = sum(w < thr for w in on_lvl) + sum(w >= thr for w in off_lvl)
    # ataque del bombo del 1 frente al del 3, que suena solo (en el 2 y el 4 cae también la caja); sin los
    # compases en que el cencerro de 3 pasos cae encima
    clean = [b for b in range(bars) if (b * 16) % 3 and (b * 16 + 8) % 3]
    hit = lambda t0: np.abs(d[int(t0 * sr): int((t0 + 0.03) * sr)]).max()    # noqa: E731
    acc = np.median([hit(b * 4 * beat) / hit((b * 4 + 2) * beat) for b in clean])
    roll = [1 for b, d_, n, v in notes if n == FIRST_DRUM_NOTE + SNARE and v == 60]
    print(f"{bars} compases a {g.bpm:.0f} BPM: hi-hats {len(on_lvl)} suenan / {len(off_lvl)} callan "
          f"(50 %), {wrong} fuera de sitio; bombo del 1 ×{acc:.2f} (fuerte 127/100); redoble {len(roll)} golpes")
    assert 0.3 < len(on_lvl) / (len(on_lvl) + len(off_lvl)) < 0.7
    assert wrong == 0, "cada hi-hat suena justo donde el motor lo decidió"
    assert acc == pytest.approx(1.27, rel=0.05)      # suelto da 1,269 (test_fuerza_del_paso); aquí suman las colas de otros golpes
    assert len(roll) == 4 * bars

"""F7: análisis del proyecto (Python): tonalidad, acordes y secciones de canciones completas.

Proyectos de `song_factory` de 4 géneros (batería, bajo o 808, armonía y voces desafinadas, mezclados
como suenan en el proyecto). La verdad sale de cómo se escribió cada canción: su tonalidad y su
progresión de acordes por compás. Para las secciones se monta una canción A-B-A-B (A sin batería ni
bajo, B completa) y se comprueba que las fronteras y las letras caen en su sitio.
"""
import dataclasses

import numpy as np
import pytest
import soundfile as sf
from scipy.signal import resample_poly

import song_factory as F
from allforone import analysis as A

GENEROS = ["trap", "balada", "rock", "regueton"]
RITMO = {"Kick", "Clap", "HiHat", "Snare", "Bateria", "808", "Bajo"}


def _verdad(g, t):
    """Acorde que suena en el segundo t según la progresión de la canción (fundamental, calidad)."""
    bar = 4 * 60 / g.bpm
    ch = F._chord(g, g.progression[int(t / bar) % len(g.progression)], 4)
    return ch[0] % 12, "min" if (ch[1] - ch[0]) % 12 == 3 else "maj"


def _cancion(genre, tmp_path):
    s = F.write_song(genre, tmp_path / genre)
    xs = [sf.read(p, dtype="float32")[0] for p in s["paths"]]
    p = tmp_path / f"{genre}.wav"
    sf.write(str(p), sum(xs) / len(xs), F.SR)
    return str(p), s["genre"]


@pytest.mark.parametrize("genre", GENEROS)
def test_tonalidad_y_acordes(genre, tmp_path):
    path, g = _cancion(genre, tmp_path)
    r = A.analyze_mix(A.read_mono(path), g.bpm * 1.05)
    assert (r["key"]["key"], r["key"]["scale"]) == (g.key, g.scale), r["key"]
    assert abs(r["tempo"]["bpm"] - g.bpm) < 0.1
    ok = tot = 0
    for c in r["chords"]:
        for t in np.arange(c["start"], c["end"], 0.05):
            tot += 1
            ok += _verdad(g, t) == (c["root"], c["quality"])
    cubre = sum(c["end"] - c["start"] for c in r["chords"]) / g.seconds
    names = [c["name"] for c in r["chords"]]
    print(genre, f"{100 * ok / tot:.0f} %", names)
    assert cubre > 0.95 and ok / tot >= 0.85, (ok / tot, names)
    # los cambios de acorde caen en las barras de compás (± medio pulso)
    bar, beat = 4 * 60 / g.bpm, 60 / g.bpm
    for c in r["chords"][1:]:
        assert abs(c["start"] / bar - round(c["start"] / bar)) * bar < beat / 2, (c, names)
    assert all(c["name_es"] for c in r["chords"]) and r["chords"][0]["name_es"] == A.chord_name(*_verdad(g, 0.1), es=True)


def _con_secciones(genre, plan):
    g0 = F.TODOS[genre]
    bar = 4 * 60 / g0.bpm
    g = dataclasses.replace(g0, seconds=sum(n for n, _ in plan) * bar)
    F.TODOS["_secciones"] = g                    # la melodía busca su género en TODOS
    try:
        n = int(g.seconds * F.SR)
        stems = {**F.drums(g, n, set(g.parts)), **F.tonal(g, n, set(g.parts))}
        vox = sum(F.voice_track(g, v, n)[0] for v in g.voices)
    finally:
        del F.TODOS["_secciones"]
    mix, at, truth = np.zeros(n), 0, []
    for nb, kind in plan:
        a, b = int(at * bar * F.SR), int((at + nb) * bar * F.SR)
        for name, x in stems.items():
            if kind == "A" and name in RITMO:
                continue
            mix[a:b] += x[a:b]
        mix[a:b] += vox[a:b] * (0.6 if kind == "A" else 1.0)
        truth.append((at * bar, kind))
        at += nb
    return resample_poly(mix, 1, 2).astype(np.float32), g, truth


@pytest.mark.parametrize("genre", GENEROS)
def test_secciones(genre):
    y, g, truth = _con_secciones(genre, [(4, "A"), (8, "B"), (4, "A"), (8, "B")])
    r = A.analyze_mix(y, g.bpm)
    got = [(s["start"], s["label"]) for s in r["sections"]]
    assert len(got) == len(truth), (got, truth)
    for (t0, k0), (t1, k1) in zip(truth, got):
        assert abs(t0 - t1) < 60 / g.bpm / 2 and k0 == k1, (got, truth)


def test_mezcla_de_clips_en_su_sitio(tmp_path):
    """Los clips se suman donde suenan: desplazamiento en el archivo, posición y estiramiento."""
    sr = 44100
    t = np.arange(sr * 2) / sr
    x = np.where(t < 1, np.sin(2 * np.pi * 220 * t), np.sin(2 * np.pi * 440 * t)).astype("float32")
    p = tmp_path / "dos.wav"
    sf.write(str(p), x, sr)
    # segundo 1-2 del archivo (440 Hz) puesto en el segundo 3, y el archivo entero estirado al doble en el 5
    y = A.mix_clips([(str(p), 3.0, 1.0, 1.0, 1.0, 0.0), (str(p), 5.0, 0.0, 2.0, 4.0, -6.0)])
    assert abs(y.size / A.SR - 9.0) < 0.01
    assert np.max(np.abs(y[: int(2.9 * A.SR)])) < 1e-3                      # antes del clip, silencio

    def freq(a, b):
        seg = y[int(a * A.SR):int(b * A.SR)]
        f = np.fft.rfftfreq(seg.size, 1 / A.SR)
        return f[np.argmax(np.abs(np.fft.rfft(seg)))]
    assert abs(freq(3.1, 3.9) - 440) < 3
    assert abs(freq(5.2, 6.8) - 110) < 3        # 220 Hz estirado al doble de largo (sin conservar el tono)
    assert abs(freq(7.2, 8.8) - 220) < 3

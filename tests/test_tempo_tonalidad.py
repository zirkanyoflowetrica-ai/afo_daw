"""F11: detectar tempo y tonalidad de un audio importado y acomodarlo al proyecto (o al revés).

Proyectos completos de `song_factory` (8 géneros, voces y sus instrumentos mezclados en un solo
archivo, como una canción importada): el análisis da su tempo y su tonalidad, y el motor (SoundTouch
en C++) estira y transpone el clip; se mide en el render real.
"""
import numpy as np
import pytest
import soundfile as sf

import song_factory as F
from allforone import analysis as A
from allforone.engine_host import EngineHost, afo_audio


def _mix(genre, tmp_path):
    s = F.write_song(genre, tmp_path / genre)
    xs = [sf.read(p, dtype="float32")[0] for p in s["paths"]]
    mix = sum(xs) / len(xs)
    p = tmp_path / f"{genre}_cancion.wav"
    sf.write(str(p), mix, F.SR)
    return str(p), s["genre"]


def test_detecta_tempo_y_tonalidad_en_8_generos(tmp_path):
    ok_key, out = 0, []
    for g in F.TODOS:
        path, G = _mix(g, tmp_path)
        r = A.analyze_file(path, near_bpm=G.bpm * 1.08)          # proyecto a un tempo parecido
        out.append((g, G.bpm, r["tempo"]["bpm"], G.key + " " + G.scale, r["key"]["key"] + " " + r["key"]["scale"]))
        assert abs(r["tempo"]["bpm"] - G.bpm) < 0.1, out[-1]
        # medio o doble tiempo sin referencia: siempre una lectura del mismo pulso
        raw = r["tempo"]["raw"]
        assert min(abs(raw - G.bpm * k) for k in (0.5, 1, 2)) < 0.1, out[-1]
        ok_key += (r["key"]["key"], r["key"]["scale"]) == (G.key, G.scale)
        # para transponer basta el relativo: La menor y Do mayor son las mismas notas
        assert A.semitones_between(r["key"]["key"], r["key"]["scale"], G.key, G.scale) in (0, 5, -5), out[-1]
    assert ok_key >= 7, out
    print(out)


def test_semitonos_entre_tonalidades():
    assert A.semitones_between("A", "Menor natural", "C", "Mayor") == 0
    assert A.semitones_between("C", "Mayor", "D", "Mayor") == 2
    assert A.semitones_between("C", "Mayor", "A#", "Mayor") == -2
    assert A.semitones_between("E", "Menor natural", "A", "Menor natural") == 5
    assert A.semitones_between("F", "Mayor", "B", "Mayor") == -6
    assert A.key_name("F#", "Menor natural") == "Fa# menor"


@pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
@pytest.mark.parametrize("genre,target_bpm,semis", [("balada", 80.0, 2), ("rock", 110.0, -3)])
def test_audio_al_tempo_y_tono_del_proyecto(tmp_path, genre, target_bpm, semis):
    path, G = _mix(genre, tmp_path)
    h = EngineHost.create()
    assert h.ok, h.error
    try:
        eng = h.engine
        info = h.add_audio(path, convert=False)
        tid = info["id"]
        c = eng.clips(tid)[0]
        src_len = c["length"]
        speed = target_bpm / G.bpm
        r = eng.set_clip_stretch(c["id"], speed, float(semis))
        assert abs(r["speed"] - speed) < 1e-6 and abs(r["semitones"] - semis) < 1e-4
        assert abs(r["length"] - src_len / speed) < 0.02, (r["length"], src_len / speed)
        eng.set_tempo(target_bpm)
        out = tmp_path / "estirado.wav"
        assert eng.render_to_wav(str(out))
        y, sr = sf.read(str(out), dtype="float32")
        y = y.mean(axis=1) if y.ndim > 1 else y
        y = y[: int(r["length"] * sr)]
        from scipy.signal import resample_poly
        import math
        g = math.gcd(A.SR, sr)
        y = resample_poly(y, A.SR // g, sr // g).astype(np.float32)
        t = A.detect_tempo(y, near=target_bpm)
        k = A.detect_key(y)
        assert abs(t["bpm"] - target_bpm) < 0.6, t
        want = F.NOTES[(G.tonic + semis) % 12]
        assert A.semitones_between(want, G.scale, k["key"], k["scale"]) == 0, (k, want, G.scale)
        # deshacer: los clips vuelven con su velocidad y tono, y la pista vuelve a su duración
        eng.set_clips(tid, [{**c, "speed": 1.0, "semitones": 0.0}])
        back = eng.clips(tid)[0]
        assert abs(back["length"] - src_len) < 0.02 and back["speed"] == 1.0 and back["semitones"] == 0.0
        # duplicar y dividir conservan la velocidad
        eng.set_clip_stretch(back["id"], speed, 0.0)
        d = eng.duplicate_clip(back["id"])
        assert abs(d["speed"] - speed) < 1e-6
        parts = eng.split_clip(back["id"], 3.0)
        assert all(abs(p["speed"] - speed) < 1e-6 for p in parts)
    finally:
        h.engine = None


def test_transponer_instrumentos_no_bateria():
    from allforone.engine_host import pattern_notes, transpose_of
    inst = {"type": "inst", "cfg": {"tr": 3}, "roll": {"12-0": 1}, "clips": [[0, 100]]}
    base = {"type": "inst", "cfg": {}, "roll": {"12-0": 1}, "clips": [[0, 100]]}
    a, b = pattern_notes(inst), pattern_notes(base)
    assert a and [n + 3 for _, n in b] == [n for _, n in a]
    assert transpose_of({"type": "drum", "cfg": {"tr": 5}}) == 0

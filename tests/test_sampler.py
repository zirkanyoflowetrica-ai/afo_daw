"""Sampler de la Batería (C10): los pads suenan con golpes grabados, con PROYECTOS COMPLETOS.

De cada canción de song_factory (hip-hop, trap, house, rock) se cortan sus golpes reales (bombo,
caja, hi-hat) con `lab.cut_hit`, como hace el Instrumental Lab, y se cargan en los pads de una pista
de Batería al tempo del género. Se comprueba con el render del motor:
  * el patrón suena como la suma de los golpes colocados en sus pasos (r > 0,95);
  * Volumen escala el golpe y Afinación cambia la velocidad de lectura (al 100 %, la mitad de largo);
  * un carril sin golpe sigue con el sonido sintetizado; quitar los golpes devuelve el sintetizado;
  * un archivo que ya no existe no rompe la pista: vuelve al sintetizado y se avisa;
  * escuchar un pad (audition) usa el golpe de esa pista."""
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import song_factory as F
from allforone import lab as L
from allforone.engine_host import FIRST_DRUM_NOTE, EngineHost, afo_audio, pattern_notes

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
SR = 44100
LANES = {0: ("Kick", "808", "Drums"), 1: ("Snare", "Clap"), 2: ("HiHat",)}
PAT = {**{f"0-{s}": 1 for s in (0, 6, 8, 11)}, "1-4": 1, "1-12": 1, **{f"2-{s}": 1 for s in range(2, 16, 4)}}


@pytest.fixture(scope="module")
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    yield h
    h.engine = None


def _hits(genre: str, folder: Path) -> dict[int, Path]:
    song = F.write_song(genre, folder)
    by = {p.split(f"{genre.capitalize()}_", 1)[1][:-4]: p for p in song["paths"]}
    out = {}
    for lane, names in LANES.items():
        name = next((n for n in names if n in by), None)
        if name is None:
            continue
        hit = L.cut_hit(sf.read(by[name], always_2d=True, dtype="float32")[0])
        if hit is not None:
            out[lane] = folder / f"golpe_{lane}.wav"
            sf.write(out[lane], hit, SR, subtype="FLOAT")
    return out


def _render(h, path: Path, seconds: float) -> np.ndarray:
    assert h.engine.render_to_wav(str(path))
    y, sr = sf.read(str(path), always_2d=True, dtype="float32")
    if sr != SR:
        from scipy.signal import resample_poly
        y = resample_poly(y, SR, sr, axis=0).astype("float32")
    return y[: int(seconds * SR), 0]


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    n = min(len(a), len(b))
    c = np.correlate(a[:n], b[:n], "full")[n - 1 - 64:n + 64]
    lag = int(np.argmax(c)) - 64
    a = a[lag:] if lag >= 0 else np.pad(a, (-lag, 0))
    m = min(len(a), len(b))
    return float(np.corrcoef(a[:m], b[:m])[0, 1])


def _expected(hits: dict[int, Path], bpm: float, seconds: float, vol: float, pat: dict | None = None) -> np.ndarray:
    out = np.zeros(int(seconds * SR) + SR, dtype="float32")
    for beat, note in pattern_notes({"type": "drum", "clips": [[0, 100]], "pat": pat or PAT}):
        lane = note - FIRST_DRUM_NOTE
        at = int(round(beat * 60 / bpm * SR))
        if lane in hits and at < len(out):
            x = sf.read(hits[lane], dtype="float32")[0].mean(axis=1) * vol / 100
            out[at:at + len(x)] += x[: len(out) - at]
    return out[: int(seconds * SR)]


@pytest.mark.parametrize("genre", ["hiphop", "trap", "house", "rock"])
def test_pads_con_golpes_de_la_cancion(genre, host, tmp_path):
    g = F.TODOS[genre]
    hits = _hits(genre, tmp_path)
    # hip-hop y rock traen la batería en una pista: de ahí sale un golpe (el más fuerte) para el bombo
    assert 0 in hits, f"{genre}: sin golpe que cortar ({sorted(hits)})"
    eng = host.engine
    eng.set_tempo(float(g.bpm))
    tid = host.add_synth("Batería", 1)["id"]
    try:
        smp = [str(hits.get(i, "")) for i in range(8)]
        pat = {k: 1 for k in PAT if int(k.split("-")[0]) in hits}     # solo los carriles con golpe grabado
        track = {"type": "drum", "clips": [[0, 100]], "pat": pat, "cfg": {"vol": 40, "tun": 50, "sw": 0, "smp": smp}}
        host.update_synth(tid, track)
        secs = 2 * 240 / g.bpm                                     # dos compases
        r1 = _corr(_render(host, tmp_path / "r1.wav", secs), _expected(hits, g.bpm, secs, 40, pat))

        # Volumen: el doble de volumen, el doble de nivel
        y40 = _render(host, tmp_path / "r40.wav", secs)
        host.update_synth(tid, {**track, "settingsOnly": True, "cfg": {**track["cfg"], "vol": 80}})
        y80 = _render(host, tmp_path / "r80.wav", secs)
        gain = float(np.sqrt(np.mean(y80 ** 2) / np.mean(y40 ** 2)))

        # Afinación al 100 %: el golpe dura la mitad (lectura al doble de velocidad)
        one = {"type": "drum", "clips": [[0, 100]], "pat": {"0-0": 1}, "cfg": {"vol": 80, "tun": 50, "sw": 0, "smp": smp}}
        host.update_synth(tid, one)
        e50 = _render(host, tmp_path / "t50.wav", 1.5)
        host.update_synth(tid, {**one, "cfg": {**one["cfg"], "tun": 100}})
        e100 = _render(host, tmp_path / "t100.wav", 1.5)

        def dur(y):
            env = np.abs(y) > 0.02 * np.abs(y).max()
            return (len(env) - int(np.argmax(env[::-1]))) - int(np.argmax(env))
        ratio = dur(e100) / dur(e50)

        # Escuchar un pad usa el golpe grabado de esa pista
        assert host.audition({"type": "drum", "cfg": one["cfg"], "lane": 0, "id": tid})

        # Sin golpes: vuelve el sonido sintetizado (un bombo con barrido, no la grabación)
        host.update_synth(tid, {**one, "cfg": {**one["cfg"], "tun": 50, "smp": []}})
        synth = _render(host, tmp_path / "s.wav", 1.5)
        rs = _corr(synth, _expected({0: hits[0]}, g.bpm, 1.5, 80, {"0-0": 1}))

        # Un golpe que ya no existe: la pista sigue, ese pad vuelve al sintetizado y se avisa
        gone = tmp_path / "borrado.wav"
        sf.write(gone, np.zeros((100, 1), "float32"), SR)
        gone.unlink()
        missing = host.drum_samples(tid, {"cfg": {"smp": [str(gone)]}})
        print(f"{genre} ({g.bpm} BPM): patrón con golpes r={r1:.3f}; volumen ×2 → nivel ×{gain:.2f}; "
              f"afinación 100 % → duración ×{ratio:.2f}; sintetizado vs grabado r={rs:.2f}")
        assert r1 > 0.95
        assert 1.8 < gain < 2.2
        assert 0.4 < ratio < 0.6
        assert rs < 0.9, "sin golpes no debe sonar la grabación"
        assert missing == [str(gone)]
    finally:
        host.engine.remove_track(tid)
        host.tracks.pop(tid, None)


def test_golpes_del_laboratorio_a_los_carriles(tmp_path, monkeypatch):
    """lab.hit_lanes: Bombo → Bombo, Caja / Clap → Caja, Platos → Platillo."""
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    lab = L.Lab(lambda e: None, lambda: False)
    lab.new({"style": "Libre", "bpm": 90, "bars": 2, "families": ["Batería"]})
    lab.state["oneshots"] = {"from": "v1", "family": "Batería",
                             "hits": {"Bombo": "golpes/bombo_v1.wav", "Caja / Clap": "golpes/caja_v1.wav", "Platos": "golpes/platos_v1.wav"}}
    lanes = lab.hit_lanes()
    assert [Path(p).name if p else "" for p in lanes] == ["bombo_v1.wav", "caja_v1.wav", "", "", "", "", "platos_v1.wav", ""]
    lab.shutdown()
    json.dumps(lanes)

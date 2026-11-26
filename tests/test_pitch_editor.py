"""Pitch Editor (AF-64) en el motor C++: las notas de una voz, movidas una a una.

Con PROYECTOS COMPLETOS (la voz de la balada de song_factory, que trae su partitura: inicio, fin, nota
y desafinación de cada nota, con entrada desde abajo y vibrato que entra tarde). El análisis encuentra
las notas donde están y con su tono; sin cambios la toma sale idéntica; una nota movida suena donde se
pidió (medido con pYIN de librosa, un detector distinto del del motor) y las demás no cambian;
el tiempo no se mueve; «enderezar» quita el vibrato sin mover el centro. Por el puente: analizar y
aplicar corren en su hilo, la pista pasa a la copia con los mismos clips y, sin cambios, vuelve a la
toma analizada.
"""
import json
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy.ndimage import uniform_filter1d

from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")


@pytest.fixture(scope="module")
def balada(tmp_path_factory):
    from song_factory import write_song
    song = write_song("balada", tmp_path_factory.mktemp("balada"))
    p = next(p for p in song["paths"] if Path(p).stem.endswith("Voz_Lead"))
    a = afo_audio.pitch_analyze(p)
    assert a["ok"], a["error"]
    return p, song["truth"]["Voz_Lead"], a


def _pyin(path, t0, t1):
    """Mediana del tono (MIDI) entre t0 y t1 s con pYIN (librosa), independiente del motor."""
    import librosa
    y, sr = sf.read(path, always_2d=True)
    seg = y[int(t0 * sr):int(t1 * sr), 0]
    f0, voiced, _ = librosa.pyin(seg, fmin=80, fmax=1000, sr=sr, frame_length=2048, hop_length=256, resolution=0.01)
    f = f0[voiced & np.isfinite(f0)]
    assert len(f) >= 5, (t0, t1)
    return float(np.median(librosa.hz_to_midi(f))), librosa.hz_to_midi(f)


def _match(notes, t0, t1):
    """Nota detectada que más se solapa con [t0, t1]."""
    best, ov = None, 0.0
    for n in notes:
        o = min(t1, n["end"]) - max(t0, n["start"])
        if o > ov:
            best, ov = n, o
    return best, ov


def test_encuentra_las_notas_de_la_partitura(balada):
    """Cada nota cantada sale en el análisis: con su inicio (±60 ms) y su tono (nota + desafinación,
    ±25 cents: la mediana no se deja llevar por la entrada desde abajo ni por el vibrato)."""
    p, truth, a = balada
    assert abs(a["hop"] - 0.01) < 1e-9 and abs(a["seconds"] - sf.info(p).duration) < 0.01
    found, on_time, in_tune = 0, 0, []
    for t0, t1, m, cents in truth:
        n, ov = _match(a["notes"], t0, t1)
        if n is None or ov < 0.5 * (t1 - t0):
            continue
        found += 1
        on_time += abs(n["start"] - t0) < 0.06
        in_tune.append(abs(n["midi"] - (m + cents / 100)) * 100)
    print(f"{len(truth)} notas en la partitura, {len(a['notes'])} detectadas; encontradas {found}, "
          f"a tiempo {on_time}; error de tono mediano {np.median(in_tune):.1f} cents (máx. {max(in_tune):.1f})")
    assert found >= 0.9 * len(truth) and on_time >= 0.85 * found
    assert np.median(in_tune) < 10 and np.mean(np.array(in_tune) < 25) >= 0.9
    assert len(a["notes"]) <= 1.3 * len(truth)                  # sin trocear las notas por el vibrato
    assert all(n["shift"] == 0 and n["flatten"] == 0 for n in a["notes"])


def test_sin_cambios_la_toma_sale_identica(balada, tmp_path):
    p, _, a = balada
    out = tmp_path / "igual.wav"
    assert afo_audio.pitch_edit(p, str(out), a["notes"]) == ""
    x, sr = sf.read(p, always_2d=True)
    y, sr2 = sf.read(str(out), always_2d=True)
    assert sr == sr2 and y.shape == x.shape and np.max(np.abs(y - x)) < 1e-6


def test_mueve_cada_nota_donde_se_pide(balada, tmp_path):
    """Cuatro notas movidas (+2, −1, +0,5 y −3 semitonos): pYIN las oye a ±8 cents de lo pedido; las
    notas no tocadas no cambian de tono, y lejos de lo editado el audio es el mismo muestra a muestra."""
    p, _, a = balada
    notes = [dict(n) for n in a["notes"]]
    long_ = [i for i, n in enumerate(notes) if n["end"] - n["start"] >= 0.5]
    picks = dict(zip(long_[1::2][:4], [2.0, -1.0, 0.5, -3.0]))
    assert len(picks) == 4
    for i, s in picks.items():
        notes[i]["shift"] = s
    out = tmp_path / "movidas.wav"
    t = time.time()
    assert afo_audio.pitch_edit(p, str(out), notes) == ""
    took = time.time() - t
    errs, still = [], []
    for i, n in enumerate(notes):
        if n["end"] - n["start"] < 0.3:
            continue
        t0, t1 = n["start"] + 0.08, n["end"] - 0.05
        before, _ = _pyin(p, t0, t1)
        after, _ = _pyin(str(out), t0, t1)
        (errs if i in picks else still).append(abs((after - before) - picks.get(i, 0.0)) * 100)
    print(f"movidas: error {[round(e, 1) for e in errs]} cents; no tocadas: hasta {max(still):.1f} cents; {took:.2f} s")
    assert max(errs) < 8 and max(still) < 3
    x, sr = sf.read(p, always_2d=True)
    y, _ = sf.read(str(out), always_2d=True)
    assert y.shape == x.shape
    far = np.ones(len(x), bool)
    for i in picks:
        far[max(0, int((notes[i]["start"] - 0.1) * sr)):int((notes[i]["end"] + 0.1) * sr)] = False
    assert np.max(np.abs(y[far] - x[far])) < 1e-5


def test_el_tiempo_no_cambia(balada, tmp_path):
    """Con todas las notas una tercera arriba, la envolvente sigue en su sitio (desfase < 2 ms) y cada
    nota empieza donde empezaba."""
    p, _, a = balada
    notes = [dict(n, shift=4.0) for n in a["notes"]]
    out = tmp_path / "tercera.wav"
    assert afo_audio.pitch_edit(p, str(out), notes) == ""
    x, sr = sf.read(p, always_2d=True)
    y, _ = sf.read(str(out), always_2d=True)
    env = lambda v: uniform_filter1d(np.abs(v[:, 0]), int(0.01 * sr))
    ex, ey = env(x), env(y)
    m = int(0.02 * sr)
    lag = max(range(-m, m + 1, 8), key=lambda L: float(np.dot(ex[m:-m], ey[m + L:len(ey) - m + L])))
    b = afo_audio.pitch_analyze(str(out))
    starts = []
    for n in a["notes"]:
        k, ov = _match(b["notes"], n["start"], n["end"])
        if k is not None and ov > 0.5 * (n["end"] - n["start"]):
            starts.append(abs(k["start"] - n["start"]))
            assert abs(k["midi"] - n["midi"] - 4.0) < 0.15, (n, k)
    print(f"desfase de la envolvente {lag / sr * 1000:.2f} ms; inicios a mediana {np.median(starts) * 1000:.0f} ms")
    assert abs(lag / sr) < 0.002 and len(starts) >= 0.9 * len(a["notes"]) and np.median(starts) < 0.02


def test_enderezar_quita_el_vibrato(balada, tmp_path):
    """Las notas largas llevan vibrato de ±25 cents: enderezadas, la desviación del tono (pYIN) baja a
    menos de una sexta parte y el centro no se mueve más de 5 cents."""
    p, _, a = balada
    notes = [dict(n, flatten=1.0) for n in a["notes"]]
    out = tmp_path / "recta.wav"
    assert afo_audio.pitch_edit(p, str(out), notes) == ""
    rows = []
    for n in a["notes"]:
        if n["end"] - n["start"] < 0.9:
            continue
        t0, t1 = n["start"] + 0.45, n["end"] - 0.08             # donde ya hay vibrato
        c0, f0 = _pyin(p, t0, t1)
        c1, f1 = _pyin(str(out), t0, t1)
        rows.append((np.std(f0) * 100, np.std(f1) * 100, abs(c1 - c0) * 100))
    rows = np.array(rows)
    print(f"{len(rows)} notas largas: vibrato {rows[:, 0].mean():.1f} → {rows[:, 1].mean():.1f} cents (desv.), "
          f"centro movido hasta {rows[:, 2].max():.1f} cents")
    assert len(rows) >= 4
    assert rows[:, 1].mean() < rows[:, 0].mean() / 6 and rows[:, 2].max() < 5


def test_errores(tmp_path):
    a = afo_audio.pitch_analyze(str(tmp_path / "no.wav"))
    assert not a["ok"] and "no.wav" in a["error"]
    assert "no.wav" in afo_audio.pitch_edit(str(tmp_path / "no.wav"), str(tmp_path / "o.wav"), [])


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    from allforone.bridge import Bridge
    h = EngineHost.create()
    assert h.ok, h.error
    b = Bridge(h)
    yield h, b
    h.engine = None


def test_puente_analiza_aplica_y_vuelve(balada, bridge):
    """La voz con su clip en el segundo 2 del proyecto: «Analizar» da las notas y dónde cae el archivo;
    «Aplicar» con una nota movida pone en la pista una copia (mismos clips, `previous` para deshacer);
    aplicar sin cambios devuelve la pista a la toma analizada."""
    h, b = bridge
    p, _, a = balada
    tid = h.add_audio(p, "Voz")["id"]
    c = h.engine.clips(tid)[0]
    assert json.loads(b.clipEdit(tid, json.dumps({"op": "range", "clip": c["id"], "start": 2.0,
                                                  "length": c["length"], "offset": c["offset"]})))["ok"]
    clips = h.engine.clips(tid)
    events = []
    b.aiEvent.connect(lambda s: events.append(json.loads(s)))

    def wait(kind):
        t0 = time.time()
        while not any(e["type"] == kind for e in events) and time.time() - t0 < 60:
            b._drain_mixer_events(); time.sleep(0.02)
        ev = [e for e in events if e["type"] == kind][-1]
        events.clear()
        return ev

    assert json.loads(b.pitchAnalyze(tid))["ok"]
    assert not json.loads(b.pitchAnalyze(tid))["ok"]               # ya está trabajando
    ev = wait("pitchNotes")
    assert ev["ok"] and ev["source"] == p and abs(ev["fileStart"] - 2.0) < 1e-6
    assert len(ev["notes"]) == len(a["notes"]) and len(ev["curve"]) == len(a["curve"])
    notes = ev["notes"]
    notes[3]["shift"] = 1.0
    r = json.loads(b.pitchApply(tid, json.dumps({"source": ev["source"], "notes": notes})))
    assert r["ok"] and r["edited"] == 1
    ev2 = wait("pitchEdit")
    assert ev2["ok"] and ev2["previous"] == p and ev2["path"] != p and Path(ev2["path"]).is_file()
    assert "afinadas" in ev2["path"] and h.tracks[tid]["originalPath"] == ev2["path"]
    keep = lambda cs: [(round(c["start"], 6), round(c["length"], 6), round(c["offset"], 6)) for c in cs]
    assert keep(h.engine.clips(tid)) == keep(clips)
    n = notes[3]
    before, _ = _pyin(p, n["start"] + 0.06, n["end"] - 0.04)
    after, _ = _pyin(ev2["path"], n["start"] + 0.06, n["end"] - 0.04)
    assert abs(after - before - 1.0) < 0.1
    # Otra vez, ahora sin cambios: desde la toma analizada (no desde la copia) y de vuelta a ella
    for x in notes:
        x["shift"] = 0.0
    r = json.loads(b.pitchApply(tid, json.dumps({"source": ev["source"], "notes": notes})))
    assert r["ok"] and r["edited"] == 0
    ev3 = wait("pitchEdit")
    assert ev3["ok"] and ev3["path"] == p and ev3["previous"] == ev2["path"]
    assert h.tracks[tid]["originalPath"] == p and keep(h.engine.clips(tid)) == keep(clips)
    assert not json.loads(b.pitchApply(tid, json.dumps({"source": "no.wav", "notes": []})))["ok"]

"""G7: la IA escribe MIDI en la rejilla del Piano roll de una pista de instrumento ya existente.
Las notas caen en la rejilla elegida (también tresillos), solo en el tramo pedido (lo de fuera no se
toca), sin la transposición de la pista, y suenan con su sintetizador dentro de una canción completa
(tests/song_factory.py). Con el modelo MIDI local, una composición real de punta a punta."""
import json
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from allforone import midi_ai as M
from allforone import midi_edit
from allforone.engine_host import EngineHost, afo_audio

# Lo que manda la IA: negras desde 0 sin rejilla (el modelo piensa en segundos de 10 ms)
AI = [[0.03, 0.47, 60, 96], [0.52, 0.2, 64, 96], [0.98, 0.9, 67, 96], [1.49, 0.26, 72, 96], [2.02, 1.1, 60, 96],
      [2.02, 1.0, 60, 96], [3.4, 0.4, 65, 96], [7.9, 2.0, 59, 96], [9.2, 1.0, 62, 96]]


def _on_grid(x, g):
    return abs(x / g - round(x / g)) < 1e-4          # se guardan con 6 decimales (tresillos)


def test_las_notas_de_la_ia_caen_en_la_rejilla_del_tramo():
    before = [[0.0, 1.0, 48, 100], [4.5, 0.5, 50, 100], [8.0, 1.0, 52, 100], [12.0, 2.0, 55, 100]]
    track = {"type": "inst", "cfg": {"v": 0}, "midi": before}
    out, added = midi_edit.ai_fill(track, AI, 4.0, 12.0, "1/16")
    inside = [n for n in out if 4.0 <= n[0] < 12.0]
    assert added == len(inside) == 6                                  # la nota repetida en 2,02 entra una vez
    assert all(_on_grid(n[0], 0.25) and _on_grid(n[1], 0.25) for n in inside)
    assert all(n[0] + n[1] <= 12.0 + 1e-9 for n in inside)            # nada pasa del tramo
    assert [n for n in out if not 4.0 <= n[0] < 12.0] == [before[0], before[3]]   # fuera no se toca
    assert [n[2] for n in inside][:3] == [60, 64, 67]

    tri, _ = midi_edit.ai_fill(track, AI, 0.0, 4.0, "1/8T")
    assert all(_on_grid(n[0], 1 / 3) for n in tri if n[0] < 4.0)
    # la pista transpuesta +12: se guarda sin ella para sonar a la altura que eligió la IA
    up, _ = midi_edit.ai_fill({"type": "inst", "cfg": {"v": 0, "tr": 12}, "midi": []}, AI, 0.0, 4.0, "1/16")
    assert up[0][2] == 60 - 12
    with pytest.raises(ValueError):
        midi_edit.ai_fill(track, AI, 0.0, 4.0, "1/5")
    with pytest.raises(ValueError):
        midi_edit.ai_fill(track, AI, 4.0, 4.1, "1/4")


@pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
def test_suenan_en_su_sitio_dentro_de_una_cancion(tmp_path):
    from song_factory import write_song
    h = EngineHost.create()
    assert h.ok, h.error
    try:
        eng = h.engine
        eng.set_tempo(120.0)
        for p in write_song("lofi", tmp_path / "lofi")["paths"]:
            h.add_audio(p, Path(p).stem)
        tid = eng.add_synth_track("Teclas", 0)["id"]
        track = {"type": "inst", "cfg": {"v": 0}, "midi": None, "roll": {}, "clips": [[0, 100]]}
        midi, added = midi_edit.ai_fill(track, AI, 8.0, 16.0, "1/8")          # compases 3–4
        assert added > 0
        track["midi"] = midi
        h.update_synth(tid, track)
        for t in eng.tracks():
            eng.set_track_mute(t["id"], t["id"] != tid)
        out = tmp_path / "teclas.wav"
        assert eng.render_to_wav(str(out))
        y, sr = sf.read(str(out), always_2d=True)
        y = y.mean(axis=1)
        rms = lambda a, b: 20 * np.log10(np.sqrt(np.mean(y[int(a * sr):int(b * sr)] ** 2)) + 1e-12)
        # 120 bpm: negra 8 = 4 s. Antes del tramo, nada; la primera nota (en la línea de 4 s) suena
        assert rms(0.5, 3.9) < -80
        assert rms(4.0, 4.25) > -40
        first = np.argmax(np.abs(y) > 1e-3) / sr
        assert abs(first - 4.0) < 0.02, first                             # en la rejilla, no 15 ms tarde
    finally:
        h.engine.stop()
        h.engine = None


def _wait(ai, events, timeout=600):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if any(e.get("type") == "aiMidi" and e.get("phase") == "done" for e in events):
            break
        time.sleep(0.5)
    return next(e for e in events if e.get("type") == "aiMidi" and e.get("phase") == "done")


@pytest.mark.skipif(M.engine_dir() is None or not M.model_status()["done"], reason="sin llama-server o sin el modelo MIDI")
def test_la_ia_local_rellena_una_pista_de_bajo(tmp_path, monkeypatch):
    """De punta a punta con el modelo local (gráfica): pedir un bajo para una pista que lo espera."""
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    events = []
    ai = M.MidiAi(lambda e: events.append(e if isinstance(e, dict) else json.loads(e)))
    try:
        ai.generate({"family": "Bajo", "style": "Libre", "key": "A minor", "bpm": 90, "bars": 4, "beats": 4,
                     "length": 900, "creativity": 60, "seed": 7, "target": "s42"})
        done = _wait(ai, events)
        assert done["ok"], done
        assert done["target"] == "s42"
        tr = [t for t in done["tracks"] if t["type"] == "inst"]
        assert tr
        track = {"type": "inst", "cfg": {"v": 1}, "midi": [[0.0, 4.0, 33, 90]]}
        out, added = midi_edit.ai_fill(track, tr[0]["midi"], 16.0, 32.0, "1/16")
        assert added >= 4
        assert out[0] == [0.0, 4.0, 33, 90]                                # lo de antes del tramo sigue
        assert all(_on_grid(n[0], 0.25) and 16.0 <= n[0] < 32.0 for n in out[1:])
    finally:
        ai.shutdown()

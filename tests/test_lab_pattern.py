"""Patrón MIDI por familia del Instrumental Lab (C14).

Sin modelo: la descripción sale de la sesión (estilo, tonalidad, tempo), solo cuentan las notas de los
instrumentos de la familia (nunca se cambia el instrumento de otras) y el patrón queda en semicorcheas
del tempo y dentro de los compases.

Con el modelo MIDI-LLM instalado: una sesión de trap a 140 compone un bajo y una de reguetón a 95 una
batería; se comprueba que todo lo que llega es de esa familia, a tempo y dentro de los compases."""
import json
import time

import pytest

from allforone import midi_ai as M


def test_descripcion_y_familias():
    p = M.family_prompt("Bajo", "trap, 808 bass", "F minor", 140, "dark")
    assert p == "trap, 808 bass, bass line, 140 bpm, in F minor, dark"
    assert "in" not in M.family_prompt("Batería", "", "Auto", 95).split(", ")[-1]
    with pytest.raises(ValueError):
        M.family_prompt("Voces", "", "Auto", 90)
    assert set(M.FAMILY_GM) >= {"Batería", "Bajo", "Piano / teclados", "Guitarra", "Sintetizador", "Cuerdas",
                                "Metales", "Maderas", "Percusión"}
    notes = [(0.0, 0.5, 36, 33), (0.1, 0.5, 60, 0), (0.2, 0.1, 38, M.DRUMS), (0.3, 0.5, 40, 81)]
    assert M.pick_family(notes, "Bajo") == [(0.0, 0.5, 36, 33)]
    assert M.pick_family(notes, "Batería") == [(0.2, 0.1, 38, M.DRUMS)]
    assert M.pick_family(notes, "Cuerdas") == []                    # sin cuerdas: nada, no se inventa


def test_a_tempo_y_dentro_de_los_compases():
    bpm, bars = 120.0, 2                     # semicorchea = 0,125 s; 2 compases de 4/4 = 4 s
    notes = [(0.06, 0.3, 40, 33), (0.13, 0.01, 43, 33), (3.99, 1.0, 45, 33), (4.2, 0.5, 47, 33), (0.124, 0.2, 43, 33)]
    out = M.to_pattern(notes, bpm, bars)
    step = 0.125
    assert all(abs(t / step - round(t / step)) < 1e-6 for t, *_ in out)
    assert all(t < 4.0 and t + d <= 4.0 + 1e-6 for t, d, *_ in out)
    assert all(d >= step - 1e-9 for _, d, *_ in out)
    assert len(out) == 2, out                    # 3,99 → 4,0 y 4,2 quedan fuera; dos 43 en el mismo paso cuentan una
    mixed = M.to_pattern([(0.0, 0.2, 40, 33), (0.25, 0.2, 43, 34), (0.5, 0.2, 45, 34)], bpm, bars)
    assert {n[3] for n in mixed} == {34} and len(mixed) == 3      # un patrón = una pista: el bajo con más notas


def _wait(b, events, timeout=900):
    from PySide6.QtCore import QCoreApplication
    t0 = time.monotonic()
    while not any(e.get("type") == "aiMidi" and e.get("phase") == "done" for e in events) and time.monotonic() - t0 < timeout:
        QCoreApplication.processEvents()
        time.sleep(0.05)
    return next(e for e in events if e.get("type") == "aiMidi" and e.get("phase") == "done")


@pytest.mark.skipif(M.engine_dir() is None or not M.model_status()["done"], reason="sin llama-server o sin el modelo MIDI")
@pytest.mark.parametrize("style,family,bpm,key", [("Trap", "Bajo", 140, "F minor"), ("Reguetón", "Batería", 95, "Auto")])
def test_patron_de_una_sesion(style, family, bpm, key, tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    events = []
    ai = M.MidiAi(lambda e: events.append(e if isinstance(e, dict) else json.loads(e)))
    try:
        bars = 4
        t0 = time.monotonic()
        ai.generate({"family": family, "style": style, "key": key, "bpm": bpm, "bars": bars, "beats": 4,
                     "length": 900, "creativity": 60, "seed": 11})
        done = _wait(ai, events)
        assert done["ok"], done
        assert done["family"] == family and done["tracks"]
        beat_end = bars * 4                                       # negras del patrón
        progs = M.FAMILY_GM[family][0]
        n = 0
        for tr in done["tracks"]:
            assert tr["program"] in progs, tr["program"]
            for b0, dur, *_ in tr["midi"]:
                assert abs(b0 * 4 - round(b0 * 4)) < 1e-3, "en la rejilla de semicorcheas"
                assert 0 <= b0 < beat_end
                n += 1
        names = [tr["name"] for tr in done["tracks"]]
        assert len(done["tracks"]) == 1, names                    # un patrón = una pista
        print(f"{style} {bpm} · {family}: {n} notas en {names} ({time.monotonic() - t0:.0f} s)")
        assert n >= 4
    finally:
        ai.shutdown()

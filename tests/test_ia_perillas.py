"""X8: las dos perillas «Creatividad» del módulo IA actúan de verdad (sin GPU: se comprueba lo que llega
al motor). Canción (ACE-Step) → temperatura del compositor; MIDI → temperatura del muestreo."""
import pytest

from allforone import ai_music, midi_ai


@pytest.mark.parametrize("style", ["Trap", "Rock", "Balada"])
def test_creatividad_de_cancion_cambia_la_temperatura(style):
    pack = next(iter(ai_music.PACKS))
    req = lambda c: ai_music.build_request({"style": style, "prompt": "prueba", "creativity": c}, pack)  # noqa: E731
    t0, t50, t100 = (req(c)["lm_temperature"] for c in (0, 50, 100))
    assert t0 < t50 < t100
    assert (t0, t100) == (0.6, 1.1)


def test_creatividad_de_midi_cambia_la_temperatura():
    t = [midi_ai.creativity_temperature(c) for c in (0, 50, 100)]
    assert t[0] < t[1] < t[2]
    assert t[0] == pytest.approx(0.7) and t[2] == pytest.approx(1.2)

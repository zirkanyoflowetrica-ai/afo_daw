"""Sintetizador del motor (Instrumento / Batería): clip MIDI + plugin propio, render real de Tracktion."""
import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")


@pytest.fixture()
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    yield h
    h.engine = None


def peak_hz(x, sr):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return np.fft.rfftfreq(len(x), 1 / sr)[spec.argmax()]


def test_nota_en_su_tiempo_y_afinada(host, tmp_path):
    eng = host.engine
    eng.set_tempo(120.0)
    tid = eng.add_synth_track("Prueba", 0)["id"]
    eng.set_synth_settings(tid, mode=0, wave=4, vel=100, bri=100)          # «Pad ambiental»: seno
    length = eng.set_synth_notes(tid, [(1.0, 69)], 8.0)                      # La 440 Hz en el tiempo 2 (0,5 s)
    assert length == pytest.approx(4.0, abs=0.01)                            # 8 negras a 120 BPM
    out = tmp_path / "nota.wav"
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    y = y[:, 0]
    at = int(0.5 * sr)
    assert np.abs(y[: at - int(0.01 * sr)]).max() < 1e-4                     # silencio antes de la nota
    assert peak_hz(y[at: at + int(0.25 * sr)], sr) == pytest.approx(440, abs=5)
    assert np.abs(y[at + int(0.35 * sr): at + int(0.5 * sr)]).max() < 0.01   # la nota dura 0,3 s


def test_bateria_y_cambio_de_patron(host, tmp_path):
    eng = host.engine
    eng.set_tempo(96.0)
    tid = eng.add_synth_track("Batería", 1)["id"]
    eng.set_synth_settings(tid, mode=1, vol=80, tun=50)
    eng.set_synth_notes(tid, [(b * 1.0, 36) for b in range(4)], 4.0)          # bombo en negras
    out = tmp_path / "bateria.wav"
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    beat = 60 / 96
    hits = [np.abs(y[int(k * beat * sr): int(k * beat * sr) + 2000, 0]).max() for k in range(4)]
    assert min(hits) > 0.3
    # Rehacer el patrón sustituye el clip (no se acumulan)
    eng.set_synth_notes(tid, [(2.0, 36)], 4.0)
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    assert np.abs(y[: int(1.9 * beat * sr), 0]).max() < 1e-4
    assert eng.set_synth_notes(tid, [], 4.0) == 0.0


def test_no_es_pista_de_sintesis(host):
    path = host.add_test_tone()["id"]
    with pytest.raises(Exception):
        host.engine.set_synth_notes(path, [(0.0, 60)], 4.0)


def test_patron_de_la_plantilla_a_notas():
    from allforone.engine_host import pattern_notes

    # «Acordes»: 7 notas del piano roll, clips en los compases 1-8 y 11-16 (como la plantilla)
    roll = {f"{r}-{c}": 1 for r, c in [(0, 0), (4, 4), (7, 5), (10, 6), (3, 8), (6, 10), (9, 12)]}
    notes = pattern_notes({"type": "inst", "clips": [[0, 50], [62.5, 37.5]], "roll": roll})
    assert len(notes) == 7 * (8 + 6)
    assert (0.0, 72) in notes and (1.0 + 4 * 1, 72 - 4) in notes            # C5 en el compás 1; G#4 paso 5 del compás 2
    assert not [n for n in notes if 32 <= n[0] < 40]                         # compases 9-10 sin clip
    # «Batería 1»: patrón básico (bombo en negras, caja en 2 y 4, hi-hat en corcheas, hi-hat abierto)
    pat = {**{f"0-{s}": 1 for s in (0, 4, 8, 12)}, "1-4": 1, "1-12": 1, **{f"2-{s}": 1 for s in range(0, 16, 2)}, "3-14": 1}
    drums = pattern_notes({"type": "drum", "clips": [[0, 100]], "pat": pat})
    assert len(drums) == 16 * 15 and (0.0, 36) in drums and (3.5, 39) in drums

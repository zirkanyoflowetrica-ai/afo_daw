"""Motor nativo desde Python: audio real, sin dispositivo (render offline)."""
import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import EngineHost, afo_audio, fader_to_db

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")


def test_fader_law():
    assert fader_to_db(70) == pytest.approx(0.0)
    assert fader_to_db(0) == -100.0
    assert fader_to_db(100) == pytest.approx(6.196, abs=0.01)
    assert fader_to_db(35) == pytest.approx(-12.04, abs=0.01)


@pytest.fixture(scope="module")
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    yield h
    h.engine = None


def test_tone_render_measure(host, tmp_path):
    tr = host.add_test_tone()
    assert tr["length_seconds"] == pytest.approx(8.0, abs=0.01)
    assert len(tr["peaks"]) == 600 and max(tr["peaks"]) == pytest.approx(0.251, abs=0.01)
    out = tmp_path / "mix.wav"
    host.engine.set_track_gain_db(tr["id"], fader_to_db(35))   # -12 dB
    assert host.engine.render_to_wav(str(out))
    data, sr = sf.read(str(out))
    assert data.shape[1] == 2
    assert 20 * np.log10(np.abs(data).max()) == pytest.approx(-24.04, abs=0.1)
    spec = np.abs(np.fft.rfft(data[: sr * 2, 0]))
    assert np.fft.rfftfreq(sr * 2, 1 / sr)[spec.argmax()] == pytest.approx(440, abs=1)
    m = afo_audio.measure_file(str(out))
    assert m["peak_db"] == pytest.approx(-24.04, abs=0.1)
    host.remove(tr["id"])


def test_pan_moves_energy(host, tmp_path):
    tr = host.add_test_tone()
    host.engine.set_track_pan(tr["id"], -1.0)
    out = tmp_path / "pan.wav"
    assert host.engine.render_to_wav(str(out))
    data, _ = sf.read(str(out))
    assert np.abs(data[:, 0]).max() > 0.1 and np.abs(data[:, 1]).max() < 1e-4
    host.remove(tr["id"])


def test_transport_state_without_device(host):
    host.engine.set_tempo(128)
    assert host.engine.tempo() == pytest.approx(128)
    snap = host.snapshot()
    assert set(snap) == {"playing", "position", "length", "master", "vu", "tracks", "rec", "preview", "loud", "mloud"}
    assert snap["playing"] is False

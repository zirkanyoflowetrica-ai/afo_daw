"""Pruebas focalizadas sobre voces _B, sin modificar V3 fuera de esa ruta."""
from pathlib import Path
import sys
import tempfile
import numpy as np
import soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mixer_engine as eng


def main():
    for name in ['Voz_B.wav', 'Voz_B_02.wav', 'Vocal_B_L.wav', 'Toma_B_R.wav', 'toma_b.wav']:
        assert eng.is_backing_voice(name), name
        assert eng.guess_type(name) == 'Voz de apoyo (_B)', name
    for name in ['Bass.wav', 'Bateria.wav', 'Voz_Brillo.wav', 'Voz_B2.wav', 'Voice_L.wav']:
        assert not eng.is_backing_voice(name), name
    assert eng.pan_from_filename('Guitarra_L.wav') == 'Izquierda'
    assert eng.pan_from_filename('Voz_B_R.wav') == 'Derecha'  # Raw parse; overrides in render_mix.
    sr=eng.SR
    t=np.arange(sr*4) / sr
    lead=(.20*np.sin(2*np.pi*180*t)+.05*np.sin(2*np.pi*720*t)).astype('float32')
    support=(.30*np.sin(2*np.pi*185*t)+.04*np.sin(2*np.pi*745*t)).astype('float32')
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)
        sf.write(p/'Voz_principal.wav', lead, sr)
        sf.write(p/'Toma_B_R.wav', support, sr)
        both, report, _=eng.render_mix([{'path':str(p/'Voz_principal.wav')},{'path':str(p/'Toma_B_R.wav')}],return_details=True)
        assert 'Voces L/R (grupo):' in report, report
        assert 'Toma_B_R.wav: Voz de apoyo (_B)' in report, report
        assert np.all(np.isfinite(both))
        # La reverb estereo puede dar diferencias L/R en la mezcla final,
        # pero el paneo seco _B debe ser exactamente centrado.
        raw = eng.stereo(support[None, :], 'Original / centro')
        assert np.array_equal(raw[0], raw[1])
        assert 'escalon objetivo 7.0 dB bajo principal' in report
        only_backing, report_without, _ = eng.render_mix([{'path':str(p/'Toma_B_R.wav')}],return_details=True)
        assert 'Sin principal: techo -26 LUFS' in report_without
        assert np.all(np.isfinite(only_backing))
    print('Pruebas de voces _B OK')

if __name__ == '__main__':
    main()


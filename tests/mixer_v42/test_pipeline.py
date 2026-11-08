"""Test de humo: DSP, separacion reconstruible, referencia, interfaz."""
import os
import sys
import tempfile
from pathlib import Path
import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drum_split import split_drums
from audio_intelligence import identify_audio
import mixer_engine as eng


def main():
    sr = eng.SR
    seconds = 3.0
    n = int(sr*seconds)
    t = np.arange(n) / sr
    kick = np.zeros(n, np.float32)
    snare = np.zeros(n, np.float32)
    hat = np.zeros(n, np.float32)
    rng = np.random.default_rng(1234)
    for start in (0, .5, 1, 1.5, 2, 2.5):
        i = int(start*sr)
        sl = slice(i, min(i+int(.15*sr), n))
        tau = t[sl] - t[i]
        kick[sl] += (.62*np.sin(2*np.pi*65*tau) * np.exp(-28*tau)).astype(np.float32)
    for start in (.5, 1.5, 2.5):
        i = int(start*sr)
        sl = slice(i, i+int(.1*sr))
        tau = t[sl] - t[i]
        snare[sl] += (.2*rng.standard_normal(len(tau))*np.exp(-45*tau)).astype(np.float32)
    for start in np.arange(0, seconds, .25):
        i = int(start*sr)
        sl = slice(i, min(i+int(.04*sr), n))
        tau = t[sl] - t[i]
        zz = rng.standard_normal(len(tau))
        hat[sl] += (.07*np.diff(zz,prepend=zz[:1])*np.exp(-100*tau)).astype(np.float32)
    drums = np.clip(kick+snare+hat,-1,1).astype(np.float32)
    split = split_drums(drums[None,:])
    total = np.sum(np.stack(list(split.values()),axis=0),axis=0)
    error = float(np.max(np.abs(total-drums[None,:])))
    print('Error reconstruccion drums:',error)
    assert error < 2e-4, error
    print('Audio guess drums:',identify_audio(drums[None,:], sr))
    with tempfile.TemporaryDirectory() as d:
        d=Path(d)
        # referencia tiene un balance tonal algo diferente
        bass = .13*np.sin(2*np.pi*82*t).astype(np.float32)
        guitar = .07*np.sin(2*np.pi*330*t).astype(np.float32)
        sf.write(d/'Drums.wav', drums, sr)
        sf.write(d/'Bass.wav', bass, sr)
        sf.write(d/'Guitarra_L.wav', guitar, sr)
        sf.write(d/'Guitarra_R.wav', guitar*.7, sr)
        ref = .25*drums + .14*bass + .22*guitar
        sf.write(d/'Referencia.wav', ref, sr)
        mix, report, details = eng.render_mix([{'path':str(p)} for p in sorted(d.glob('*.wav')) if p.name != 'Referencia.wav'],reference_path=str(d/'Referencia.wav'),return_details=True)
        print('Informe:',report[:2200])
        assert mix.shape == (2,n)
        assert np.all(np.isfinite(mix))
        assert details['reference_lufs'] is not None
        assert len(details['derived']) == 5
        assert eng.pan_from_filename('guitarra_L.wav') == 'Izquierda'
        assert eng.pan_from_filename('guitarra_L_01.wav') == 'Original / centro'
        for preset in eng.MASTERS:
            mastered, stats=eng.master(mix,preset)
            assert mastered.shape == mix.shape
            assert np.all(np.isfinite(mastered))
            assert stats['true_peak'] <= -0.9, (preset,stats)
            print('Master:',preset,stats)
        print('Interfaz:', end=' ')
        import app
        ui=app.build_ui()
        assert ui is not None
        print('OK')
        fp=eng.save_wav(d/'out.wav',mix)
        assert Path(fp).exists()
    print('TESTS OK')

if __name__ == '__main__':
    main()

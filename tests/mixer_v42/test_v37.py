"""Comprobar PSOLA conservador y que los apoyos no son afinados por defecto."""
import sys
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scale_tuner import tune_to_scale, track_pitch
import mixer_engine as eng

SR=44100

def test_psola():
    t=np.arange(SR*4)/SR
    a=(.13*np.sin(2*np.pi*237*t)+.03*np.sin(2*np.pi*474*t)).astype('float32')
    shape=np.zeros(len(t),dtype='float32'); shape[(t>.5)&(t<3.4)]=1.
    a*=shape
    stereo=np.stack([a,.8*a]); y,note=tune_to_scale(stereo,SR,'C','Mayor',100)
    assert 'PSOLA' in note,(note,)
    assert np.array_equal(stereo[:,:SR//4],y[:,:SR//4]),'silencio alterado'
    assert np.array_equal(stereo[:,int(3.65*SR):],y[:,int(3.65*SR):]),'cola alterada'
    assert y.shape==stereo.shape and np.isfinite(y).all()
    assert np.allclose(y[1],.8*y[0],atol=2e-6),'coherencia de estereo perdida'
    _,f,c=track_pitch(y[:,int(1*SR):int(2.5*SR)],SR)
    freq=np.nanmedian(f[c>.8])
    assert abs(freq-246.94)<2.,(freq,note)
    # Un estéreo vocal REAL no debe reducirse a mono ni procesarse con desfase.
    z=np.stack([a,np.roll(a,375)])
    skipped,notice=tune_to_scale(z,SR,'C','Mayor',100)
    assert np.array_equal(z,skipped),notice
    assert 'estereo' in notice
    print('PSOLA: pitch, duracion, silencios, fase e imagen estereo OK')

def test_pipeline_default_lead():
    t=np.arange(SR*2)/SR
    sig=.09*np.sin(2*np.pi*237*t).astype('float32')
    with tempfile.TemporaryDirectory() as d:
        lead=Path(d)/'Voz_Principal.wav'; side=Path(d)/'Voz_B_L.wav'
        sf.write(lead,sig,SR); sf.write(side,sig*.5,SR)
        calls=[]
        real=eng.process_vocal
        def log_tuning(x,sr,tuning=False,kind='Voz principal'):
            calls.append((kind,tuning))
            return real(x,sr,tuning,kind)
        with patch.object(eng,'process_vocal',side_effect=log_tuning):
            eng.render_mix([{'path':str(lead)},{'path':str(side)}],tuning={'key':'C','scale':'Mayor','strength':70},backing_step_db=7)
        assert len(calls)==2,calls
        assert isinstance(calls[0][1],dict) and calls[1][1] is False,calls
        print('Afinacion solo voz principal por defecto, apoyo intacto OK')

if __name__=='__main__':
    test_psola(); test_pipeline_default_lead(); print('V3.7 TESTS OK')

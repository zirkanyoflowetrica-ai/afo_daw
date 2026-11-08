"""Regresiones contra artefactos: notas, fronteras, silencios y orden DSP."""
import sys
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scale_tuner import tune_to_scale,track_pitch
from vocal_dsp import process_vocal

SR=44100

def f0_region(signal,t0,t1):
    p,f,c=track_pitch(signal[:,int(t0*SR):int(t1*SR)],SR)
    return float(np.nanmedian(f[c>.83]))

def test_phrases():
    rng=np.random.default_rng(99)
    t=np.arange(SR*8)/SR
    x=np.zeros((2,len(t)),dtype='float32')
    # Dos frases con vibrato suave, no una señal idéntica a un test de seno puro.
    for left,right,base in [(1.,3.6,267.0),(4.1,6.5,293.664768)]:
        mask=(t>=left)&(t<right)
        phase=2*np.pi*np.cumsum(base*(1+.002*np.sin(t*2*np.pi*4.5)))/SR
        signal=(.12*np.sin(phase)+.034*np.sin(2*phase+.15)+.01*np.sin(3*phase+.3))
        env=np.zeros(len(t))
        local=t[mask]-left
        duration=right-left
        env[mask]=np.minimum(1,np.minimum(local/.06,(duration-local)/.06))
        x[0] += (signal*env).astype('float32')
        x[1] += (.9*signal*env).astype('float32')
    # Consonante/sibilancia sin F0 entre notas; no debe generar pitch aleatorio.
    noise=rng.normal(0,.025,int(.16*SR)).astype('float32')
    x[:,int(3.83*SR):int(3.83*SR)+len(noise)]+=noise[None,:]
    y,note=tune_to_scale(x,SR,'C','Mayor',100)
    assert y.shape==x.shape and np.isfinite(y).all()
    assert np.array_equal(x[:,:int(.6*SR)],y[:,:int(.6*SR)]), 'Silencio alterado'
    assert np.array_equal(x[:,int(7*SR):],y[:,int(7*SR):]),'Cola no tonal alterada'
    assert np.array_equal(x[:,int(3.83*SR):int(3.99*SR)],y[:,int(3.83*SR):int(3.99*SR)]), 'Consonante no tonal alterada'
    target=261.625565
    f=f0_region(y,1.4,2.7)
    assert abs(1200*np.log2(f/target))<9,(f,note)
    second=f0_region(y,4.5,6.)
    assert abs(1200*np.log2(second/293.664768))<9,second
    assert np.max(abs(y))<.8, 'Resintesis descontrolada'
    corr=float(np.corrcoef(y[:,int(1.3*SR):int(3*SR)])[0,1])
    assert corr>.985,corr
    print('V3.5: frases, notas, sibilancia no tonal, estereo, duración y nivel OK')

def test_order():
    events=[]
    inp=np.zeros((1,SR//2),dtype='float32')
    def tuned(x,*args,**kwargs):
        events.append('afinacion')
        return x,'afinacion prueba'
    def repaired(x,*args,**kwargs):
        events.append('limpieza')
        return x,'limpieza prueba'
    with patch('scale_tuner.tune_to_scale',side_effect=tuned),patch('track_tools.repair_vocal',side_effect=repaired):
        process_vocal(inp,SR,tuning={'key':'C','scale':'Mayor','strength':100})
    assert events[:2]==['afinacion','limpieza'],events
    print('V3.5: afinacion estrictamente antes que limpieza/EQ/FX OK')

if __name__=='__main__':
    test_phrases()
    test_order()
    print('V3.5 TESTS OK')

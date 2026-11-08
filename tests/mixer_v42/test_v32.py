"""Validación cuantitativa con audio sintético, no evaluación auditiva."""
import sys
from pathlib import Path
import tempfile
import os
import numpy as np
import soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mixer_engine as eng
from vocal_dsp import pitch_profile, dynamic_cut, process_vocal, phase_notes, compare_phase, vocal_effects

def main():
    sr=eng.SR
    t=np.arange(sr*3)/sr
    tone=lambda f: np.sin(2*np.pi*f*t)[None,:].astype('float32')*.2
    for f in (82.4, 180, 440, 650):
        p=pitch_profile(tone(f),sr)
        assert p and abs(p['median']-f)/f<.02, (f,p)
        print('F0', f, p)
    assert pitch_profile(np.zeros((1,sr)),sr) is None
    rng=np.random.default_rng(47)
    assert pitch_profile(rng.normal(0,.05,(1,sr*3)),sr) is None
    # El de-esser reduce las ráfagas de alta frecuencia; preserva el tramo grave.
    gate=(t>1)&(t<2)
    dry=tone(180)+tone(6500)*gate
    out, reduction=dynamic_cut(dry,sr,4500,10000,4)
    sibilant=slice(int(sr*1.2),int(sr*1.8))
    def amplitude(x,f,sl):
        return abs(np.mean(x[0,sl]*np.exp(-2j*np.pi*f*t[sl])))*2
    assert amplitude(out,6500,sibilant)<amplitude(dry,6500,sibilant)*.85
    assert abs(amplitude(out,180,sibilant)/amplitude(dry,180,sibilant)-1)<.02
    assert reduction<=4.0001
    assert np.max(np.abs(out[:,:int(sr*.8)]-dry[:,:int(sr*.8)]))<.001
    # EQ dinámica: el sidechain inactivo deja pasar; activo abre espacio.
    source=tone(3100)
    idle,_=dynamic_cut(source,sr,2200,4500,1.8,np.zeros_like(source))
    active,_=dynamic_cut(source,sr,2200,4500,1.8,tone(180))
    assert np.allclose(idle,source)
    assert np.std(active)<np.std(source)*.9
    for suffix,ratio in (('_B_L',1+np.sqrt(2)),('_B_R',1/(1+np.sqrt(2)))):
        pan=eng.stereo(tone(180),eng.backing_position('Voz'+suffix+'.wav'))
        assert np.isclose(np.std(pan[0])/np.std(pan[1]),ratio,rtol=1e-5)
        assert np.isclose(np.sum(pan**2),np.sum(tone(180)**2),rtol=1e-5)
    c=eng.stereo(tone(180),eng.backing_position('Voz_B_02.wav'))
    assert np.array_equal(c[0],c[1])
    assert phase_notes(np.concatenate([tone(180),-tone(180)]),'invertida')
    history=[]
    assert not compare_phase(tone(180),'primera',history,sr)
    assert compare_phase(-tone(180),'segunda',history,sr)
    # Afinación OFF es determinista; ON reduce desvío de una toma estable.
    detuned=tone(220*2**(.20/12))
    off,msg=process_vocal(detuned,sr,False)
    on,msg_on=process_vocal(detuned,sr,True)
    assert 'afinacion cromatica global prudente' in msg_on, msg_on
    foff=pitch_profile(off[:,sr//2:],sr)['median']
    fon=pitch_profile(on[:,sr//2:],sr)['median']
    assert abs(fon-220)<abs(foff-220), (foff,fon)
    variable=np.concatenate([tone(180)[:,:sr],tone(240)[:,:sr],tone(300)[:,:sr]],axis=1)
    _,msg=process_vocal(variable,sr,True)
    assert 'afinacion omitida' in msg
    effected=vocal_effects(off,sr)
    assert effected.shape==off.shape and np.all(np.isfinite(effected))
    assert not np.allclose(effected,off)
    # Prueba completa también del callback UI, archivos y referencia.
    import app
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)
        names=['Voz_principal.wav','Voz_B_L.wav','Voz_B_R.wav','Voz_B.wav']
        for i,name in enumerate(names):
            sf.write(p/name,tone(180+i*10)[0],sr)
        paths=[str(p/name) for name in names]
        original=os.getcwd()
        os.chdir(p)
        try:
            result=app.process(paths,paths[0],True,progress=lambda *a,**kw:None)
        finally:
            os.chdir(original)
        assert len(result)==4+len(eng.MASTERS)
        assert '50% izquierda' in result[0] and '50% derecha' in result[0]
        assert 'F0 mediana' in result[0] and 'de-esser' in result[0]
        for file in result[-1]:
            assert Path(file).is_file(),file
            if file.endswith('.wav'):
                x,rate=sf.read(file,always_2d=True)
                assert rate==sr and x.shape==(len(t),2)
                assert np.all(np.isfinite(x)) and np.max(np.abs(x))<1
    print('V3.2: F0, de-esser, EQ dinamica, fase, paneo, efectos, afinacion, callback y exportaciones OK')

if __name__=='__main__':
    main()


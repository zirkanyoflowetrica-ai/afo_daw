"""Afinación por escala, intensidad, air, color y corrección del cache de Gradio."""
import sys,os,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import runtime_setup
from scale_tuner import tune_to_scale,track_pitch,allowed_notes
from sonic_tools import enhance_vocal,enhance_master,saturation
import mixer_engine as eng

def median_frequency(x,sr,left=.3,right=2.7):
    pos,f,c=track_pitch(x,sr)
    return float(np.nanmedian(f[(pos>left*sr)&(pos<right*sr)]))

def main():
    sr=eng.SR
    t=np.arange(sr*3)/sr
    target=261.625565
    original=(.2*np.sin(2*np.pi*target*2**(.35/12)*t)).astype('float32')[None,:]
    frequencies=[]
    for strength in (0,50,100):
        y,note=tune_to_scale(original,sr,'C','Mayor',strength)
        assert y.shape==original.shape and np.all(np.isfinite(y))
        if strength==0:assert np.array_equal(y,original)
        f=median_frequency(y,sr)
        cents=1200*np.log2(f/target)
        frequencies.append(cents)
        print(f'Afinacion {strength}%: {f:.3f} Hz, desvio {cents:.2f} cents')
    assert 25<frequencies[0]<45
    assert 8<frequencies[1]<25
    assert abs(frequencies[2])<8
    assert abs(frequencies[2])<abs(frequencies[1])<abs(frequencies[0])
    assert 66 in allowed_notes('D','Mayor') and 65 not in allowed_notes('D','Mayor')
    # Una nota excluida de C mayor sí se mueve a un grado de esa escala.
    forbidden=(.2*np.sin(2*np.pi*280*t)).astype('float32')[None,:]
    tuned,_=tune_to_scale(forbidden,sr,'C','Mayor',100)
    assert abs(1200*np.log2(median_frequency(tuned,sr)/293.664768))<10
    rng=np.random.default_rng(34)
    noise=rng.normal(0,.03,original.shape).astype('float32')
    untouched,note=tune_to_scale(noise,sr,'C','Mayor',100)
    assert np.array_equal(noise,untouched),note
    long_t=np.arange(sr*10)/sr
    sustained=(.2*np.sin(2*np.pi*267*long_t)).astype('float32')[None,:]
    smooth,_=tune_to_scale(sustained,sr,'C','Mayor',100)
    reference=np.std(smooth[:,sr*4:sr*5])
    for left in (5.7,5.8,5.9,6.,6.1):
        level=np.std(smooth[:,int(left*sr):int((left+.1)*sr)])
        assert level>reference*.85,(left,level,reference)
    print('Afinacion: escala respetada, ruido intacto y solapes sin cancelacion de vocal sostenida')
    gate=np.clip(np.sin(2*np.pi*.5*t)*4,0,1)
    dark=(gate*(.12*np.sin(2*np.pi*180*t)+.005*np.sin(2*np.pi*9000*t))).astype('float32')[None,:]
    enhanced,note=enhance_vocal(dark,sr,'Voz principal')
    assert 'air adaptativo +' in note and 'saturacion paralela 8%' in note,note
    assert 'air adaptativo +0.0' not in note,note
    bright=(gate*(.04*np.sin(2*np.pi*180*t)+.12*np.sin(2*np.pi*19000*t))).astype('float32')[None,:]
    high,note=enhance_vocal(bright,sr,'Voz principal')
    assert 'air adaptativo +0.0' in note and '18.5 kHz' in note,note
    assert np.all(np.isfinite(high)) and high.shape==bright.shape
    colored,amount=saturation(original,sr,.08)
    delta=20*np.log10(np.std(colored)/np.std(original))
    assert abs(delta)<.6,delta
    master,note=enhance_master(eng.stereo(dark,'Original / centro'),sr)
    assert np.all(np.isfinite(master)) and '2.5%' in note
    print('Air adaptativo, recorte condicional y aportes de saturacion/compresion: OK')
    assert Path(os.environ['GRADIO_TEMP_DIR']).resolve()==runtime_setup.CACHE
    assert Path(tempfile.gettempdir()).resolve()==runtime_setup.TEMP
    with tempfile.TemporaryDirectory() as folder:
        p=Path(folder)/'Voz_principal.wav';sf.write(p,original.T,sr)
        with patch('runtime_setup.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
            try:runtime_setup.check_space([p],folder)
            except OSError as error:assert 'Espacio insuficiente' in str(error)
            else:raise AssertionError('No detecto disco lleno')
        import app
        cwd=os.getcwd();os.chdir(folder)
        try:result=app.process([str(p)],None,dict(key='C',scale='Mayor',strength=100),progress=lambda *a,**k:None,with_review=True)
        finally:os.chdir(cwd)
        assert 'afinacion vocal PSOLA C Mayor' in result[0]
        assert 'saturacion paralela' in result[0]
        assert len(result[-3])<=10  # descargas esenciales, no duplicar todos los stems
        assert Path(result[-3][0]).is_file()
    print(f'Cache y temporales: {runtime_setup.ROOT}; preflight de espacio y sesion afinada OK')
    print('V3.4 TESTS OK')

if __name__=='__main__':main()

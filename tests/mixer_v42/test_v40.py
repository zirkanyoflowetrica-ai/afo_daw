"""V4.0: stems afinados uno a uno + tonalidad/BPM desde instrumentos."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mixer_engine as eng
import app
from music_analysis import analyze_music, _key_estimate


def _tone(f,t,sr=11025):
    # Oscilador armónico con fundidos por nota.
    x=np.sin(2*np.pi*f*t)+.22*np.sin(2*np.pi*2*f*t)+.13*np.sin(2*np.pi*3*f*t)
    return x


def write_music(root,sr=11025,duration=17):
    t=np.arange(int(sr*duration))/sr
    z=np.zeros(len(t),dtype='float32')
    fs=[261.63,329.63,392.,523.25]
    # secuencias con silencios entre notas y acordes C-F-G-C
    for k in range(int(duration*2)):
        begin=int((k*.5)*sr); end=min(begin+int(.43*sr),len(t))
        if end<=begin:continue
        q=np.arange(end-begin)/sr
        env=(1-np.exp(-q*40))*np.exp(-q*2.5)
        z[begin:end]+=.09*_tone(fs[k%4],q)*env
    sf.write(root/'Piano.wav',z,sr)
    drums=np.zeros(len(t),dtype='float32')
    for i in range(int(duration*2)):
        j=int(i*.5*sr)
        m=min(int(sr*.015),len(drums)-j)
        rng=np.random.default_rng(i)
        drums[j:j+m]+=(rng.standard_normal(m)*np.exp(-np.linspace(0,5,m))*.3).astype('float32')
    sf.write(root/'Drums.wav',drums,sr)
    return root/'Piano.wav',root/'Drums.wav'


def test_auto_analysis():
    with tempfile.TemporaryDirectory() as td:
        piano,drums=write_music(Path(td))
        res=analyze_music([str(piano),str(drums)])
        print('AUTO:',res.summary())
        assert res.bpm is not None and abs(res.bpm-120)<5
        assert res.key=='C' and res.scale=='Mayor' and res.key_confidence>=.50
        assert res.source_names and 'Piano.wav' in res.source_names
        assert res.key_status
        assert res.bpm_status
        # Solo percusión: nunca afirmar una tonalidad sin evidencia armónica.
        only=analyze_music([str(drums)])
        assert only.key is None


def test_independent_tuning_switches():
    sr=eng.SR
    t=np.arange(sr*2.4)/sr
    x=(.08*np.sin(2*np.pi*245*t)).astype(np.float32)
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)
        for name in ('Voz_Principal.wav','Voz_L.wav','Voz_R.wav'):
            sf.write(p/name,x,sr)
        calls=[]
        def fake_process(audio, rate, tuning,kind):
            calls.append((kind, bool(isinstance(tuning,dict))))
            return audio,'mock'
        with patch.object(eng,'process_vocal',side_effect=fake_process):
            eng.render_mix([{'path':str(p/name)} for name in ('Voz_Principal.wav','Voz_L.wav','Voz_R.wav')],
                         tuning={'key':'C','scale':'Mayor','strength':45,'tune_lead':True,'tune_left':True,'tune_right':False},
                         vocal_space_amount=0)
        assert len(calls)==3,calls
        assert [flag for _,flag in calls]==[True,True,False],calls


def test_ui():
    ui=app.build_ui()
    labels={c.get('props',{}).get('label') for c in ui.get_config_file()['components']}
    for x in ['Escala de afinación','Detectar BPM automáticamente','BPM manual (0 = detección automática)',
              'Análisis instrumental (orientativo)']:
        assert x in labels,x
    called=[]
    def fake(*a,**kw):called.append((a,kw));return 'ok'
    with patch.object(app,'process',side_effect=fake):
        app.process_ui([],None,'C','Mayor',60,7,key_mode='Automático',auto_bpm=True,progress=None)
        app.process_ui([],None,'G','Menor natural',60,7,key_mode='Manual',auto_bpm=False,space_bpm=90,progress=None)
    assert called[0][0][2]['auto_key'] is True
    assert called[0][1]['auto_music_bpm'] is True
    assert called[1][0][2]['auto_key'] is False
    assert called[1][1]['vocal_space_bpm']==90


def test_key_protection():
    # Ningún instrumento => no afinar automáticamente sobre solo voces.
    result=analyze_music([])
    assert result.key is None and result.bpm is None
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'Voz_Principal.wav'
        sr=eng.SR;t=np.arange(sr*1.1)/sr
        sf.write(path,(.04*np.sin(2*np.pi*240*t)).astype(np.float32),sr)
        calls=[]
        def fake_process(audio, rate, tuning, kind):
            calls.append(tuning)
            return audio,'mock'
        with patch.object(eng,'process_vocal',side_effect=fake_process):
            _,report,_=eng.render_mix([{'path':str(path)}],return_details=True,vocal_space_amount=0,
                           tuning={'key':'C','scale':'Mayor','strength':80,'auto_key':True})
        assert 'PROTECCION:' in report
        assert calls==[False] or calls[0] is False,calls

if __name__=='__main__':
    test_auto_analysis();test_independent_tuning_switches();test_ui();test_key_protection()
    print('V4.0 OK')


def test_auto_key_is_passed_to_individual_voice():
    from music_analysis import MusicResult
    import tempfile
    from unittest.mock import patch
    sr=eng.SR; t=np.arange(sr*1.2)/sr
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'Voz_Principal.wav'
        sf.write(path,(.03*np.sin(2*np.pi*250*t)).astype(np.float32),sr)
        called=[]
        def fake_process(audio,rate,tuning,kind):
            called.append(tuning);return audio,'mock'
        prediction=MusicResult('D','Menor natural',.84,'fiable',120.,.90,'pulso',('Piano.wav',))
        with patch('music_analysis.analyze_music',return_value=prediction):
            with patch.object(eng,'process_vocal',side_effect=fake_process):
                _,report,details=eng.render_mix([{'path':str(path)}],return_details=True,vocal_space_amount=0,
                                     tuning={'key':'C','scale':'Cromatica','strength':65,'auto_key':True})
        assert len(called)==1 and called[0]['key']=='D' and called[0]['scale']=='Menor natural'
        assert details['music_analysis']['key']=='D'
        assert 'detectada' in report

"""Pruebas V4.1: confirmación, ruteo independiente y motores opcionales."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import numpy as np
import soundfile as sf
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import mixer_engine as eng
import music_analysis as ma
from music_confirmation import resolve_choice


def _make_stems(directory, sr=22050, seconds=12):
    p=Path(directory)
    t=np.arange(sr*seconds)/sr
    piano=np.zeros(len(t),np.float32)
    # Fa menor: F-Ab-C con Bb y Eb repartidas.
    notes=[174.614,207.652,261.626,311.127,233.082]
    for n in range(int(seconds*2)):
        a=int(n*.5*sr); b=min(a+int(.42*sr),len(t))
        q=np.arange(b-a)/sr
        env=np.sin(np.pi*np.arange(len(q))/max(1,len(q)))**2
        piano[a:b]+=(.07*np.sin(2*np.pi*notes[n%len(notes)]*q)*env).astype('float32')
    drums=np.zeros(len(t),np.float32)
    for i in range(int(seconds*91/60)):
        j=int(i*60/91*sr)
        if j+100>len(t):break
        drums[j:j+100]+=(.3*np.exp(-np.arange(100)*.052)).astype('float32')
    voice=(.04*np.sin(2*np.pi*233.08*t)).astype('float32')
    sf.write(p/'Piano.wav',piano,sr)
    sf.write(p/'Drums.wav',drums,sr)
    sf.write(p/'Voz_Principal.wav',voice,sr)
    sf.write(p/'Voz_L.wav',voice*.6,sr)
    sf.write(p/'Voz_R.wav',voice*.6,sr)
    return [str(p/n) for n in ['Piano.wav','Drums.wav','Voz_Principal.wav','Voz_L.wav','Voz_R.wav']]


def test_known_f_minor_91_auto_has_authority():
    a={'key':'F','scale':'Mayor','key_confidence':.9,'bpm':92.3,'bpm_confidence':.99}
    choice=resolve_choice(a,'Automático','F','Menor natural',91,True)
    assert (choice['key'],choice['scale'],choice['bpm'])==('F','Menor natural',91.)
    assert choice['mode']=='Automático'
    with pytest.raises(ValueError):resolve_choice({},'Automático','F','Menor natural',91,False)
    choice2=resolve_choice(a,'Automático','F','Menor natural',91,False)
    assert choice2['scale']=='Mayor' and choice2['bpm']==92.3


def test_consent_is_bound_to_audio_and_settings():
    with tempfile.TemporaryDirectory() as td:
        files=_make_stems(td,seconds=3)
        with patch.object(ma,'analyze_music',return_value=ma.MusicResult('F','Mayor',.8,'orientativa',92.3,.95,'estimado')):
            view,state,msg=app.preview_hybrid(files,None,False,False)
        assert 'Tonalidad candidata' in view
        consent,text=app.confirm_hybrid(files,None,'Automático','F','Menor natural',91,True,state,False,False)
        assert consent['confirmed'] and consent['key']=='F' and consent['bpm']==91
        app._validate_hybrid(consent,files,None,'Automático','F','Menor natural',91,True,False,False)
        with pytest.raises(Exception):app._validate_hybrid(consent,files,None,'Automático','F','Menor natural',92,True,False,False)
        with pytest.raises(Exception):app._validate_hybrid(consent,files,None,'Automático','F','Menor natural',91,False,False,False)
        blocked,text=app.confirm_hybrid(files,None,'Automático','F','Menor natural',91,False,{},False,False)
        assert not blocked and 'Sin confirmar' in text
        with patch.object(app,'process',return_value='ok') as called:
            app.process_ui(files,None,'C','Mayor',75,7,tune_lead=True,tune_left=True,tune_right=False,
                    music_mode='Automático',confirmed_key='F',confirmed_scale='Menor natural',confirmed_bpm=91,
                    prefer_confirmed=True,music_analysis_state=state,music_approval_state=consent,
                    use_essentia=False,use_beat_this=False,progress=None)
            args,kwargs=called.call_args
            assert args[2]['key']=='F' and args[2]['scale']=='Menor natural'
            assert kwargs['music_plan']['confirmed']
            assert kwargs['vocal_space_bpm']==91


def test_engine_uses_confirmation_for_each_vocal():
    with tempfile.TemporaryDirectory() as td:
        files=_make_stems(td, sr=eng.SR, seconds=2)
        source=[{'path':f} for f in files[2:]]
        plan=dict(confirmed=True,key='F',scale='Menor natural',bpm=91.,source='referencia',analysis={'key':'F','scale':'Mayor','bpm':92.3})
        calls=[]
        def capture(x,sr,tuning,kind):
            calls.append((kind,tuning and (tuning['key'],tuning['scale']) or False))
            return x,'simulada'
        with patch.object(eng,'process_vocal',side_effect=capture):
            mix,report,details=eng.render_mix(source,return_details=True,
                tuning=dict(strength=70, auto_key=True,tune_lead=True,tune_left=True,tune_right=False),
                music_plan=plan,vocal_space_amount=0)
        assert len(calls)==3 and calls[0][1]==('F','Menor natural')
        assert calls[1][1]==('F','Menor natural') and calls[2][1] is False
        assert '91.0 BPM' in report
        assert details['music_analysis']['bpm']==92.3 # Predicción reportada sin prevalecer
        assert np.all(np.isfinite(mix))


def test_hybrid_backends_with_fake_model_votes():
    with tempfile.TemporaryDirectory() as td:
        files=_make_stems(td)
        def fake_ess(path,mode):
            if mode=='clave':return {'keys':[{'key':'F','scale':'minor','strength':.8,'profile':n} for n in ['krumhansl','edmm','temperley']]}
            return {'bpm':91.0,'beats':[i*60/91 for i in range(20)]}
        with patch.object(ma,'_essentia_available_path',side_effect=fake_ess), \
             patch.object(ma,'_beat_this_tempo',return_value=(91.,.9)), \
             patch.object(ma.importlib.util,'find_spec',side_effect=lambda name: object() if name=='beat_this' else None):
            result=ma.analyze_music(files,use_essentia=True,use_beat_this=True)
        assert any('Essentia' in p and 'ejecutado' in p for p in result.providers),result.providers
        assert any('Beat This' in p and 'ejecutado' in p for p in result.providers),result.providers
        assert result.bpm is not None and abs(result.bpm-91)<3, result.summary()
        assert 'NO porcentajes' in result.summary()
        assert 'Voz_Principal.wav' not in result.source_names


def test_automatic_fallback_and_ui():
    with tempfile.TemporaryDirectory() as td:
        files=_make_stems(td,seconds=5)
        result=ma.analyze_music(files,use_essentia=False,use_beat_this=False)
        assert len(result.providers)>=3 and 'desactivado' in result.providers[1]
        assert not any('Voz_' in name for name in result.source_names)
    ui=app.build_ui()
    labels={c.get('props',{}).get('label') for c in ui.get_config_file()['components']}
    assert {'Modo de análisis musical','Tonalidad conocida','Escala conocida','BPM conocido','Confirmación de tonalidad y BPM'}.issubset(labels)
    if False:print('unused')

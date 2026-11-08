"""V3.9: profundidad separada, predelay, BPM, ruteo y etapa pos-escalon."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import numpy as np
import soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import mixer_engine as eng
from vocal_space import PROFILES, render_space


def sample(sr, nsec=2.6):
    t = np.arange(int(sr*nsec))/sr
    s = (.08*np.sin(2*np.pi*210*t) + .018*np.sin(2*np.pi*420*t)).astype(np.float32)
    s[:int(sr*.12)] = 0
    return np.stack([s*np.sqrt(.5),s*np.sqrt(.5)])


def test_role_profiles():
    assert set(PROFILES) == {'principal','laterales','apoyo','dobles','coros'}
    assert PROFILES['principal'].pre_ms > PROFILES['laterales'].pre_ms
    assert PROFILES['coros'].verb > PROFILES['principal'].verb
    src=sample(eng.SR)
    groups={r:src.copy() for r in PROFILES}
    output, note=render_space(groups,eng.SR,amount=45.,bpm=120.,lead=src)
    assert set(output)==set(groups)
    assert '120 BPM' in note
    for name, wet in output.items():
        assert wet.shape==src.shape and np.all(np.isfinite(wet)),name
        assert np.max(np.abs(wet))<1.
        assert np.sqrt(np.mean(wet**2)) < np.sqrt(np.mean(src**2))*.26
        # Sin contaminacion antes del primer fragmento vocal.
        assert np.max(np.abs(wet[:, :int(eng.SR*.12)])) < 1e-5
    assert not np.allclose(output['principal'], output['coros'], atol=1e-5)
    off,note=render_space(groups,eng.SR,amount=0.,bpm=0.)
    assert off=={} and 'desactivado' in note
    dry=src.copy()
    render_space({'principal':src},eng.SR,amount=25,bpm=0.)
    assert np.array_equal(src,dry), 'Nunca debe tocar el audio seco'
    for bpm in [-1,53,231,np.nan]:
        try: render_space(groups,eng.SR,amount=45,bpm=bpm)
        except ValueError: pass
        else: raise AssertionError(f'BPM invalido admitido: {bpm}')


def test_lateral_stereo_and_eq():
    s=sample(eng.SR)
    x=np.stack([s[0],np.zeros(s.shape[1],np.float32)])
    wet,note=render_space({'laterales':x},eng.SR,amount=45.,bpm=100.)
    y=wet['laterales']
    assert np.sqrt(np.mean(y[0]**2))>np.sqrt(np.mean(y[1]**2))*.8
    assert np.any(y[1]),'Reverb estereo/eco discreto debe dar algo de amplitud'


def test_interface():
    ui=app.build_ui()
    labels={c.get('props',{}).get('label') for c in ui.get_config_file()['components']}
    for label in ('Reverb + delay vocal','Profundidad general · 0–100','BPM manual (0 = detección automática)'):
        assert label in labels,label
    called=[]
    def fake(*args,**kwargs):
        called.append(kwargs);return 'OK'
    with patch.object(app,'process',side_effect=fake):
        app.process_ui([],None,'C','Mayor',0,7,progress=None,space_enabled=False,space_amount=80.,space_bpm=115.)
        app.process_ui([],None,'C','Mayor',0,7,progress=None,space_enabled=True,space_amount=55.,space_bpm=0.)
    assert called[0]['vocal_space_amount']==0
    assert called[1]['vocal_space_amount']==55
    assert called[0]['vocal_space_bpm']==115


def test_mix_stage_and_buses():
    sr=eng.SR
    s=sample(sr,2.4)[0]
    with tempfile.TemporaryDirectory() as folder:
        p=Path(folder)
        for name,scale in [('Voz_Principal.wav',1.),('Voz_L.wav',.70),('Voz_B_R.wav',.65),('Coros.wav',.48),('Dobles.wav',.53),('Bass.wav',.45)]:
            sf.write(p/name,s*scale,sr,subtype='FLOAT')
        tracks=[{'path':str(p/name)} for name in ('Voz_Principal.wav','Voz_L.wav','Voz_B_R.wav','Coros.wav','Dobles.wav','Bass.wav')]
        with patch.object(eng,'process_vocal',side_effect=lambda x,sr,tuning=False,kind=None:(x,'test')):
            mix_on,report,details=eng.render_mix(tracks,return_details=True,vocal_space_amount=45.,vocal_space_bpm=120.,backing_step_db=7.)
            mix_off,off_report,off_details=eng.render_mix(tracks,return_details=True,vocal_space_amount=0.,vocal_space_bpm=120.,backing_step_db=7.)
        assert 'FX vocales - principal' in details['buses']
        assert 'FX vocales - laterales' in details['buses']
        assert 'FX vocales - coros' in details['buses']
        assert 'FX vocales - dobles' in details['buses']
        assert not any('FX vocales' in k for k in off_details['buses'])
        assert 'Voces L/R (grupo)' in report and 'Profundidad vocal 45' in report
        assert 'sin BPM' not in report
        assert mix_on.shape==mix_off.shape and np.all(np.isfinite(mix_on))
        # El balance seco se conserva; los FX son retornos adicionales separables.
        for stem_name in ('Voces','Bajo'):
            np.testing.assert_allclose(details['buses'][stem_name]/details['mix_gain'],off_details['buses'][stem_name]/off_details['mix_gain'],rtol=1e-5,atol=1e-5)
        # Ninguna cola previa al escalon: el L/R ya recibio reducción en su origen.
        wet_rms = np.sqrt(np.mean(details['buses']['FX vocales - laterales'].astype(float)**2))
        dry_rms = np.sqrt(np.mean(details['buses']['Voces'].astype(float)**2))
        assert wet_rms < dry_rms*.25

if __name__=='__main__':
    test_role_profiles(); test_lateral_stereo_and_eq(); test_interface(); test_mix_stage_and_buses()
    print('V3.9 OK')

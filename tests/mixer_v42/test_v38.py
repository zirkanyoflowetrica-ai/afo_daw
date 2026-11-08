"""V3.8: interruptores independientes de PSOLA para voz principal, L, R y centro."""
from pathlib import Path
from unittest.mock import patch
import sys
import tempfile
import numpy as np
import soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mixer_engine as eng
import app


def test_flags():
    kinds=[
        ('lead','Voz principal',False,'Original / centro'),
        ('left','Voz lateral (_L/_R)',True,'Izquierda'),
        ('left_b','Voz de apoyo (_B)',True,'50% izquierda'),
        ('right','Voz lateral (_L/_R)',True,'Derecha'),
        ('right_b','Voz de apoyo (_B)',True,'50% derecha'),
        ('center_b','Voz de apoyo (_B)',False,'Original / centro'),
        ('chorus','Coros',False,'Original / centro'),
    ]
    cases=[
        ({'tune_lead':True}, {'lead'}),
        ({'tune_lead':False,'tune_left':True}, {'left','left_b'}),
        ({'tune_lead':False,'tune_right':True}, {'right','right_b'}),
        ({'tune_lead':False,'tune_center_backings':True}, {'center_b','chorus'}),
        ({'tune_lead':False}, set()),
        ({'tune_lead':True, 'tune_left':True, 'tune_right':True,'tune_center_backings':True}, {k[0] for k in kinds}),
    ]
    for flags,expected in cases:
        tuning=dict(key='C',scale='Mayor',strength=70, tune_left=False,tune_right=False,tune_center_backings=False)
        tuning.update(flags)
        result={name for name,typ,lat,pos in kinds if eng._should_tune_vocal(tuning,typ,lat,pos)}
        assert result==expected,(flags,result,expected)
        assert not any(eng._should_tune_vocal(dict(tuning, strength=0),kind,lat,pos) for _,kind,lat,pos in kinds)
    # Contratos anteriores (API antigua) sin regresión.
    previous=dict(key='C',scale='Mayor',strength=70)
    assert eng._should_tune_vocal(previous,'Voz principal',False,'Original / centro')
    assert not eng._should_tune_vocal(previous,'Voz de apoyo (_B)',True,'50% izquierda')
    previous['include_backings']=True
    assert eng._should_tune_vocal(previous,'Voz de apoyo (_B)',True,'50% izquierda')
    assert eng._should_tune_vocal(previous,'Coros',False,'Original / centro')
    print('Interruptores separados, V3.7 compatible y cero desactiva: OK')


def test_ui_wiring():
    # La interfaz debe crear 4 casillas visibles, sin el viejo interruptor global.
    ui=app.build_ui()
    assert ui is not None
    cfg=ui.get_config_file()
    labels=[comp.get('props',{}).get('label','') for comp in cfg['components']]
    for title in ('Voz principal · centro','Voces L · izquierda','Voces R · derecha','Dobles/coros/_B · centro'):
        assert title in labels,(title, labels)
    assert not any('Afinar también dobles' in (label or '') for label in labels)
    captured=[]
    def fake_process(files,reference,tuning,progress,with_review=False,backing_step_db=7,**kwargs):
        captured.append((tuning,backing_step_db,with_review))
        return 'OK'
    with patch.object(app,'process',side_effect=fake_process):
        app.process_ui([],None,'D','Menor natural',65,8,False,True,False,False,progress=None)
        app.process_ui([],None,'D','Menor natural',0,8,True,True,True,True,progress=None)
    assert captured[0][0]['tune_lead'] is False
    assert captured[0][0]['tune_left'] is True
    assert captured[0][0]['tune_right'] is False
    assert captured[0][1]==8 and captured[0][2] is True
    assert captured[1][0] is False
    print('Panel, conexión API, cero apagado: OK')


def test_real_engine_routing():
    sr=eng.SR
    t=np.arange(sr*2, dtype=np.float64)/sr
    x=(.08*np.sin(2*np.pi*237*t)).astype('float32')
    names=['Voz_principal.wav','Voz_L.wav','Voz_R.wav','Voz_B_L.wav','Voz_B_R.wav','Voz_B.wav','Guitarra_L.wav']
    with tempfile.TemporaryDirectory() as d:
        for j,name in enumerate(names):
            sf.write(Path(d)/name,x*(1-j*.08),sr,subtype='FLOAT')
        received=[]
        def fake_vocal(data,sr,tuning=False,kind='Voz principal'):
            received.append((kind, isinstance(tuning,dict)))
            return data,'test afinacion' if isinstance(tuning,dict) else 'test sin afinacion'
        config=dict(key='C',scale='Mayor',strength=70, tune_lead=False,tune_left=True,tune_right=False,tune_center_backings=False)
        with patch.object(eng,'process_vocal',side_effect=fake_vocal):
            _,report,details=eng.render_mix([{'path':str(Path(d)/name)} for name in names],tuning=config,return_details=True)
        voice_map=[(t['name'],t['kind']) for t in details['tracks']]
        assert len(received)==6,(received,voice_map)
        # El orden de pistas originales conserva el orden de procesamiento.
        assert [v for _,v in received]==[False,True,False,True,False,False],received
        assert 'Voz_R.wav: test sin afinacion' in report
        assert 'Voz_L.wav: test afinacion' in report
        assert all(v['kind'] != 'Voz principal' for v in details['tracks'] if v['name']=='Guitarra_L.wav')
        print('Enrutamiento del motor: lead NO, L SI, R NO, _B_L SI, _B_R NO, _B NO; guitarras sin afinar: OK')


if __name__=='__main__':
    test_flags()
    test_ui_wiring()
    test_real_engine_routing()
    print('V3.8 TESTS OK')

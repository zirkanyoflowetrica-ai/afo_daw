"""V3.6: comprobar nivel relativo, suma de voces L/R y prioridad del lead."""
from pathlib import Path
import sys
import tempfile
import numpy as np
import pyloudnorm as pyln
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mixer_engine as eng


def main():
    sr=eng.SR
    meter=pyln.Meter(sr)
    n=sr*4
    t=np.arange(n,dtype=np.float64)/sr
    lead=(.2*np.sin(2*np.pi*180*t)).astype('float32')
    # Dos tomas coherentes deben ser controladas juntas, no -7 dB cada una.
    side_l=(.27*np.sin(2*np.pi*190*t)).astype('float32')
    side_r=(.27*np.sin(2*np.pi*194*t)).astype('float32')
    main_st=eng.stereo(lead[None,:], 'Original / centro')
    lateral_pair=eng.stereo(side_l[None,:],'50% izquierda')+eng.stereo(side_r[None,:],'50% derecha')
    lead_level=eng._lufs(main_st,meter)
    for step in [5.,7.,8.,10.]:
        b={'Voces laterales':lateral_pair.copy()}
        report=[]
        mixback=eng._blend_backing(b,main_st,meter,report,step_db=step)
        delta=lead_level-eng._lufs(mixback,meter)
        # Ducking es un dB adicional, no levanta los apoyos sobre el target.
        assert step-.1<=delta<=step+1.2,(step,delta,report)
        assert np.max(abs(b['Voces']-mixback))<1e-7
    # Una pista L/R no identificada como voz sigue siendo instrumento.
    for name,kind,expected in [
        ('Voz_L.wav','Voz principal',True),
        ('vocal_R.wav','Voz principal',True),
        ('Voz_B_L.wav','Voz de apoyo (_B)',True),
        ('Guitarra_L.wav','Guitarra ritmica',False),
        ('Bass_R.wav','Bajo',False),
        ('Voz.wav','Voz principal',False),
        ('Voz_B.wav','Voz de apoyo (_B)',False),
    ]:
        assert eng.is_lateral_voice(name,kind)==expected,(name,kind)
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)
        samples={
            'Voz_principal.wav':lead,
            'Voz_L.wav':side_l,
            'Voz_R.wav':side_r,
            'Voz_B_L.wav':side_l*.8,
            'Voz_B.wav':side_l*.5,
            'Guitarra_L.wav':(.10*np.sin(2*np.pi*330*t)).astype('float32'),
        }
        for name,x in samples.items():sf.write(p/name,x,sr,subtype='FLOAT')
        tracks=[dict(path=str(p/name)) for name in samples]
        mixed, report, details=eng.render_mix(tracks,return_details=True,backing_step_db=7.5)
        assert all(np.isfinite(mixed.ravel()))
        assert 'Voces L/R (grupo)' in report and '7.5 dB bajo principal' in report
        assert 'Voces _B centro' in report
        byname={t['name']:t for t in details['tracks']}
        assert byname['Voz_L.wav']['kind']=='Voz lateral (_L/_R)'
        assert byname['Voz_R.wav']['kind']=='Voz lateral (_L/_R)'
        assert byname['Voz_L.wav']['position']=='Izquierda'
        assert byname['Voz_R.wav']['position']=='Derecha'
        assert byname['Voz_B_L.wav']['position']=='50% izquierda'
        assert byname['Voz_B.wav']['position']=='Original / centro'
        assert byname['Guitarra_L.wav']['kind']=='Guitarra ritmica'
        assert abs(mixed-sum(details['buses'].values())).max()<3e-6
        print('Balance por grupos, paneo, distincion instrumentos, reconstruccion:', 'OK')
        # La interfaz debe aceptar el slider y los archivos originales de Windows.
        import app
        assert app.VERSION in ('3.6', '3.7', '3.8', '3.9')
        ui=app.build_ui()
        assert ui is not None
        assert 'Voz lateral (_L/_R)' in app.inspect_files([str(p/'Voz_L.wav')])
        print('Interfaz, inspeccion y control 5-10 dB:', 'OK')
    print('V3.6 TESTS OK')


if __name__=='__main__':main()

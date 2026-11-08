"""Regresiones de canciones largas, edición, envíos y entrega por plataformas."""
import sys,os,tempfile,zipfile,json
from pathlib import Path
import numpy as np
import soundfile as sf
import pyloudnorm as pyln
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mixer_engine as eng
import vocal_dsp
from track_tools import level_phrases,repair_vocal,level_match_pair,section_balance,resonance_eq
from mastering_tools import limit_linked
from audio_intelligence import identify_audio

def main():
    sr=eng.SR
    meter=pyln.Meter(sr)
    rng=np.random.default_rng(2026)
    # Esta duración activaba salto=4 y convertía agudos de 10 kHz en medios.
    t=np.arange(sr*180,dtype=np.float64)/sr
    long=(.1*np.sin(2*np.pi*10000*t)).astype('float32')[None,:]
    a=eng.analyze(long,meter)
    assert a.bands['air']>.98 and abs(a.centroid_hz-10000)<20,a
    identity=identify_audio(long,sr)
    assert identity.kind=='Overheads / Platillos',identity
    print(f'180 s: centroide {a.centroid_hz:.1f} Hz, aire {a.bands["air"]:.2%}; clasificacion {identity.kind}')
    del long,t
    t=np.arange(sr*6)/sr
    voice=(.15*np.sin(2*np.pi*180*t)+.035*np.sin(2*np.pi*540*t)).astype('float32')[None,:]
    opposite=np.concatenate([voice,-voice])
    analysis=eng.analyze(opposite,meter)
    assert analysis.rms>.05 and analysis.bands['low']>.5
    print('Analisis estereo: no pierde energia al existir oposicion de canales')
    stepped=voice.copy()
    stepped[:,:sr*2]*=.4
    before=np.std(stepped[0,sr*4:sr*5])/np.std(stepped[0,sr//2:sr])
    levelled,note=level_phrases(stepped,sr)
    after=np.std(levelled[0,sr*4:sr*5])/np.std(levelled[0,sr//2:sr])
    assert 1<after<before,(before,after)
    gain=np.abs(levelled[abs(stepped)>1e-5]/stepped[abs(stepped)>1e-5])
    assert gain.min()>=10**(-3.001/20) and gain.max()<=10**(1.501/20)
    assert np.array_equal(level_phrases(np.zeros_like(voice),sr)[0],np.zeros_like(voice))
    clicked=voice.copy();clicked[0,sr]=.95
    repaired,note=repair_vocal(clicked,sr)
    assert abs(repaired[0,sr]-voice[0,sr])<.01,note
    assert np.max(abs(repaired-voice))<.01
    print(f'Nivelacion: contraste {before:.2f} -> {after:.2f}; clic aislado reparado')
    # Un único filtro de graves, con y sin fundamental fiable.
    original_board=vocal_dsp.Pedalboard
    counts=[]
    def board(chain):
        counts.extend(isinstance(item,eng.HighpassFilter) for item in chain)
        return original_board(chain)
    vocal_dsp.Pedalboard=board
    try:
        vocal_dsp.process_vocal(voice,sr,False)
    finally:
        vocal_dsp.Pedalboard=original_board
    assert sum(counts)==1,counts
    spec=eng.analyze(voice,meter)
    assert not any(isinstance(p,eng.HighpassFilter) for p in eng._adaptive_chain('Voz principal',spec))
    noisy=(rng.normal(0,.04,len(t))+.03*np.sin(2*np.pi*3150*t)).astype('float32')[None,:]
    treated,resonance_note=resonance_eq(noisy,sr,'Voz principal')
    assert 'resonancia candidata' in resonance_note,resonance_note
    tone_before=abs(np.mean(noisy[0]*np.exp(-2j*np.pi*3150*t)))
    tone_after=abs(np.mean(treated[0]*np.exp(-2j*np.pi*3150*t)))
    assert tone_after<tone_before*.99,(tone_before,tone_after)
    print('Resonancia estrecha: recorte aplicado y tono reducido')
    bass=(.12*np.sin(2*np.pi*65*t)+.05*np.sin(2*np.pi*1000*t)).astype('float32')[None,:]
    kick=(.2*np.sin(2*np.pi*65*t)*np.exp(-25*(t%.5))).astype('float32')[None,:]
    bass_buses={'Bajo':eng.stereo(bass,'Original / centro')}
    original_bass=bass_buses['Bajo'].copy()
    eng._kick_duck_bass(bass_buses,eng.stereo(kick,'Original / centro'),[])
    def harmonic(x,f):return abs(np.mean(x[0]*np.exp(-2j*np.pi*f*t)))
    assert harmonic(bass_buses['Bajo'],65)<harmonic(original_bass,65)*.99
    assert abs(harmonic(bass_buses['Bajo'],1000)/harmonic(original_bass,1000)-1)<.005
    print('Ducking kick/bajo: reduce graves y conserva armonica de 1 kHz')
    # Contexto musical variable: máximo +/-0.8 dB, no cambian proporciones L/R.
    stereo=eng.stereo(voice,'Original / centro')
    bed=stereo.copy();bed[:,sr*3:]*=4
    buses={'Voces':stereo.copy(),'Guitarras':bed}
    curve,_=section_balance(buses,stereo,sr)
    assert curve is not None and np.max(abs(20*np.log10(curve)))<=.8001
    assert np.array_equal(buses['Voces'][0],buses['Voces'][1])
    # El limitador enlazado conserva la relación entre canales, acota GR y duración.
    driven=np.concatenate([voice*7,voice*2.8])
    limited,stats=limit_linked(driven,sr,-2,3)
    assert stats['max_reduction_db']<=3.001,stats
    assert limited.shape==driven.shape
    assert np.max(abs(limited[1]-limited[0]*.4))<1e-5
    for preset,config in eng.MASTERS.items():
        out,stats=eng.master(stereo,preset)
        assert stats['true_peak']<=config['tp']+.001,stats
        assert stats['max_reduction_db']<=config['max_gr']+.001,stats
        assert np.all(np.isfinite(out))
        print(f'{preset}: {stats["lufs"]:.2f} LUFS, {stats["true_peak"]:.2f} dBTP, GR {stats["max_reduction_db"]:.2f} dB')
    short=stereo[:,:sr//10]*10
    _,short_stats=eng.master(short,'Plataformas (-14 LUFS, -2 dBTP)')
    assert short_stats['true_peak']<=-2.0,short_stats
    assert 'corto' in short_stats['note']
    # A/B usa el mismo LUFS sin cambiar los arrays originales.
    a,b,note=level_match_pair(stereo,stereo*.2,meter)
    assert abs(eng._lufs(a,meter)-eng._lufs(b,meter))<.01
    # Completa la mezcla con voces, instrumentos, apoyo y referencia.
    with tempfile.TemporaryDirectory() as folder:
        p=Path(folder)
        samples={'Voz_principal.wav':voice[0],'Voz_B_L.wav':voice[0]*1.8,
                 'Guitarra_R.wav':(.07*np.sin(2*np.pi*330*t)).astype('float32'),
                 'Bass.wav':(.08*np.sin(2*np.pi*82*t)).astype('float32')}
        for name,x in samples.items(): sf.write(p/name,x,sr,subtype='FLOAT')
        ref=p/'Referencia.wav';sf.write(ref,stereo.T,sr)
        paths=[str(p/name) for name in samples]
        tracks=[{'path':name} for name in paths]
        for reference in (None,str(ref)):
            mix,report,details=eng.render_mix(tracks,reference_path=reference,return_details=True)
            reconstruction=sum(details['buses'].values())
            error=float(np.max(abs(reconstruction-mix)))
            assert error<3e-6,error
            assert len(details['tracks'])==len(tracks)
            print(f'Buses reconstruyen mezcla: referencia {bool(reference)}, error {error:.3g}')
        # Si se silencia el bus _B en su balance final, tampoco queda su reverb previa.
        baseline=eng.render_mix([tracks[0]])[0]
        blend=eng._blend_backing
        def muted(buses,lead,meter,report,step_db=7.0,fx_groups=None):
            backing=blend(buses,lead,meter,report,step_db,fx_groups=fx_groups)
            if fx_groups is not None:
                fx_groups.clear()
            if backing is not None:
                buses['Voces']-=backing
                return np.zeros_like(backing)
            return None
        eng._blend_backing=muted
        try: without_leak=eng.render_mix(tracks[:2])[0]
        finally: eng._blend_backing=blend
        assert np.max(abs(baseline-without_leak))<1e-6
        print('Reverb _B: sigue la reduccion final sin envio residual previo')
        import app
        original=os.getcwd();os.chdir(p)
        try:
            result=app.process(paths,str(ref),False,progress=lambda *a,**k:None,with_review=True)
        finally:os.chdir(original)
        session=result[-1]
        outputs=result[-3]
        assert len(session)==len(tracks)+1
        for label in session:
            ap,bp,note=app.review_track(label,session)
            assert Path(ap).is_file() and Path(bp).is_file()
            ax,_=sf.read(ap,always_2d=True);bx,_=sf.read(bp,always_2d=True)
            assert abs(meter.integrated_loudness(ax)-meter.integrated_loudness(bx))<.05,label
        assert app.review_track('inexistente',session)[:2]==(None,None)
        archive=Path(outputs[0])
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            assert 'master_plataformas.wav' in z.namelist()
            manifest=json.loads(z.read('sesion.json'))
            assert manifest['version']==app.VERSION
            assert len(manifest['tracks'])==len(tracks)
            assert len(manifest['masters'])==4
            assert len([n for n in z.namelist() if n.startswith('pistas_procesadas_pre_bus/')])==4
        dest=archive.parent
        platform,_=sf.read(dest/'master_plataformas.wav',always_2d=True)
        assert eng._true_peak_db(platform.T)<=-2.0
        bus_files=list((dest/'buses_finales').glob('*.wav'))
        total=sum(sf.read(f,always_2d=True)[0] for f in bus_files)
        unmastered,_=sf.read(dest/'mezcla_sin_master.wav',always_2d=True)
        assert np.max(abs(total-unmastered))<4e-6
        for f in (dest/'pistas_procesadas_pre_bus').glob('*.wav'):
            assert sf.info(f).subtype=='FLOAT'
        print(f'Sesion completa: {len(outputs)} descargas; A/B, stems float32, buses y ZIP OK')
    print('V3.3 TESTS OK')

if __name__=='__main__':main()

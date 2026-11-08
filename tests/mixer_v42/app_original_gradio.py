"""Interfaz local compacta; exportación y comparación por sesión de usuario."""
from __future__ import annotations
from runtime_setup import ROOT, CACHE, logger, check_space
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
import numpy as np
import pyloudnorm as pyln
import gradio as gr
import mixer_engine as eng
from track_tools import level_match_pair
from scale_tuner import KEYS,SCALES
from mix_templates import (DEFAULT_TEMPLATE, GUIDE_ONLY, GUIDE_MODES, PROFILES,
                           recommendations, export_guide)

VERSION='4.2'
PLATFORM='Plataformas (-14 LUFS, -2 dBTP)'

def _paths(files):
    return [str(f if isinstance(f, (str,Path)) else f.name) for f in (files or [])]

def safe_name(name):
    return re.sub(r'[^a-zA-Z0-9_\-]','_',Path(name).stem)[:55].strip('_') or 'pista'

def inspect_files(files):
    paths=_paths(files)
    out=['Previsión por nombre; el audio se analiza al mezclar.']
    for path in paths[:eng.MAX_TRACKS]:
        p=Path(path)
        kind = eng.guess_type(p.name)
        position=eng.backing_position(p.name) if eng.is_backing_voice(p.name) else eng.pan_from_filename(p.name)
        if eng.is_lateral_voice(p.name, kind) and kind != 'Voz de apoyo (_B)':
            kind = 'Voz lateral (_L/_R)'
        out.append(f'{p.name} | {kind} | {position}')
    if len(paths)>eng.MAX_TRACKS:
        out.append(f'Máximo {eng.MAX_TRACKS} stems.')
    return '\n'.join(out)

def preview_mix_guide(files, template_key=DEFAULT_TEMPLATE):
    names=[Path(path).name for path in _paths(files)[:eng.MAX_TRACKS]]
    try:
        return recommendations(template_key,names)[0]
    except (ValueError, OSError) as exc:
        return f'No se pudo generar la guía: {exc}'


def review_track(choice,session):
    item=(session or {}).get(choice)
    if not item:
        return None,None,'Selecciona una pista después de mezclar.'
    return item['a'],item['b'],item['note']

def process(files,reference,tuning=False,progress=gr.Progress(),with_review=False,
            backing_step_db=eng.BACKING_STEP_DEFAULT_DB, vocal_space_amount=45., vocal_space_bpm=0., auto_music_bpm=False, music_source_path=None, music_plan=None,
            mix_template=DEFAULT_TEMPLATE, template_mode=GUIDE_ONLY):
    paths=_paths(files)
    if not paths:
        raise gr.Error('Sube al menos un stem.')
    if len(paths)>eng.MAX_TRACKS:
        raise gr.Error(f'Solo se admiten {eng.MAX_TRACKS} stems.')
    reference_path=_paths([reference])[0] if reference else None
    try:
        check_space(paths,Path.cwd())
        logger.info('Inicio de mezcla: %s pistas; afinacion=%s',len(paths),tuning)
        mix,report,details=eng.render_mix([{'path':p} for p in paths],reference_path=reference_path,
            return_details=True,progress=progress,tuning=tuning,backing_step_db=backing_step_db,
            vocal_space_amount=vocal_space_amount, vocal_space_bpm=vocal_space_bpm,
            auto_music_bpm=auto_music_bpm, music_source_path=music_source_path, music_plan=music_plan,
            mix_template=mix_template, template_mode=template_mode)
        dest=Path('salida')/f'{safe_name(paths[0])}_{datetime.now():%Y%m%d_%H%M%S_%f}'
        mix_path=eng.save_wav(dest/'mezcla_sin_master.wav',mix)
        files_out=[mix_path]
        master_paths=[]
        platform_audio=None
        master_stats={}
        for k,preset in enumerate(eng.MASTERS):
            progress((k+1,len(eng.MASTERS)),desc=f'Masterizando: {preset}')
            audio,stats=eng.master(mix,preset)
            filename='master_plataformas.wav' if preset==PLATFORM else 'master_'+re.sub(r'[^a-zA-Z0-9]+','_',preset).strip('_')+'.wav'
            master_paths.append(eng.save_wav(dest/filename,audio))
            master_stats[preset]=stats
            if preset==PLATFORM:
                platform_audio=audio
            report+=(f"\n{preset}: {stats['lufs']:.1f} LUFS; {stats['true_peak']:.2f} dBTP estimado; "
                     f"limitador max. {stats.get('max_reduction_db',0):.1f} dB, P95 {stats.get('p95_reduction_db',0):.1f} dB; "
                     f"crest {stats.get('crest_db',0):.1f} dB; variacion RMS entre ventanas 3 s {stats.get('window_range_db',0):.1f} dB; {stats['note']}")
        files_out.extend(master_paths)
        ref_master=None
        if details['reference_lufs'] is not None:
            target=float(np.clip(details['reference_lufs'],-16.,-9.))
            audio,stats=eng.master(mix,'Comercial (-11 LUFS)',target_lufs=target)
            ref_master=eng.save_wav(dest/'master_segun_referencia.wav',audio)
            files_out.append(ref_master)
            report+=f"\nMaster de referencia: objetivo {target:.1f}; resultado {stats['lufs']:.1f} LUFS y {stats['true_peak']:.2f} dBTP estimado."
        meter=pyln.Meter(eng.SR)
        review={}
        track_manifest=[]
        for i,item in enumerate(details['tracks'],1):
            progress((i,len(details['tracks'])),desc=f'Exportando y preparando A/B: {item["name"]}')
            stem=f'{i:02d}_{safe_name(item["name"])}'
            processed=eng.save_wav(dest/'pistas_procesadas_pre_bus'/f'{stem}.wav',item['audio'],subtype='FLOAT')
            files_out.append(processed)
            original=eng.stereo(eng.load_stem(item['path']),'Original / centro')
            a,b,note=level_match_pair(original,item['audio'],meter)
            a_path=eng.save_wav(dest/'comparacion'/f'{stem}_A_original.wav',a)
            b_path=eng.save_wav(dest/'comparacion'/f'{stem}_B_procesada.wav',b)
            files_out.extend([a_path,b_path])
            label=f'{i:02d} · {item["name"]}'
            review[label]=dict(a=a_path,b=b_path,note=f'{item["kind"]} · {item["position"]}\n{item["note"]}\n{note}. Pista seca antes de buses y efectos compartidos.')
            track_manifest.append(dict(name=item['name'],kind=item['kind'],position=item['position'],file=f'pistas_procesadas_pre_bus/{stem}.wav',decisions=item['note']))
        for i,(name,audio) in enumerate(details['buses'].items(),1):
            files_out.append(eng.save_wav(dest/'buses_finales'/f'{i:02d}_{safe_name(name)}.wav',audio,subtype='FLOAT'))
        for i,(label,audio) in enumerate(details['derived'].items(),1):
            files_out.append(eng.save_wav(dest/'drums_separados_aproximados'/f'{i:02d}_{safe_name(label)}.wav',audio,subtype='FLOAT'))
        if reference_path and details['reference_lufs'] is not None and platform_audio is not None:
            ref_audio=eng.stereo(eng.load_stem(reference_path),'Original / centro')
            a,b,note=level_match_pair(ref_audio,platform_audio,meter)
            ap=eng.save_wav(dest/'comparacion'/'referencia_A.wav',a)
            bp=eng.save_wav(dest/'comparacion'/'master_plataformas_B.wav',b)
            files_out.extend([ap,bp])
            review['Referencia / master plataformas']=dict(a=ap,b=bp,note=note+'. A = referencia; B = tu master. No se alinean arreglos ni tempos.')
        guide_md, guide_json = export_guide(dest, mix_template, details['tracks'])
        files_out.extend([guide_md,guide_json])
        report += f"\n\nPLANTILLA DE GUÍA: {PROFILES[mix_template]['name']} ({template_mode}). "
        report += 'Revisa guia_mezcla_por_stems.md dentro del ZIP: recomendaciones y decisiones reales por pista.'
        report+='\n\nMaster plataformas: -14 LUFS orientativos; techo -2 dBTP estimado; hasta 3 dB de limitacion. No garantiza una sonoridad identica en todos los servicios.'
        report+='\nPistas individuales: secas antes de buses, FLOAT 32 bits. Buses finales: incluyen balance, ducking, EQ compartida y FX separados; suman la mezcla sin master. Masters: PCM 24 bits / 44.1 kHz.'
        report+='\nLa variacion RMS entre ventanas no es LRA certificada. Comparaciones A/B son copias al mismo volumen para escuchar; no son los stems de produccion.'
        report+=f'\nCarpeta: {dest.resolve()}'
        report_path=dest/'informe.txt'
        report_path.write_text(report,encoding='utf-8')
        manifest=dict(version=VERSION,samplerate=eng.SR,tracks=track_manifest,masters=master_stats,dynamics=details['dynamics'],stem_stage='pre_bus_dry',bus_stage='final_sum_to_unmastered_mix',
                      mix_template=dict(key=mix_template,name=PROFILES[mix_template]['name'],mode=template_mode),
                      music_analysis=details.get('music_analysis'),
                      music_selection=({key:music_plan.get(key) for key in ('key','scale','bpm','mode','source','confirmed')} if music_plan else None))
        def clean(value):
            if isinstance(value,dict): return {k:clean(v) for k,v in value.items()}
            if isinstance(value,list): return [clean(v) for v in value]
            if isinstance(value,float) and not np.isfinite(value): return None
            return value
        manifest_path=dest/'sesion.json'
        manifest_path.write_text(json.dumps(clean(manifest),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        files_out.extend([str(report_path.resolve()),str(manifest_path.resolve())])
        archive=dest/'sesion_completa.zip'
        progress((1,1),desc='Preparando ZIP de la sesión')
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
            for file in files_out:
                z.write(file,Path(file).relative_to(dest.resolve()).as_posix())
        # Evita copiar al cache todos los stems/buses y A/B de una vez.
        # Los individuales siguen dentro del ZIP; A/B se sirve bajo demanda.
        files_out=[str(archive.resolve()),mix_path,*master_paths,*([ref_master] if ref_master else []),str(report_path.resolve()),str(manifest_path.resolve()),guide_md,guide_json]
        logger.info('Sesion terminada: %s',dest.resolve())
        result=(report,mix_path,*master_paths,ref_master,files_out)
        if with_review:
            return (*result,gr.Dropdown(choices=list(review),value=None,interactive=bool(review)),review)
        return result
    except Exception as e:
        logger.exception('Fallo de mezcla')
        hint='Falta memoria: prueba menos stems o una seccion mas corta.' if isinstance(e,MemoryError) else str(e)
        raise gr.Error(f'No se pudo completar la sesion: {hint}. Detalles en logs/errores.log') from e

def preview_music(files, instrumental_file=None, use_essentia=True, use_beat_this=True):
    paths=_paths(files)
    music_path=_paths([instrumental_file])[0] if instrumental_file else None
    if not paths and not music_path:
        return 'Sube stems instrumentales primero; se ignoran las voces.'
    try:
        from music_analysis import analyze_music
        return analyze_music(paths,instrumental_source=music_path, use_essentia=use_essentia, use_beat_this=use_beat_this).summary()
    except Exception as exc:
        logger.exception('Error en análisis musical')
        return f'No se pudo analizar el instrumental: {exc}'



def preview_hybrid(files, music_file, use_essentia=True, use_beat_this=True):
    paths = _paths(files)
    music_path = _paths([music_file])[0] if music_file else None
    if not paths and not music_path:
        return 'Carga instrumentos antes de analizar.', {}, 'Faltan fuentes musicales.'
    try:
        from music_analysis import analyze_music
        from music_confirmation import signature
        result = analyze_music(paths,instrumental_source=music_path,
                               use_essentia=bool(use_essentia), use_beat_this=bool(use_beat_this))
        data = result.as_dict()
        # Se comprueba que la vista previa corresponde a estos archivos.
        data['source_signature']=signature(paths,music_path,{'essentia':bool(use_essentia),'beat_this':bool(use_beat_this)})
        return result.summary(), data, 'Análisis preparado. Comprueba la propuesta y pulsa «Confirmar».'
    except Exception as exc:
        logger.exception('Falló el preanálisis híbrido')
        return f'No se pudo analizar: {exc}', {}, 'No confirmado.'


def confirm_hybrid(files, music_file, mode, key, scale, bpm, prefer_known,
                   analysis, use_essentia=True, use_beat_this=True):
    """Autoriza solo una combinación concreta de archivos + controles."""
    from music_confirmation import signature, resolve_choice
    paths=_paths(files)
    music_path=_paths([music_file])[0] if music_file else None
    analysis=analysis or {}
    try:
        if mode != 'Manual':
            expected=signature(paths,music_path,{'essentia':bool(use_essentia),'beat_this':bool(use_beat_this)})
            if not analysis or analysis.get('source_signature') != expected:
                raise ValueError('Primero pulsa «Analizar música» con estos archivos.')
        choice=resolve_choice(analysis,mode,key,scale,bpm,bool(prefer_known))
        choices=dict(mode=mode,key=key,scale=scale,bpm=float(bpm),prefer=bool(prefer_known),
                     essentia=bool(use_essentia),beat_this=bool(use_beat_this))
        choice['signature']=signature(paths,music_path,choices)
        choice['confirmed']=True
        return choice, (f'CONFIRMADO: {choice["key"]} {choice["scale"]}, {choice["bpm"]:.1f} BPM. '
                        f'{choice["source"]}. Afinación permitida por canales separados.')
    except (ValueError, OSError) as exc:
        return {}, f'Sin confirmar: {exc}'


def _validate_hybrid(approval,files,music_file,mode,key,scale,bpm,prefer,essentia,beat_this):
    from music_confirmation import signature
    if not approval or not approval.get('confirmed'):
        raise gr.Error('Primero analiza y confirma la tonalidad y el BPM antes de mezclar.')
    values=dict(mode=mode,key=key,scale=scale,bpm=float(bpm),prefer=bool(prefer),
                essentia=bool(essentia),beat_this=bool(beat_this))
    music_path=_paths([music_file])[0] if music_file else None
    if signature(_paths(files),music_path,values) != approval.get('signature'):
        raise gr.Error('Cambiaste archivos o configuración tras confirmar. Vuelve a analizar y confirmar.')
    return dict(approval)

def process_ui(files, reference, key, scale, strength, backing_step_db,
               tune_lead=True, tune_left=False, tune_right=False,
               tune_center_backings=False, space_enabled=True,
               space_amount=45., space_bpm=0., key_mode="Manual", auto_bpm=False, music_file=None,
               music_mode=None, confirmed_key="F", confirmed_scale="Menor natural", confirmed_bpm=91,
               prefer_confirmed=True, music_analysis_state=None, music_approval_state=None,
               use_essentia=True, use_beat_this=True,
               mix_template=DEFAULT_TEMPLATE, template_mode=GUIDE_ONLY, progress=gr.Progress()):
    """Cada interruptor decide qué tomas vocales entran en PSOLA.

    Intensidad 0 mantiene todo sin afinar, aunque los interruptores estén activos.
    No altera la ecualización, los FX ni el escalón de voces L/R.
    """
    strength = float(strength)
    music_plan = None
    if music_approval_state is not None:
        music_plan = _validate_hybrid(music_approval_state,files,music_file,
                         music_mode,confirmed_key,confirmed_scale,confirmed_bpm,
                         prefer_confirmed,use_essentia,use_beat_this)
        key,scale=music_plan['key'],music_plan['scale']
        space_bpm=music_plan['bpm']
        key_mode='Manual'
        auto_bpm=False
    tuning = dict(
        key=key, scale=scale, strength=strength,
        auto_key=(key_mode=="Automático"),
        tune_lead=bool(tune_lead), tune_left=bool(tune_left),
        tune_right=bool(tune_right),
        tune_center_backings=bool(tune_center_backings),
    ) if strength > 0 else False
    return process(files, reference, tuning, progress, with_review=True,
                   backing_step_db=backing_step_db,
                   vocal_space_amount=float(space_amount) if space_enabled else 0.,
                   vocal_space_bpm=float(space_bpm or 0),
                   auto_music_bpm=bool(auto_bpm) and not float(space_bpm or 0),
                   music_source_path=_paths([music_file])[0] if music_file else None,
                   music_plan=music_plan,
                   mix_template=mix_template, template_mode=template_mode)

def build_ui():
    with gr.Blocks(title=f'Mezclador Automático V{VERSION}',analytics_enabled=False) as demo:
        gr.Markdown(f'## Mezclador automático · V{VERSION}\n`_B` centro · `_B_L/_B_R` 50% de su lado · `Voz_L/Voz_R` a su lado. Voces laterales en segundo plano.')
        session=gr.State({})
        with gr.Row():
            files=gr.File(label='Stems sincronizados · hasta 30',file_count='multiple',file_types=['audio'],type='filepath',height=120,scale=2)
            reference=gr.File(label='Referencia opcional para mastering',file_count='single',file_types=['audio'],type='filepath',height=120,scale=1)
        with gr.Accordion('Guías de mezcla · Trap y rap (orientativas)',open=False):
            gr.Markdown('Escoge un **enfoque de producción**, no un preset de EQ. Cada stem tendrá su propia guía y se identificarán capas múltiples de sintes, guitarras, pianos y voces. Las recomendaciones también se exportan al ZIP.')
            with gr.Row():
                mix_template=gr.Dropdown(label='Plantilla artística',choices=[(v['name'],k) for k,v in PROFILES.items()],value=DEFAULT_TEMPLATE,scale=2)
                template_mode=gr.Dropdown(label='Uso en el motor',choices=GUIDE_MODES,value=GUIDE_ONLY,scale=2)
            gr.Markdown('**Solo guía:** audio idéntico al motor V4.1, más informe. **Guía + balance muy sutil:** hasta ±1 dB orientativo por stem en función del estilo y número de capas, sin cambiar afinación, EQ, reverb, escalón L/R o mastering.')
            guide_view=gr.Markdown(value=recommendations(DEFAULT_TEMPLATE)[0])
            with gr.Row():
                guide_update=gr.Button('Revisar guías de mis stems',variant='secondary',size='sm')
            guide_update.click(preview_mix_guide,inputs=[files,mix_template],outputs=guide_view,api_name='guia_por_stems')
            mix_template.change(preview_mix_guide,inputs=[files,mix_template],outputs=guide_view)
            files.change(preview_mix_guide,inputs=[files,mix_template],outputs=guide_view)
        with gr.Accordion('Análisis musical · BPM y tonalidad',open=False):
            music_file=gr.File(label='Beat o instrumental completo (opcional, solo para análisis)',file_count='single',file_types=['audio'],type='filepath',height=70)
            gr.Markdown('Si los stems musicales tienen nombres poco claros, carga aquí el beat completo para detectar la tonalidad y el BPM. **No se sumará a la mezcla.**')
            music_mode=gr.Dropdown(label='Modo de análisis musical', choices=['Automático','Manual','Asistido'], value='Automático')
            with gr.Row():
                confirmed_key=gr.Dropdown(label='Tonalidad conocida',choices=KEYS,value='F',scale=1)
                confirmed_scale=gr.Dropdown(label='Escala conocida',choices=['Mayor','Menor natural','Menor armonica','Pentatonica mayor','Pentatonica menor','Cromatica'],value='Menor natural',scale=2)
                confirmed_bpm=gr.Number(label='BPM conocido',value=91,minimum=50,maximum=230,precision=1,scale=1)
            prefer_confirmed=gr.Checkbox(label='Priorizar tonalidad y BPM conocidos (Fa menor / 91 BPM inicialmente)',value=True)
            with gr.Row():
                use_essentia=gr.Checkbox(label='Essentia (Linux o WSL, opcional)',value=True)
                use_beat_this=gr.Checkbox(label='Beat This! (modelo adicional, opcional)',value=True)
            gr.Markdown('**Automático:** analiza instrumentos y presenta propuestas; si priorizas la referencia conocida, la respeta incluso cuando los detectores discrepan. **Asistido:** comparas ambos resultados. **Manual:** solo usa tus valores. En todos los casos debes confirmar antes de mezclar. Las dependencias avanzadas son opcionales y el informe explica si faltan.')
            music_analysis_state=gr.State({})
            music_approval_state=gr.State({})
            music_confirmation_status=gr.Textbox(label='Confirmación de tonalidad y BPM',value='Pendiente: analiza y confirma antes de mezclar.',lines=2,interactive=False)
            confirm_button=gr.Button('Confirmar tonalidad y BPM para esta mezcla',variant='secondary')

        with gr.Accordion('Afinación vocal · PSOLA (independiente por voz)', open=True):
            gr.Markdown('Afinación PSOLA **por archivo separado**. Puedes detectar la tonalidad del instrumental o fijarla tú. Confirma la tonalidad y BPM en el panel de análisis antes de afinar.')
            key_mode=gr.Dropdown(label='Escala de afinación',choices=['Automático','Manual'],value='Automático',visible=False)
            with gr.Row():
                key=gr.Dropdown(label='Tónica manual',choices=KEYS,value='F',scale=1,visible=False)
                scale=gr.Dropdown(label='Escala vocal manual',choices=list(SCALES),value='Menor natural',scale=2,visible=False)
                strength=gr.Slider(label='Intensidad · 0–100 %',minimum=0,maximum=100,value=0,step=1,scale=2)
            key_mode.change(lambda m: (gr.update(visible=(m=='Manual')),gr.update(visible=(m=='Manual'))),inputs=key_mode,outputs=[key,scale])
            with gr.Row():
                tune_lead=gr.Checkbox(label='Voz principal · centro',value=True,scale=1)
                tune_left=gr.Checkbox(label='Voces L · izquierda',value=False,scale=1)
                tune_right=gr.Checkbox(label='Voces R · derecha',value=False,scale=1)
                tune_center_backings=gr.Checkbox(label='Dobles/coros/_B · centro',value=False,scale=1)
            gr.Markdown('En modo **Manual** se usan la tónica y escala elegidas arriba. En **Automático** se analizan instrumentos, pero la selección final debe estar confirmada en el panel musical.')
            gr.Markdown('Las opciones L/R también incluyen `_B_L` y `_B_R`. La opción de apoyos al centro no afecta a L/R. PSOLA puede omitir pistas si detecta riesgo de artefactos.')
        with gr.Row():
            backing_step_db=gr.Slider(label='Escalón vocal L/R · dB bajo voz principal',minimum=5,maximum=10,value=eng.BACKING_STEP_DEFAULT_DB,step=.5,scale=2)
            gr.Markdown('**7 dB:** acompañamiento presente. **10 dB:** más al fondo. El control se aplica al grupo L/R después del procesamiento.')
        with gr.Accordion('Espacio vocal · Reverb y delay por tipo',open=False):
            gr.Markdown('Cada rol tiene una profundidad propia: principal delante, L/R en los lados, `_B` detrás, coros amplios. Son **envíos independientes filtrados**, posteriores al afinador y al escalón.')
            with gr.Row():
                space_enabled=gr.Checkbox(label='Reverb + delay vocal',value=True,scale=1)
                space_amount=gr.Slider(label='Profundidad general · 0–100',minimum=0,maximum=100,value=45,step=1,scale=2)
                space_bpm=gr.Number(label='BPM manual (0 = detección automática)',value=0,minimum=0,maximum=230,precision=0,scale=1,visible=False)
                auto_bpm=gr.Checkbox(label='Detectar BPM automáticamente',value=True,scale=1,visible=False)
            gr.Markdown('Los delays siguen el BPM que confirmaste en **Análisis musical**. Los ajustes previos se conservan internamente para compatibilidad.')
            gr.Markdown('**Principal:** predelay largo para conservar claridad. **L/R:** más ambiente y ecos laterales. **_B centrales:** espacio intermedio. **Dobles:** delay corto. **Coros:** más profundidad. Si introduces BPM entre 55 y 230 se sincronizan los ecos a 1/8 y 1/4.')
        with gr.Row():
            preview_button=gr.Button('Analizar tonalidad y BPM antes de mezclar',variant='secondary')
            music_preview=gr.Textbox(label='Análisis instrumental (orientativo)',lines=3,max_lines=5,interactive=False)
        preview_button.click(preview_hybrid,inputs=[files,music_file,use_essentia,use_beat_this],
                             outputs=[music_preview,music_analysis_state,music_confirmation_status],api_name='analizar_musica')
        confirm_button.click(confirm_hybrid,
                             inputs=[files,music_file,music_mode,confirmed_key,confirmed_scale,confirmed_bpm,
                                     prefer_confirmed,music_analysis_state,use_essentia,use_beat_this],
                             outputs=[music_approval_state,music_confirmation_status],api_name='confirmar_musica')
        go=gr.Button('Mezclar y preparar masters',variant='primary')
        with gr.Row():
            mix_audio=gr.Audio(label='Mezcla sin master',type='filepath')
            platform=gr.Audio(label='Plataformas · −14 LUFS / −2 dBTP',type='filepath')
        with gr.Accordion('Revisar cada pista · original / procesada',open=False):
            choice=gr.Dropdown(label='Pista · escucha individual',choices=[],interactive=False)
            with gr.Row():
                original=gr.Audio(label='A · Original al mismo volumen',type='filepath')
                processed=gr.Audio(label='B · Procesada al mismo volumen',type='filepath')
            decisions=gr.Textbox(label='Decisiones',lines=2,max_lines=5,interactive=False)
        with gr.Accordion('Otros masters y referencia',open=False):
            with gr.Row():
                others=[gr.Audio(label=name,type='filepath') for name in eng.MASTERS if name!=PLATFORM]
                ref_out=gr.Audio(label='Master de referencia',type='filepath')
        with gr.Accordion('Informe y previsión',open=False):
            detected=gr.Textbox(label='Previsión',lines=2,max_lines=5,interactive=False)
            report=gr.Textbox(label='Informe',lines=5,max_lines=12,interactive=False)
        downloads=gr.Files(label='Descarga · sesión ZIP, masters, pistas y buses',height=150)
        files.change(inspect_files,inputs=files,outputs=detected)
        ordered={name:widget for name,widget in zip([n for n in eng.MASTERS if n!=PLATFORM],others)}
        ordered[PLATFORM]=platform
        go.click(process_ui,inputs=[files,reference,key,scale,strength,backing_step_db,tune_lead,tune_left,tune_right,tune_center_backings,space_enabled,space_amount,space_bpm,key_mode,auto_bpm,music_file,music_mode,confirmed_key,confirmed_scale,confirmed_bpm,
                                  prefer_confirmed,music_analysis_state,music_approval_state,use_essentia,use_beat_this,mix_template,template_mode],outputs=[report,mix_audio,*[ordered[n] for n in eng.MASTERS],ref_out,downloads,choice,session],api_name='mezclar')
        choice.change(review_track,inputs=[choice,session],outputs=[original,processed,decisions],api_name='revisar_pista')
    return demo

if __name__=='__main__':
    logger.info('Inicio V%s; cache=%s',VERSION,CACHE)
    build_ui().queue(default_concurrency_limit=1).launch(inbrowser=True,show_error=True,allowed_paths=[str((Path.cwd()/'salida').resolve())])

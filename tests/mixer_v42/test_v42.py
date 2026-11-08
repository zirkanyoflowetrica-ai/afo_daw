"""V4.2: plantillas orientativas, sin cambios accidentales en el motor."""
import json
import sys
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mixer_engine as eng
from mix_templates import (PROFILES, DEFAULT_TEMPLATE, GUIDE_ONLY, SOFT_GUIDE,
                           recommendations, inventory, style_trims, export_guide,
                           role_for)

NAMES = [
    'Voz_Principal.wav','Voz_L.wav','Voz_R.wav','Voz_B_L.wav',
    '808.wav','Kick.wav','Snare.wav','Clap.wav','HiHat.wav',
    'Synth_Lead.wav','Synth_Pad.wav','Synth_Arp.wav',
    'Guitar_Rhythm_L.wav','Guitar_Rhythm_R.wav','Piano.wav',
]


def test_nine_profiles_include_different_per_track_recommendations():
    assert len(PROFILES) == 9
    docs = []
    for name in PROFILES:
        markdown, entries = recommendations(name, NAMES)
        assert 'Guía por stem (15)' in markdown
        assert 'Capa 1 de 3' in markdown
        assert 'Capa 2 de 2' in markdown
        assert 'Voz L/R' in markdown
        assert '808' in markdown
        assert PROFILES[name]['name'] in markdown
        docs.append(markdown)
    assert len(set(docs)) == len(PROFILES)


def test_layering_and_voice_roles():
    items = inventory(NAMES)
    by_name = {d['name']:d for d in items}
    assert by_name['Voz_B_L.wav']['role'] == 'side_vocal'
    assert by_name['Voz_L.wav']['role'] == 'side_vocal'
    assert by_name['Synth_Lead.wav']['layer_count'] == 3
    assert by_name['Synth_Pad.wav']['layer_count'] == 3
    assert by_name['Guitar_Rhythm_R.wav']['layer_count'] == 2
    assert by_name['Piano.wav']['layer_count'] == 1
    assert role_for('Guitarra_R.wav','Guitarra ritmica') == 'guitar_rhythm'
    assert role_for('Voz_B.wav','Voz de apoyo (_B)') == 'backing_vocal'


def test_silent_and_weak_trims_do_not_raise():
    from types import SimpleNamespace
    item = inventory(['Synth_Lead.wav','Synth_Pad.wav'])[0]
    for key in PROFILES:
        assert -1 <= style_trims(key, item, SimpleNamespace(silent=False,rms=.02)) <= 1
        assert style_trims(key,item,SimpleNamespace(silent=True,rms=.02)) == 0
        assert style_trims(key,item,SimpleNamespace(silent=False,rms=.0001)) <= 0


def test_guides_export_markdown_and_json(tmp_path):
    files=[dict(name=n,kind=eng.guess_type(n),note='EQ automática y control dinámico') for n in NAMES]
    md,js=export_guide(tmp_path,'rap_moderno',files)
    assert Path(md).is_absolute() and Path(js).is_absolute()
    data=json.loads(Path(js).read_text(encoding='utf-8'))
    assert len(data['stems']) == 15
    assert 'EQ automática' in Path(md).read_text(encoding='utf-8')
    assert data['stems'][-1]['group']=='pianos/teclados'


def test_bad_profile_rejected():
    with pytest.raises(ValueError):
        recommendations('fake')


def test_engine_guia_only_leaves_audio_identical(tmp_path,monkeypatch):
    # Señales cortas, repetibles y sin herramientas externas de IA.
    monkeypatch.chdir(tmp_path)
    sr=eng.SR
    t=np.arange(sr*2,dtype=np.float32)/sr
    audios={
        'Kick.wav':.03*np.sin(2*np.pi*60*t)*(np.sin(2*np.pi*2*t)**10),
        'Synth_Lead.wav':.025*np.sin(2*np.pi*440*t),
        'Synth_Pad.wav':.02*np.sin(2*np.pi*330*t),
    }
    tracks=[]
    for name,audio in audios.items():
        path=tmp_path/name
        sf.write(path,audio,sr)
        tracks.append({'path':str(path)})
    # El clasificador neural no debe intentar inferencias caras ni descargarse nada.
    monkeypatch.setattr('ai_classifier.recognize', lambda x,sr: None)
    y1,r1,d1=eng.render_mix(tracks,return_details=True,mix_template='trap_oscuro',template_mode=GUIDE_ONLY,vocal_space_amount=0)
    y2,r2,d2=eng.render_mix(tracks,return_details=True,mix_template='guitar_trap',template_mode=GUIDE_ONLY,vocal_space_amount=0)
    assert np.array_equal(y1,y2)
    assert d1['mix_template']=='trap_oscuro'
    assert d2['mix_template']=='guitar_trap'
    y3,r3,d3=eng.render_mix(tracks,return_details=True,mix_template='rage_hypertrap',template_mode=SOFT_GUIDE,vocal_space_amount=0)
    assert np.max(abs(y3)) < .99
    assert 'orientación estilística muy sutil' in r3
    assert not np.array_equal(y1,y3)

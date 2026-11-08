/* AllForOne — paneles del Mezclador Automático V4.2 dentro del lienzo modular.
 *
 * El mezclador se reparte en módulos del mismo lienzo, con la misma estructura visual que los
 * de la plantilla (cabecera negra, color por módulo, conectores, tiradores, Enfocar, ✕):
 *   mixia  Mezcla IA      stems, clasificación, guías trap/rap, MEZCLAR / REMEZCLAR
 *   afina  Afinador       análisis de tonalidad/BPM + confirmación + PSOLA por voz
 *   mastia Master IA      4 masters del V4.2 + master según referencia, LUFS/true peak, A/B
 *   antes  Antes/Después  comparación A/B por pista al mismo volumen
 * La lógica pesada vive en Python (mixer_v42, en un hilo de trabajo). Aquí solo se dibuja
 * y se envían comandos por el puente AFO.call(...).
 */
(function () {
  'use strict';
  if (typeof PANELS === 'undefined') return;

  /* ---------------- datos del mezclador (se reemplazan con los de Python al conectar) ---------------- */
  const D = window.AFO_MIXDATA = {
    profiles: [['trap_oscuro', 'Trap oscuro · contundente'], ['trap_melodico', 'Trap melódico · atmosférico'], ['trap_latino', 'Trap latino · urbano'],
      ['rage_hypertrap', 'Rage / hypertrap · energético'], ['drill', 'Drill · tenso y rítmico'], ['rap_moderno', 'Rap moderno · voz dominante'],
      ['boom_bap', 'Boom bap · orgánico'], ['guitar_trap', 'Guitar trap · emo rap'], ['minimal_trap', 'Trap minimalista · espacio y silencio']],
    modes: ['Solo guía (audio sin cambios)', 'Guía + balance muy sutil'],
    keys: ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'],
    scales: ['Cromatica', 'Mayor', 'Menor natural', 'Menor armonica', 'Pentatonica mayor', 'Pentatonica menor'],
    masters: ['Dinamico (-14 LUFS)', 'Comercial (-11 LUFS)', 'Fuerte (-8.5 LUFS)', 'Plataformas (-14 LUFS, -2 dBTP)'],
    types: ['Voz principal', 'Voz doble', 'Voz lateral (_L/_R)', 'Voz de apoyo (_B)', 'Coros', 'Drums', 'Kick', 'Snare', 'Hi-hat', 'Overheads / Platillos', 'Toms', 'Percusion',
      'Bajo', 'Guitarra acustica', 'Guitarra lead / solo', 'Guitarra ritmica', 'Piano', 'Pad / Cuerdas', 'Teclados / Synth', 'FX', 'Otro']
  };
  const ROLES = ['—', 'P', 'B', 'L', 'R', 'B_L', 'B_R'];

  /* ---------------- estado ---------------- */
  const MX = window.AFO_MX = {
    stems: [], reference: null, profile: 'trap_oscuro', mode: D.modes[0],
    busy: false, progress: 0, status: 'Arrastra tus stems o pulsa «+ Stems».', runs: [], run: null,
    tune: { mode: 'Automático', key: 'F', scale: 'Menor natural', bpm: 91, prefer: true, voices: { lead: true, l: false, r: false, b: false },
      analysis: null, confirmed: null, status: 'Pendiente: analiza y confirma antes de mezclar.' },
    master: { sel: 3, ab: 'B' },
    review: { sel: 0, ab: 'A' }
  };
  KV.mxStep = KV.mxStep ?? 40;     // 5..10 dB -> 0..100 (7 dB = 40)
  KV.mxSpace = KV.mxSpace ?? 45;   // profundidad 0..100
  KV.tnStr = KV.tnStr ?? 0;        // intensidad PSOLA 0..100
  const stepDb = () => 5 + KV.mxStep / 20;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const opt = (v, cur, label) => `<option value="${esc(v)}"${v == cur ? ' selected' : ''}>${esc(label ?? v)}</option>`;
  const KIND_COLOR = k => /Voz|Coros/.test(k) ? '#ffc233' : /Drum|Kick|Snare|Hi-hat|Overhead|Toms|Percu/.test(k) ? '#d4f26a' : /Bajo/.test(k) ? '#ff7a70' : /Guitarra|Piano|Pad|Teclado/.test(k) ? '#b79bff' : '#c9ccd2';

  /* ---------------- registro de los módulos en el lienzo ---------------- */
  const NEW = [['mixia', 'Mezcla IA', 'Auto-Mix V4.2', '#ff9f45', [2200, 1040, 760]],
    ['afina', 'Afinador', 'PSOLA AT-1', '#7ae7ff', [3060, 1040, 520]],
    ['mastia', 'Master IA', 'Master M-4', '#ff6b9a', [3680, 1040, 440]],
    ['antes', 'Antes / Después', 'A/B Comp', '#e6d3a3', [4220, 1040, 420]]];
  for (const [id, name, model, color, pos] of NEW) {
    if (!PANELS.some(p => p[0] === id)) PANELS.push([id, name, model]);
    PC[id] = color; POS[id] = pos.slice(); DEFAULT_POS[id] = pos.slice();
  }

  /* cables: Pistas → Mezcla IA → Master IA → Mezcla final ; Afinador → Mezcla IA ; Mezcla IA → Antes/Después */
  const _links2 = links;
  links = function () {
    const L = _links2();
    const add = (f, t) => { if (!hidden[f] && !hidden[t]) L.push({ key: f + '-' + t, f, t, c: PC[f] }); };
    add('pistas', 'mixia'); add('afina', 'mixia'); add('mixia', 'mastia'); add('mixia', 'antes'); add('mastia', 'master');
    return L;
  };

  /* ---------------- render ---------------- */
  function rMix() {
    const el = $('#b-mixia'); if (!el) return;
    const rows = MX.stems.map((s, i) => `<div class="afo-stem" style="--k:${KIND_COLOR(s.kind)}"><span>${String(i + 1).padStart(2, '0')}</span><b title="${esc(s.path)}">${esc(s.name)}</b>
      <select data-mxkind="${i}" aria-label="Tipo de ${esc(s.name)}">${D.types.map(t => opt(t, s.kind)).join('')}</select>
      <select data-mxrole="${i}" aria-label="Rol vocal de ${esc(s.name)}">${ROLES.map(r => opt(r, s.role || '—')).join('')}</select>
      <button data-mxdel="${i}" aria-label="Quitar ${esc(s.name)}">✕</button></div>`).join('');
    el.innerHTML = `<div class="vst"><b class="lcd">${String(MX.stems.length).padStart(2, '0')}/30</b><small>Stems sincronizados. Tipo y rol se detectan por el nombre (<code>_L</code>, <code>_R</code>, <code>_B</code>, <code>_B_L</code>…) y puedes corregirlos.</small></div>
      <div class="afo-drop" data-mxdrop="stems">⬇ Arrastra aquí tus stems<small>WAV · AIFF · FLAC · hasta 30 pistas</small></div>
      <div class="tb"><button data-mx="add">+ Stems</button><button data-mx="ref">${MX.reference ? '↺ Referencia: ' + esc(MX.reference.name) : '+ Referencia (opcional)'}</button><button data-mx="fromtracks">⇠ Usar pistas de audio</button>${MX.stems.length ? '<button data-mx="clear">Vaciar</button>' : ''}</div>
      <div class="afo-stems">${rows || '<p class="empty">Sin stems todavía.</p>'}</div>
      <div class="afo-row2"><label>Plantilla artística<select data-mxset="profile">${D.profiles.map(([k, n]) => opt(k, MX.profile, n)).join('')}</select></label>
      <label>Uso en el motor<select data-mxset="mode">${D.modes.map(m => opt(m, MX.mode)).join('')}</select></label></div>
      <div class="krow">${knob('mxStep', 'Escalón L/R', null, 40)}${knob('mxSpace', 'Espacio vocal', null, 45)}</div>
      <p class="hint" style="text-align:center"><b id="mxStepV">${stepDb().toFixed(1)} dB</b> bajo la voz principal · profundidad <b id="mxSpaceV">${Math.round(KV.mxSpace)}</b></p>
      <div class="afo-big"><button class="afo-go" data-mx="mix" ${MX.busy ? 'disabled' : ''}>MEZCLAR AUTOMÁTICAMENTE</button><button data-mx="remix" ${MX.busy || !MX.runs.length ? 'disabled' : ''}>↻ REMEZCLAR</button></div>
      <div class="afo-prog"><span style="--p:${MX.progress}%"></span></div><div class="afo-status" id="mxStatus">${esc(MX.status)}</div>
      ${MX.runs.length ? `<div class="afo-hist">${MX.runs.map((r, i) => `<button data-mxrun="${i}" aria-pressed="${MX.run === i}">#${i + 1} · ${esc(r.label)}</button>`).join('')}</div>` : ''}`;
  }

  function rTune() {
    const el = $('#b-afina'); if (!el) return;
    const T = MX.tune, c = T.confirmed;
    const v = (k, l) => `<button data-tnv="${k}" aria-pressed="${T.voices[k]}"><i></i>${l}</button>`;
    el.innerHTML = `<div class="afo-lcdbig"><div><small>${c ? 'CONFIRMADO' : 'SIN CONFIRMAR'}</small><b>${esc(c ? c.key : T.key)} ${esc((c ? c.scale : T.scale).replace('Menor natural', 'm').replace('Mayor', ''))}</b></div><div style="text-align:right"><small>BPM</small><b>${(+(c ? c.bpm : T.bpm)).toFixed(1)}</b></div></div>
      <div class="tabs">${['Automático', 'Asistido', 'Manual'].map(m => `<button data-tnmode="${m}" aria-pressed="${T.mode === m}">${m}</button>`).join('')}</div>
      <div class="afo-row3"><label>Tónica<select data-tnset="key">${D.keys.map(k => opt(k, T.key)).join('')}</select></label>
      <label>Escala<select data-tnset="scale">${D.scales.map(s => opt(s, T.scale)).join('')}</select></label>
      <label>BPM<input data-tnset="bpm" type="number" min="50" max="230" step="0.1" value="${T.bpm}" class="afo-num"></label></div>
      <div class="tb"><button data-tn="analyze">Analizar música</button><button data-tn="confirm">✔ Confirmar</button></div>
      <div class="afo-note" id="tnStatus">${esc(T.status)}</div>
      <div class="krow" style="margin-top:10px">${knob('tnStr', 'Intensidad', null, 0)}</div>
      <p class="hint" style="text-align:center"><b id="tnStrV">${Math.round(KV.tnStr)} %</b> · 0 % = sin afinación</p>
      <div class="afo-toggles">${v('lead', 'Voz principal · centro')}${v('l', 'Voces L · izquierda')}${v('r', 'Voces R · derecha')}${v('b', 'Dobles / coros / _B')}</div>
      <div class="afo-pitch" aria-label="Curva de afinación antes y después"><svg viewBox="0 0 300 70" preserveAspectRatio="none"><g stroke-width="2" fill="none">${[14, 28, 42, 56].map(y => `<line x1="0" x2="300" y1="${y}" y2="${y}" stroke="#ffffff1f"/>`).join('')}</g><text x="8" y="40" fill="#bdb398" font-size="11">Curva de tono antes/después: pendiente (V0.6)</text></svg></div>
      <p class="hint">PSOLA por archivo separado. Puede omitir pistas si detecta riesgo de artefactos.</p>`;
  }

  function rMaster() {
    const el = $('#b-mastia'); if (!el) return;
    const res = MX.run !== null && MX.runs[MX.run] ? MX.runs[MX.run].masters || {} : {};
    const names = [...D.masters, 'Según referencia'];
    el.innerHTML = `<div class="vst"><b class="lcd">${res[names[MX.master.sel]] ? (+res[names[MX.master.sel]].lufs).toFixed(1) + ' LUFS' : '-- LUFS'}</b><small>Masters adaptativos del V4.2: priorizan evitar clipping y exceso de limitación. Se informa el resultado real.</small></div>
      <div class="afo-presets">${names.map((n, i) => { const s = res[n]; const dis = i === 4 && !s;
        return `<button class="afo-preset" data-msel="${i}" aria-pressed="${MX.master.sel === i}" ${dis ? 'disabled' : ''}><span><b>${esc(n)}</b><small>${s ? `${(+s.lufs).toFixed(1)} LUFS · ${(+s.true_peak).toFixed(2)} dBTP · limitación ${(+(s.max_reduction_db || 0)).toFixed(1)} dB` : (i === 4 ? 'requiere referencia' : 'pendiente de mezcla')}</small></span><span class="lcd">${s ? (+s.lufs).toFixed(1) : '--.-'}</span></button>`; }).join('')}</div>
      <div class="afo-ab"><button data-mab="A" aria-pressed="${MX.master.ab === 'A'}">A · sin master</button><button data-mab="B" aria-pressed="${MX.master.ab === 'B'}">B · master</button></div>
      <div class="tb"><button data-ms="tracks">⇢ Enviar a Pistas</button><button data-ms="zip">Exportar sesión ZIP</button><button data-ms="folder">Abrir carpeta</button></div>`;
  }

  function rAB() {
    const el = $('#b-antes'); if (!el) return;
    const r = MX.run !== null ? MX.runs[MX.run] : null, list = r ? r.review || [] : [], cur = list[MX.review.sel];
    el.innerHTML = `<div class="vst"><b class="lcd">${list.length ? String(MX.review.sel + 1).padStart(2, '0') + '/' + String(list.length).padStart(2, '0') : '--/--'}</b><small>Original y procesada al mismo volumen. Pista seca antes de buses y efectos compartidos.</small></div>
      <label>Pista<select data-abset="sel" ${list.length ? '' : 'disabled'}>${list.length ? list.map((x, i) => opt(i, MX.review.sel, x.label)).join('') : '<option>Sin mezcla todavía</option>'}</select></label>
      <div class="afo-ab"><button data-abp="A" aria-pressed="${MX.review.ab === 'A'}" ${cur ? '' : 'disabled'}>▶ A · original</button><button data-abp="B" aria-pressed="${MX.review.ab === 'B'}" ${cur ? '' : 'disabled'}>▶ B · procesada</button><button data-abp="stop" ${cur ? '' : 'disabled'}>■</button></div>
      <div class="afo-note">${esc(cur ? cur.note : 'Tras mezclar verás aquí las decisiones tomadas para cada pista (tipo, posición, EQ, compresión, afinación, espacio).')}</div>`;
  }

  function renderAll() { rMix(); rTune(); rMaster(); rAB(); }
  window.AFO_renderMixer = renderAll;
  const _refresh = refresh;
  refresh = function () { _refresh(); renderAll(); };

  /* perillas propias: actualizar las lecturas */
  const _setK3 = setK;
  setK = function (e, n) {
    _setK3(e, n);
    const k = e.dataset.k;
    if (k === 'mxStep') { const x = $('#mxStepV'); if (x) x.textContent = stepDb().toFixed(1) + ' dB'; }
    if (k === 'mxSpace') { const x = $('#mxSpaceV'); if (x) x.textContent = Math.round(KV.mxSpace); }
    if (k === 'tnStr') { const x = $('#tnStrV'); if (x) x.textContent = Math.round(KV.tnStr) + ' %'; }
  };

  /* ---------------- comunicación con Python (mixer_service.py) ---------------- */
  const mixer = (cmd, data) => (window.AFO && AFO.bridge) ? AFO.call('mixer', cmd, JSON.stringify(data || {})) : Promise.resolve({ ok: false, pending: true });
  const request = () => ({
    stems: MX.stems.map(s => ({ path: s.path, name: s.name, kind: s.kind, role: s.role, auto_kind: s.auto_kind, auto_role: s.auto_role })),
    reference: MX.reference, profile: MX.profile, mode: MX.mode,
    profile_name: (D.profiles.find(p => p[0] === MX.profile) || [])[1],
    step_db: stepDb(), space: KV.mxSpace,
    tune: { mode: MX.tune.mode, key: MX.tune.key, scale: MX.tune.scale, bpm: MX.tune.bpm, prefer: MX.tune.prefer, strength: KV.tnStr, voices: MX.tune.voices }
  });
  window.AFO_mixerRequest = request;
  const addStems = list => {
    const known = new Set(MX.stems.map(s => s.path));
    const fresh = (list || []).filter(s => !known.has(s.path));
    MX.stems.push(...fresh.slice(0, Math.max(0, 30 - MX.stems.length)));
    MX.tune.confirmed = null;
    MX.status = `${MX.stems.length} stems listos.` + (fresh.length ? '' : ' (ya estaban en la lista)');
    rMix(); rTune();
  };
  const status = (txt, p) => { MX.status = txt; if (p !== undefined) MX.progress = p; const el = $('#mxStatus'); if (el) el.textContent = txt; const bar = $('#b-mixia .afo-prog span'); if (bar) bar.style.setProperty('--p', MX.progress + '%'); };
  const fail = r => { if (r && !r.ok && !r.cancelled) toast(r.pending ? 'Motor no conectado' : r.error); return r; };

  function onEvent(ev) {
    if (ev.type === 'progress') {
      if (ev.panel === 'afina') { MX.tune.status = ev.desc; const n = $('#tnStatus'); if (n) n.textContent = ev.desc; }
      else status(ev.desc || 'Trabajando…', ev.p);
    } else if (ev.type === 'analysis') {
      MX.tune.analysis = ev;
      if (ev.key && MX.tune.mode !== 'Manual') { MX.tune.key = ev.key; MX.tune.scale = ev.scale || MX.tune.scale; }
      if (ev.bpm && MX.tune.mode !== 'Manual') MX.tune.bpm = Math.round(ev.bpm * 10) / 10;
      MX.tune.status = ev.summary + '\n\nRevisa la propuesta y pulsa «Confirmar».';
      rTune();
    } else if (ev.type === 'done') {
      MX.runs.push(ev.run); MX.run = MX.runs.length - 1; MX.busy = false; MX.review.sel = 0;
      MX.status = `Mezcla #${MX.runs.length} lista en ${ev.run.seconds} s · ${Object.keys(ev.run.masters).length} masters · ${ev.run.review.length} pistas A/B` + (ev.run.tuned ? ' · afinada' : '');
      MX.progress = 100; renderAll(); toast('Mezcla automática terminada');
    } else if (ev.type === 'error') {
      MX.busy = false; MX.status = 'Error: ' + ev.error; MX.tune.status = ev.panel === 'analysis' ? 'Error: ' + ev.error : MX.tune.status;
      renderAll(); toast(ev.error);
    } else if (ev.type === 'idle') {
      if (MX.busy) { MX.busy = false; rMix(); }
    }
  }

  window.AFO_onMixerConnected = async function () {
    if (MX.connected || !(window.AFO && AFO.bridge)) return;
    MX.connected = true;
    AFO.bridge.mixerEvent.connect(s => { try { onEvent(JSON.parse(s)); } catch (e) { console.warn('[AFO] evento del mezclador', e); } });
    const info = await mixer('info');
    if (info.ok) {
      D.profiles = info.profiles.map(p => [p[0], p[1]]); D.modes = info.modes; D.keys = info.keys; D.scales = info.scales;
      D.masters = info.masters; D.types = info.types; MX.mode = D.modes[0];
      MX.ready = true;
    } else {
      MX.status = info.error; MX.ready = false;
    }
    renderAll();
  };

  /* Archivos soltados desde el Explorador (Qt entrega rutas reales) */
  window.AFO_onDrop = async function (paths, x, y) {
    $$('.afo-drop').forEach(z => z.classList.remove('over'));
    const el = document.elementFromPoint(x, y), panel = el && el.closest('.panel');
    if (panel && panel.id === 'p-mixia') {
      const r = fail(await mixer('describe', { paths }));
      if (r.ok) { addStems(r.stems); if (!r.stems.length) toast('Ningún archivo de audio compatible'); }
    } else if (AFO.engineOk) {
      const r = await AFO.call('importPaths', JSON.stringify(paths));
      if (r.ok) { r.tracks.forEach(t => AFO.addAudioTrack(t)); toast(r.tracks.length + ' archivo(s) importados en Pistas'); } else toast(r.error);
    }
  };

  /* ---------------- eventos de la interfaz ---------------- */
  document.addEventListener('click', async e => {
    const b = e.target.closest('button'); if (!b) return;
    const d = b.dataset;
    if (d.mx) {
      if (d.mx === 'clear') { MX.stems = []; MX.tune.confirmed = null; status('Lista vacía.', 0); rMix(); return; }
      if (d.mx === 'add' || d.mx === 'fromtracks') { const r = fail(await mixer(d.mx)); if (r.ok) addStems(r.stems); return; }
      if (d.mx === 'ref') { const r = fail(await mixer('ref')); if (r.ok) { MX.reference = r.reference; rMix(); } return; }
      if (d.mx === 'mix' || d.mx === 'remix') {
        const r = fail(await mixer(d.mx, request()));
        if (r.ok) { MX.busy = true; MX.progress = 1; MX.status = d.mx === 'remix' ? 'Remezclando (la mezcla anterior se conserva)…' : 'Mezclando…'; rMix(); }
        return;
      }
    } else if (d.mxdel !== undefined) { MX.stems.splice(+d.mxdel, 1); MX.tune.confirmed = null; rMix(); }
    else if (d.mxrun !== undefined) { MX.run = +d.mxrun; MX.review.sel = 0; renderAll(); }
    else if (d.tnmode) { MX.tune.mode = d.tnmode; MX.tune.confirmed = null; rTune(); }
    else if (d.tnv) { MX.tune.voices[d.tnv] = !MX.tune.voices[d.tnv]; rTune(); }
    else if (d.tn === 'analyze') {
      const r = fail(await mixer('analyze', request()));
      if (r.ok) { MX.tune.status = 'Analizando instrumentos…'; rTune(); }
    } else if (d.tn === 'confirm') {
      const r = await mixer('confirm', request());
      if (r.ok) { MX.tune.confirmed = r.confirmed; MX.tune.status = r.status; } else { MX.tune.confirmed = null; MX.tune.status = r.error || 'Sin confirmar'; }
      rTune();
    }
    else if (d.msel !== undefined) { MX.master.sel = +d.msel; rMaster(); }
    else if (d.mab) { MX.master.ab = d.mab; rMaster(); const r = fail(await mixer('listen', { what: 'master', sel: MX.master.sel, ab: d.mab, run: MX.run })); if (r.ok) toast('Escuchando ' + r.file); }
    else if (d.ms) {
      const r = fail(await mixer(d.ms, { run: MX.run, sel: MX.master.sel }));
      if (r.ok && d.ms === 'tracks') { r.tracks.forEach(t => AFO.addAudioTrack(t)); toast('Master añadido a Pistas'); }
      if (r.ok && d.ms === 'zip') toast('Sesión guardada: ' + r.path);
    }
    else if (d.abp) {
      if (d.abp !== 'stop') MX.review.ab = d.abp; rAB();
      const r = fail(await mixer('listen', { what: 'review', sel: MX.review.sel, ab: d.abp, run: MX.run }));
      if (r.ok && r.file) toast('Escuchando ' + r.file);
    }
  });
  document.addEventListener('change', e => {
    const t = e.target, d = t.dataset;
    if (d.mxkind !== undefined) { MX.stems[+d.mxkind].kind = t.value; rMix(); }
    else if (d.mxrole !== undefined) MX.stems[+d.mxrole].role = t.value;
    else if (d.mxset) MX[d.mxset] = t.value;
    else if (d.tnset) { MX.tune[d.tnset] = d.tnset === 'bpm' ? +t.value : t.value; MX.tune.confirmed = null; rTune(); }
    else if (d.abset) { MX.review.sel = +t.value; rAB(); }
  });
  /* realce visual al arrastrar sobre la zona (los archivos los entrega Qt con su ruta real) */
  document.addEventListener('dragover', e => { const z = e.target.closest && e.target.closest('[data-mxdrop]'); $$('.afo-drop').forEach(x => x.classList.toggle('over', x === z)); if (z) e.preventDefault(); });
  document.addEventListener('dragleave', e => { if (!e.relatedTarget) $$('.afo-drop').forEach(x => x.classList.remove('over')); });
  document.addEventListener('drop', () => $$('.afo-drop').forEach(x => x.classList.remove('over')));

  /* ---------------- montar en el lienzo ---------------- */
  loadLayout();   // vuelve a leer el diseño guardado, ahora con los módulos nuevos
  build();
  // Si el puente con Python se conectó antes de cargar este archivo, suscribirse ahora
  if (window.AFO && AFO.bridge) AFO_onMixerConnected();
})();

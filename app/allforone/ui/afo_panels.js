/* AllForOne — el Mezclador Automático V4.2 repartido por el lienzo modular.
 *
 * La plantilla no se reescribe: este archivo se carga después de su script y envuelve sus
 * funciones globales (pistas, mezcla, cinta, links, layoutPorts, defaultPin, refresh, setK).
 *
 *   audios  Audios           cargar archivos → cada uno crea su PISTA (y por tanto su tira)
 *   mezcla  Mezcla (consola) tiras reales + rol de voz por tira + MEZCLA AUTOMÁTICA fusionada:
 *                            al mezclar, faders y paneo se mueven a las decisiones reales
 *   afina   Afinador         tonalidad/BPM + PSOLA, con cable a la tira de cada voz que afina
 *   mastia  Master IA        4 masters + «según referencia», LUFS/true peak reales, A/B
 *   antes   Antes / Después  comparación A/B por pista al mismo volumen
 *
 * El trabajo pesado vive en Python (mixer_v42, hilo aparte). Aquí solo se dibuja y se envían
 * comandos por AFO.call(...). Ningún valor mostrado es inventado: los que llegan del mezclador
 * están medidos sobre el audio real.
 */
(function () {
  'use strict';
  if (typeof PANELS === 'undefined') return;

  /* ---------------- datos del mezclador (los reales llegan de Python al conectar) ---------------- */
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
  const ROLE_NAME = { '—': 'sin rol vocal', P: 'voz principal (centro)', B: 'voz de apoyo (centro)', L: 'voz lateral izquierda',
    R: 'voz lateral derecha', B_L: 'apoyo 50 % izquierda', B_R: 'apoyo 50 % derecha' };
  const VOCAL_KINDS = ['Voz principal', 'Voz doble', 'Voz lateral (_L/_R)', 'Voz de apoyo (_B)', 'Coros'];
  const KIND_FOR_ROLE = { P: 'Voz principal', B: 'Voz de apoyo (_B)', L: 'Voz lateral (_L/_R)', R: 'Voz lateral (_L/_R)',
    B_L: 'Voz de apoyo (_B)', B_R: 'Voz de apoyo (_B)' };
  const KIND_COLOR = k => /Voz|Coros/.test(k) ? '#ffc233' : /Drum|Kick|Snare|Hi-hat|Overhead|Toms|Percu/.test(k) ? '#d4f26a'
    : /Bajo/.test(k) ? '#ff7a70' : /Guitarra|Piano|Pad|Teclado/.test(k) ? '#b79bff' : '#c9ccd2';
  const KIND_SHORT = k => String(k || '').replace('Voz principal', 'Voz P').replace('Voz lateral (_L/_R)', 'Voz L/R')
    .replace('Voz de apoyo (_B)', 'Voz _B').replace('Overheads / Platillos', 'OH').replace('Guitarra ', 'Gtr ')
    .replace('Teclados / Synth', 'Synth').replace('Pad / Cuerdas', 'Pad');

  /* ---------------- estado ---------------- */
  const MX = window.AFO_MX = {
    items: [], uid: 0, reference: null, profile: 'trap_oscuro', mode: D.modes[0],
    busy: false, progress: 0, status: 'Carga audios en el módulo «Audios»: cada uno crea su pista y su tira.',
    runs: [], run: null, live: {}, working: -1,
    tune: { mode: 'Automático', key: 'F', scale: 'Menor natural', bpm: 91, prefer: true, voices: { lead: true, l: false, r: false, b: false },
      analysis: null, confirmed: null, status: 'Pendiente: analiza y confirma antes de afinar.' },
    master: { sel: 3, ab: 'B' },
    review: { sel: 0, ab: 'A' },
    take: { role: 'P' }
  };
  KV.mxStep = KV.mxStep ?? 40;     // 5..10 dB -> 0..100 (7 dB = 40)
  KV.mxSpace = KV.mxSpace ?? 45;   // profundidad 0..100
  KV.tnStr = KV.tnStr ?? 0;        // intensidad PSOLA 0..100
  const stepDb = () => 5 + KV.mxStep / 20;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const opt = (v, cur, label) => `<option value="${esc(v)}"${v == cur ? ' selected' : ''}>${esc(label ?? v)}</option>`;
  const dbToPct = db => Math.max(0, Math.min(100, (db + 60) / 60 * 100));
  /* Ley de fader de la plantilla (70 = 0 dB): posición que corresponde a una ganancia en dB. */
  const dbToFader = db => Math.max(0, Math.min(100, 70 * Math.pow(10, Math.max(-24, Math.min(6, db)) / 40)));

  /* ---------------- items: un audio = una pista = una tira ---------------- */
  const itemOf = t => MX.items.find(x => x.track === t) || null;
  const roleOfTrack = t => (t && (t.mxRole || (itemOf(t) || {}).role)) || '—';
  function setTrackRole(t, role) {
    t.mxRole = role;
    const it = itemOf(t);
    if (it) { it.role = role; if (KIND_FOR_ROLE[role] && VOCAL_KINDS.includes(it.kind)) it.kind = KIND_FOR_ROLE[role]; }
    MX.tune.confirmed = null;
  }
  const canHaveRole = t => t.type === 'audio' || t.type === 'voz';
  /* Las pistas borradas por el usuario dejan su audio en la lista, sin pista. */
  function reconcile() { for (const it of MX.items) if (it.track && !tracks.includes(it.track)) it.track = null; }

  function addItems(list) {
    const known = new Set(MX.items.map(i => i.path));
    const fresh = (list || []).filter(s => s && !known.has(s.path));
    for (const s of fresh.slice(0, Math.max(0, 30 - MX.items.length)))
      MX.items.push({ uid: ++MX.uid, path: s.path, name: s.name, kind: s.kind, role: s.role,
        auto_kind: s.auto_kind, auto_role: s.auto_role, track: null, note: '' });
    MX.tune.confirmed = null;
    return fresh;
  }
  /* Enlaza un audio ya importado al motor con su ficha del mezclador. */
  function linkTrack(t, info) {
    const path = info.originalPath || info.source_path || '';
    let it = MX.items.find(x => x.path === path && !x.track);
    if (!it && path) {
      addItems([{ path, name: info.name, kind: 'Otro', role: '—', auto_kind: 'Otro', auto_role: '—' }]);
      it = MX.items[MX.items.length - 1];
      // Importado desde fuera del módulo Audios: que el mezclador lo clasifique por su nombre.
      const ref = it;
      mixer('describe', { paths: [path] }).then(r => {
        if (!r.ok || !r.stems || !r.stems.length || !MX.items.includes(ref)) return;
        Object.assign(ref, { kind: r.stems[0].kind, role: r.stems[0].role, auto_kind: r.stems[0].auto_kind, auto_role: r.stems[0].auto_role });
        if (ref.track) ref.track.mxRole = ref.role;
        renderAll(); mezcla();
      });
    }
    if (!it) return null;
    it.track = t; it.note = info.note || '';
    t.mxRole = it.role;
    return it;
  }

  /* ---------------- registro de los módulos en el lienzo ---------------- */
  const NEW = [['audios', 'Audios', 'Carga A-30', '#ff9f45', [2200, 1040, 700]],
    ['afina', 'Afinador', 'PSOLA AT-1', '#7ae7ff', [3000, 1040, 520]],
    ['mastia', 'Master IA', 'Master M-4', '#ff6b9a', [3620, 1040, 440]],
    ['antes', 'Antes / Después', 'A/B Comp', '#e6d3a3', [4160, 1040, 420]]];
  for (const [id, name, model, color, pos] of NEW) {
    if (!PANELS.some(p => p[0] === id)) PANELS.push([id, name, model]);
    PC[id] = color; POS[id] = pos.slice(); DEFAULT_POS[id] = pos.slice();
  }
  /* La consola ahora contiene además la mezcla automática: necesita más ancho y alto por defecto. */
  POS.mezcla = [3260, 60, 760]; DEFAULT_POS.mezcla = POS.mezcla.slice();

  /* ---------------- cables ----------------
     Audios → Pistas → Mezcla → Master IA → Mezcla final ; Mezcla → Antes/Después ;
     Afinador → la TIRA concreta de cada voz que va a afinar.                        */
  const MXX = [];                     // centro horizontal de cada tira, dentro del panel Mezcla
  function tunedStrips() {
    const V = MX.tune.voices, want = [];
    if (V.lead) want.push('P');
    if (V.l) want.push('L', 'B_L');
    if (V.r) want.push('R', 'B_R');
    if (V.b) want.push('B', 'B_L', 'B_R');
    const out = [];
    tracks.forEach((t, i) => {
      if (!canHaveRole(t)) return;
      const r = roleOfTrack(t);
      if (r !== '—' && want.includes(r)) out.push({ i, role: r, name: t.name });
    });
    return out;
  }
  const _links2 = links;
  links = function () {
    const L = _links2();
    const add = (f, t) => { if (!hidden[f] && !hidden[t]) L.push({ key: f + '-' + t, f, t, c: PC[f] }); };
    add('audios', 'pistas'); add('mezcla', 'mastia'); add('mezcla', 'antes'); add('mastia', 'master');
    if (!hidden.afina && !hidden.mezcla && KV.tnStr > 0) {
      const S = tunedStrips();
      S.forEach((s, k) => L.push({ key: 'afina-tira-' + s.i, f: 'afina', t: 'mezcla', mx: s.i, slot: k, total: S.length, c: PC.afina }));
    }
    return L;
  };
  const _layoutPorts = layoutPorts;
  layoutPorts = function () {
    _layoutPorts();
    MXX.length = 0;
    const p = $('#p-mezcla'); if (!p) return;
    const pr = p.getBoundingClientRect();
    p.querySelectorAll('.strip').forEach((s, i) => { const b = s.getBoundingClientRect(); MXX[i] = (b.left - pr.left + b.width / 2) / VW.z; });
  };
  const _defaultPin = defaultPin;
  defaultPin = function (l, end) {
    if (l.mx !== undefined) {
      if (end === 'to') { const g = panelGeometry('mezcla'); return { side: 'top', u: clamp((MXX[l.mx] ?? 40) / g.w, .04, .96) }; }
      return { side: 'right', u: clamp(.12 + .76 * (l.slot + 1) / (l.total + 1), .08, .92) };
    }
    return _defaultPin(l, end);
  };

  /* ---------------- módulo Audios ---------------- */
  function roleSel(attr, val, label, cls) {
    return `<select class="${cls || ''}" data-${attr} aria-label="Rol vocal de ${esc(label)}" title="Rol vocal: ${ROLES.map(r => r + ' = ' + ROLE_NAME[r]).join(' · ')}">${ROLES.map(r => opt(r, val)).join('')}</select>`;
  }
  function rAudios() {
    const el = $('#b-audios'); if (!el) return;
    reconcile();
    const sinPista = MX.items.filter(i => !i.track).length;
    const rows = MX.items.map((s, i) => {
      const ti = s.track ? tracks.indexOf(s.track) : -1;
      return `<div class="afo-stem" style="--k:${KIND_COLOR(s.kind)}"><span>${String(i + 1).padStart(2, '0')}</span>
      <b title="${esc(s.path)}${s.note ? '\n' + esc(s.note) : ''}">${esc(s.name)}${s.note ? ' <em class="afo-conv" title="' + esc(s.note) + '">conv.</em>' : ''}</b>
      <select data-mxkind="${i}" aria-label="Tipo de ${esc(s.name)}">${D.types.map(t => opt(t, s.kind)).join('')}</select>
      ${roleSel('mxrole="' + i + '"', s.role || '—', s.name)}
      <i title="${ti >= 0 ? 'Pista y tira creadas' : 'Todavía sin pista en el motor'}">${ti >= 0 ? '▸ pista ' + (ti + 1) : 'sin pista'}</i>
      <button data-mxdel="${i}" aria-label="Quitar ${esc(s.name)}">✕</button></div>`;
    }).join('');
    el.innerHTML = `<div class="vst"><b class="lcd">${String(MX.items.length).padStart(2, '0')}/30</b><small>Cada audio crea su <b>pista</b> y, con ella, su <b>tira en la consola</b>. Tipo y rol se deducen del nombre (<code>_L</code>, <code>_R</code>, <code>_B</code>…) y se pueden corregir aquí, en Pistas o en la consola.</small></div>
      <div class="afo-drop" data-mxdrop="stems">⬇ Arrastra aquí tus audios<small>WAV · AIFF · FLAC · OGG · MP3 — hasta 30</small></div>
      <div class="tb"><button data-mx="add">+ Audios</button><button data-mx="ref">${MX.reference ? '↺ Referencia: ' + esc(MX.reference.name) : '+ Referencia (opcional)'}</button>${sinPista ? `<button data-mx="make">⇢ Crear ${sinPista} pista(s)</button>` : ''}${MX.items.length ? '<button data-mx="clear">Vaciar lista</button>' : ''}</div>
      <div class="afo-stems">${rows || '<p class="empty">Sin audios todavía.</p>'}</div>
      <p class="hint">Quitar un audio de esta lista no borra nada de tu disco. Si borras su pista, el audio sigue aquí y puedes volver a crearla.</p>`;
  }

  /* ---------------- consola: rol por tira + mezcla automática fusionada ---------------- */
  function stripExtras(t, i) {
    const live = MX.live[i];
    const it = itemOf(t);
    const kind = it ? it.kind : (t.type === 'voz' ? (KIND_FOR_ROLE[roleOfTrack(t)] || 'Voz principal') : '');
    let h = '';
    if (kind) h += `<em class="afo-kind" style="--k:${KIND_COLOR(kind)}" title="${esc(kind)}">${esc(KIND_SHORT(kind))}</em>`;
    if (canHaveRole(t)) h += roleSel('trole="' + i + '"', roleOfTrack(t), t.name, 'afo-role');
    if (live) h += `<b class="afo-slcd" title="${esc(live.note || '')}">${live.gain_db >= 0 ? '+' : ''}${(+live.gain_db).toFixed(1)}<small>${live.position || ''}</small></b>`;
    return h;
  }
  function autoMixBlock() {
    return `<div class="afo-sep">Mezcla automática · Auto-Mix V4.2</div>
      <div class="afo-row2"><label>Plantilla artística<select data-mxset="profile">${D.profiles.map(([k, n]) => opt(k, MX.profile, n)).join('')}</select></label>
      <label>Uso en el motor<select data-mxset="mode">${D.modes.map(m => opt(m, MX.mode)).join('')}</select></label></div>
      <div class="krow">${knob('mxStep', 'Escalón L/R', null, 40)}${knob('mxSpace', 'Espacio vocal', null, 45)}</div>
      <p class="hint" style="text-align:center"><b id="mxStepV">${stepDb().toFixed(1)} dB</b> bajo la voz principal · profundidad <b id="mxSpaceV">${Math.round(KV.mxSpace)}</b></p>
      <div class="afo-big"><button class="afo-go" data-mx="mix" ${MX.busy ? 'disabled' : ''}>MEZCLAR AUTOMÁTICAMENTE</button><button data-mx="remix" ${MX.busy || !MX.runs.length ? 'disabled' : ''}>↻ REMEZCLAR</button></div>
      <div class="afo-prog"><span style="--p:${MX.progress}%"></span></div><div class="afo-status" id="mxStatus">${esc(MX.status)}</div>
      ${MX.runs.length ? `<div class="afo-hist">${MX.runs.map((r, i) => `<button data-mxrun="${i}" aria-pressed="${MX.run === i}">#${i + 1} · ${esc(r.label)}</button>`).join('')}</div>` : ''}
      <p class="hint">Al mezclar, cada tira se enciende cuando le toca y acaba con el <b>nivel y el paneo reales</b> que decidió el mezclador. La EQ, la compresión y los efectos solo están en el audio renderizado (Master IA · Antes/Después).</p>`;
  }
  const _mezcla = mezcla;
  mezcla = function () {
    _mezcla();
    const el = $('#b-mezcla'); if (!el) return;
    el.querySelectorAll('.strip').forEach((s, i) => {
      const t = tracks[i]; if (!t) return;
      if (MX.working === i) s.classList.add('afo-work');
      const extra = stripExtras(t, i);
      if (extra) s.querySelector('small').insertAdjacentHTML('afterend', `<div class="afo-smeta">${extra}</div>`);
    });
    el.insertAdjacentHTML('beforeend', autoMixBlock());
    layoutPorts(); drawCables();
  };

  /* ---------------- Pistas: rol de voz en la fila ---------------- */
  const _pistas2 = pistas;
  pistas = function () {
    _pistas2();
    reconcile();
    $$('#b-pistas .row').forEach(row => {
      const i = +row.dataset.ti, t = tracks[i];
      if (!t || !canHaveRole(t)) return;
      const it = itemOf(t);
      const kind = it ? it.kind : (KIND_FOR_ROLE[roleOfTrack(t)] || '');
      row.querySelector('.th').insertAdjacentHTML('beforeend',
        `<span class="afo-trole">${kind ? `<em class="afo-kind" style="--k:${KIND_COLOR(kind)}" title="${esc(kind)}">${esc(KIND_SHORT(kind))}</em>` : ''}${roleSel('trole="' + i + '"', roleOfTrack(t), t.name, 'afo-role')}</span>`);
    });
    sync();
  };

  /* ---------------- Grabador: elegir el rol de la toma y guardarla como audio ---------------- */
  const _cinta = cinta;
  cinta = function () {
    _cinta();
    const el = $('#b-cinta'); if (!el) return;
    const t = T('voz');
    el.querySelector('.tbtn').insertAdjacentHTML('beforebegin',
      `<div class="afo-takerole"><label>Esta toma es<select data-takerole>${ROLES.filter(r => r !== '—').map(r => opt(r, MX.take.role, r + ' · ' + ROLE_NAME[r])).join('')}</select></label>
       <button data-take="save" ${t && t.rec ? '' : 'disabled'} title="Guarda la toma como WAV en los datos de AllForOne y la añade a Audios con este rol">⇢ Guardar toma como audio</button></div>`);
    if (t) t.mxRole = t.mxRole || MX.take.role;
  };

  /* ---------------- Afinador ---------------- */
  function rTune() {
    const el = $('#b-afina'); if (!el) return;
    const T2 = MX.tune, c = T2.confirmed, S = tunedStrips();
    const v = (k, l) => `<button data-tnv="${k}" aria-pressed="${T2.voices[k]}"><i></i>${l}</button>`;
    el.innerHTML = `<div class="afo-lcdbig"><div><small>${c ? 'CONFIRMADO' : 'SIN CONFIRMAR'}</small><b>${esc(c ? c.key : T2.key)} ${esc((c ? c.scale : T2.scale).replace('Menor natural', 'm').replace('Mayor', ''))}</b></div><div style="text-align:right"><small>BPM</small><b>${(+(c ? c.bpm : T2.bpm)).toFixed(1)}</b></div></div>
      <div class="tabs">${['Automático', 'Asistido', 'Manual'].map(m => `<button data-tnmode="${m}" aria-pressed="${T2.mode === m}">${m}</button>`).join('')}</div>
      <div class="afo-row3"><label>Tónica<select data-tnset="key">${D.keys.map(k => opt(k, T2.key)).join('')}</select></label>
      <label>Escala<select data-tnset="scale">${D.scales.map(s => opt(s, T2.scale)).join('')}</select></label>
      <label>BPM<input data-tnset="bpm" type="number" min="50" max="230" step="0.1" value="${T2.bpm}" class="afo-num"></label></div>
      <div class="tb"><button data-tn="analyze">Analizar música</button><button data-tn="confirm">✔ Confirmar</button></div>
      <div class="afo-note" id="tnStatus">${esc(T2.status)}</div>
      <div class="krow" style="margin-top:10px">${knob('tnStr', 'Intensidad', null, 0)}</div>
      <p class="hint" style="text-align:center"><b id="tnStrV">${Math.round(KV.tnStr)} %</b> · 0 % = sin afinación</p>
      <div class="afo-toggles">${v('lead', 'Voz principal · P')}${v('l', 'Voces L · izquierda')}${v('r', 'Voces R · derecha')}${v('b', 'Dobles / coros / _B')}</div>
      <div class="afo-wires">${S.length
        ? `<b>Conectado a ${S.length} tira(s) de la consola:</b>` + S.map(s => `<span style="--k:${PC.afina}">${esc(s.name)} · ${s.role}</span>`).join('')
        : (KV.tnStr > 0 ? '<b>Sin tiras conectadas:</b> ninguna pista tiene todavía el rol de las voces marcadas arriba.' : '<b>Intensidad 0 %:</b> sube la intensidad y los cables llegarán a las tiras de esas voces.')}</div>
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

  function renderAll() { rAudios(); rTune(); rMaster(); rAB(); }
  window.AFO_renderMixer = renderAll;
  const _refresh = refresh;
  refresh = function () { _refresh(); renderAll(); };

  const _setK3 = setK;
  setK = function (e, n) {
    _setK3(e, n);
    const k = e.dataset.k;
    if (k === 'mxStep') { const x = $('#mxStepV'); if (x) x.textContent = stepDb().toFixed(1) + ' dB'; }
    if (k === 'mxSpace') { const x = $('#mxSpaceV'); if (x) x.textContent = Math.round(KV.mxSpace); }
    if (k === 'tnStr') {
      const x = $('#tnStrV'); if (x) x.textContent = Math.round(KV.tnStr) + ' %';
      const on = KV.tnStr > 0;
      if (on !== MX.tuneOn) { MX.tuneOn = on; rTune(); sync(); }   // aparecen o se van los cables a las tiras
    }
  };

  /* ---------------- comunicación con Python (mixer_service.py) ---------------- */
  const mixer = (cmd, data) => (window.AFO && AFO.bridge) ? AFO.call('mixer', cmd, JSON.stringify(data || {})) : Promise.resolve({ ok: false, pending: true });
  const request = () => ({
    stems: MX.items.map(s => ({ path: s.path, name: s.name, kind: s.kind, role: s.role, auto_kind: s.auto_kind, auto_role: s.auto_role })),
    reference: MX.reference, profile: MX.profile, mode: MX.mode,
    profile_name: (D.profiles.find(p => p[0] === MX.profile) || [])[1],
    step_db: stepDb(), space: KV.mxSpace,
    tune: { mode: MX.tune.mode, key: MX.tune.key, scale: MX.tune.scale, bpm: MX.tune.bpm, prefer: MX.tune.prefer, strength: KV.tnStr, voices: MX.tune.voices }
  });
  window.AFO_mixerRequest = request;
  const status = (txt, p) => {
    MX.status = txt; if (p !== undefined) MX.progress = p;
    const el = $('#mxStatus'); if (el) el.textContent = txt;
    const bar = $('#b-mezcla .afo-prog span'); if (bar) bar.style.setProperty('--p', MX.progress + '%');
  };
  const fail = r => { if (r && !r.ok && !r.cancelled) toast(r.pending ? 'Motor no conectado' : r.error); return r; };

  /* Importa archivos al motor: crean pista (tira) y entran en la lista de Audios. */
  async function importToTracks(paths) {
    if (!paths || !paths.length) return [];
    const info = await mixer('describe', { paths });
    if (info.ok) addItems(info.stems);
    if (!(window.AFO && AFO.engineOk)) { renderAll(); toast('Motor no disponible: los audios quedan en la lista, sin pista'); return []; }
    const r = await AFO.call('importPaths', JSON.stringify(paths));
    if (!r.ok) { renderAll(); toast(r.error); return []; }
    const made = r.tracks.map(t => AFO.addAudioTrack(t));
    (r.errors || []).forEach(e => toast(e));
    refresh(); sync();
    const n = (r.converting || []).length;
    // Lo que el motor no lee se convierte en segundo plano y llega por eventos «import».
    if (n) status(`Convirtiendo ${n} archivo(s) que el motor no lee tal cual…`, 5);
    toast(`${made.length} pista(s) creadas` + (n ? ` · ${n} en conversión` : ''));
    return made;
  }

  /* ---------------- eventos del mezclador ---------------- */
  function applyStrip(ev) {
    const it = MX.items[ev.i]; const t = it && it.track;
    const idx = t ? tracks.indexOf(t) : -1;
    if (ev.phase === 'work') { MX.working = idx; markWorking(); return; }
    MX.working = -1;
    if (idx < 0) return;
    MX.live[idx] = { gain_db: ev.gain_db, pan: ev.pan, peak_db: ev.peak_db, rms_db: ev.rms_db, position: ev.position, note: ev.note, kind: ev.kind };
    if (it) { it.kind = ev.kind || it.kind; }
    // Las decisiones reales se llevan a la consola: fader (nivel) y perilla (paneo).
    const fad = $(`#b-mezcla input[data-v="${idx}"]`);
    if (fad) { fad.value = Math.round(dbToFader(ev.gain_db)); t.vol = +fad.value; fad.dispatchEvent(new Event('input', { bubbles: true })); }
    const kn = $(`#b-mezcla .knob[data-k="pan${idx}"]`);
    if (kn) setK(kn, 50 + 50 * (+ev.pan || 0));
    mezcla();
  }
  function markWorking() {
    $$('#b-mezcla .strip').forEach((s, i) => s.classList.toggle('afo-work', i === MX.working));
  }

  function onEvent(ev) {
    if (ev.type === 'strip') { applyStrip(ev); return; }
    if (ev.type === 'import') {
      if (ev.phase === 'convert') status(ev.desc + (ev.left ? ` (quedan ${ev.left})` : ''), Math.min(95, MX.progress + 5));
      else if (ev.phase === 'error') { toast(ev.error); status(ev.error, 0); }
      else if (ev.phase === 'track') {
        AFO.addAudioTrack(ev.track);
        status(`${ev.track.name}: ${ev.track.note || 'importado'}`, 0);
        refresh(); sync();
      }
      return;
    }
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
      MX.runs.push(ev.run); MX.run = MX.runs.length - 1; MX.busy = false; MX.review.sel = 0; MX.working = -1;
      MX.status = `Mezcla #${MX.runs.length} lista en ${ev.run.seconds} s · ${Object.keys(ev.run.masters).length} masters · ${ev.run.review.length} pistas A/B` + (ev.run.tuned ? ' · afinada' : '');
      MX.progress = 100; renderAll(); mezcla(); sync(); toast('Mezcla automática terminada · la consola refleja los niveles y el paneo');
    } else if (ev.type === 'error') {
      MX.busy = false; MX.working = -1; MX.status = 'Error: ' + ev.error;
      MX.tune.status = ev.panel === 'analysis' ? 'Error: ' + ev.error : MX.tune.status;
      renderAll(); mezcla(); toast(ev.error);
    } else if (ev.type === 'idle') {
      if (MX.busy) { MX.busy = false; MX.working = -1; mezcla(); }
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
    } else { MX.status = info.error; MX.ready = false; }
    /* Todo audio que entre al motor aparece también como ficha del mezclador. */
    if (AFO.addAudioTrack && !AFO.addAudioTrack.wrapped) {
      const base = AFO.addAudioTrack;
      const wrapped = (inf, o) => { const t = base(inf); if (!o || o.stem !== false) linkTrack(t, inf); return t; };
      wrapped.wrapped = true; AFO.addAudioTrack = wrapped;
    }
    renderAll();
  };

  /* Archivos soltados desde el Explorador (Qt entrega las rutas reales) */
  window.AFO_onDrop = async function (paths) {
    $$('.afo-drop').forEach(z => z.classList.remove('over'));
    await importToTracks(paths);   // suelta donde sueltes: audio → ficha + pista + tira
  };

  /* ---------------- guardar una toma del grabador como audio real ---------------- */
  async function saveTake() {
    const t = T('voz');
    if (!t || !t.rec || !t.rec.url) { toast('Graba una toma primero'); return; }
    if (!(window.AFO && AFO.bridge)) { toast('Sin puente con Python'); return; }
    toast('Guardando la toma…');
    try {
      const buf = await (await fetch(t.rec.url)).arrayBuffer();
      const audio = await AC().decodeAudioData(buf.slice(0));
      const wav = wavFromAudioBuffer(audio);
      const name = `${t.name}_${MX.take.role}`.replace(/[^\w.\- ]+/g, '_');
      const r = await sendBytes(wav, name);
      if (!r.ok) { toast(r.error || 'No se pudo guardar la toma'); return; }
      t.mxRole = MX.take.role;
      addItems([r.stem]);
      const it = MX.items[MX.items.length - 1];
      if (it) { it.role = MX.take.role; it.kind = KIND_FOR_ROLE[MX.take.role] || it.kind; }
      await importToTracks([r.stem.path]);
      renderAll();
      toast('Toma guardada como ' + r.stem.name + ' · rol ' + MX.take.role);
    } catch (e) { toast('No se pudo convertir la toma: ' + e); }
  }
  /* WAV PCM 24 bits a partir del AudioBuffer decodificado (sin dependencias). */
  function wavFromAudioBuffer(ab) {
    const ch = Math.min(2, ab.numberOfChannels), n = ab.length, bytes = 3;
    const data = new Uint8Array(n * ch * bytes);
    const src = []; for (let c = 0; c < ch; c++) src.push(ab.getChannelData(c));
    let o = 0;
    for (let i = 0; i < n; i++) for (let c = 0; c < ch; c++) {
      let v = Math.max(-1, Math.min(1, src[c][i]));
      v = Math.round(v * 8388607);
      data[o++] = v & 255; data[o++] = (v >> 8) & 255; data[o++] = (v >> 16) & 255;
    }
    const head = new DataView(new ArrayBuffer(44)), sr = ab.sampleRate;
    const txt = (at, s) => { for (let i = 0; i < s.length; i++) head.setUint8(at + i, s.charCodeAt(i)); };
    txt(0, 'RIFF'); head.setUint32(4, 36 + data.length, true); txt(8, 'WAVEfmt ');
    head.setUint32(16, 16, true); head.setUint16(20, 1, true); head.setUint16(22, ch, true);
    head.setUint32(24, sr, true); head.setUint32(28, sr * ch * bytes, true);
    head.setUint16(32, ch * bytes, true); head.setUint16(34, 8 * bytes, true);
    txt(36, 'data'); head.setUint32(40, data.length, true);
    const out = new Uint8Array(44 + data.length);
    out.set(new Uint8Array(head.buffer), 0); out.set(data, 44);
    return out;
  }
  const B64 = u8 => { let s = ''; const C = 0x8000; for (let i = 0; i < u8.length; i += C) s += String.fromCharCode.apply(null, u8.subarray(i, i + C)); return btoa(s); };
  async function sendBytes(u8, name) {
    const begin = await AFO.call('takeBegin', name);
    if (!begin.ok) return begin;
    const CH = 512 * 1024;
    for (let i = 0; i < u8.length; i += CH) {
      const r = await AFO.call('takeChunk', begin.token, B64(u8.subarray(i, i + CH)));
      if (!r.ok) return r;
    }
    return AFO.call('takeEnd', begin.token);
  }

  /* ---------------- eventos de la interfaz ---------------- */
  document.addEventListener('click', async e => {
    const b = e.target.closest('button'); if (!b) return;
    const d = b.dataset;
    if (d.take === 'save') { e.stopImmediatePropagation(); saveTake(); return; }
    if (d.mx) {
      if (d.mx === 'clear') { MX.items = []; MX.live = {}; MX.tune.confirmed = null; status('Lista vacía.', 0); renderAll(); sync(); return; }
      if (d.mx === 'add') { const r = fail(await mixer('add')); if (r.ok) await importToTracks(r.stems.map(s => s.path)); return; }
      if (d.mx === 'make') { await importToTracks(MX.items.filter(i => !i.track).map(i => i.path)); return; }
      if (d.mx === 'ref') { const r = fail(await mixer('ref')); if (r.ok) { MX.reference = r.reference; rAudios(); } return; }
      if (d.mx === 'mix' || d.mx === 'remix') {
        if (!MX.items.length) { toast('Carga audios en el módulo «Audios»'); return; }
        MX.live = {};
        const r = fail(await mixer(d.mx, request()));
        if (r.ok) { MX.busy = true; MX.progress = 1; MX.status = d.mx === 'remix' ? 'Remezclando (la mezcla anterior se conserva)…' : 'Mezclando…'; mezcla(); }
        return;
      }
    } else if (d.mxdel !== undefined) { MX.items.splice(+d.mxdel, 1); MX.tune.confirmed = null; renderAll(); sync(); }
    else if (d.mxrun !== undefined) { MX.run = +d.mxrun; MX.review.sel = 0; renderAll(); mezcla(); }
    else if (d.tnmode) { MX.tune.mode = d.tnmode; MX.tune.confirmed = null; rTune(); }
    else if (d.tnv) { MX.tune.voices[d.tnv] = !MX.tune.voices[d.tnv]; rTune(); sync(); }
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
      if (r.ok && d.ms === 'tracks') { r.tracks.forEach(t => AFO.addAudioTrack(t, { stem: false })); toast('Master añadido a Pistas'); }
      if (r.ok && d.ms === 'zip') toast('Comprimiendo la sesión en segundo plano → ' + r.path);
    }
    else if (d.abp) {
      if (d.abp !== 'stop') MX.review.ab = d.abp; rAB();
      const r = fail(await mixer('listen', { what: 'review', sel: MX.review.sel, ab: d.abp, run: MX.run }));
      if (r.ok && r.file) toast('Escuchando ' + r.file);
    }
  });
  document.addEventListener('change', e => {
    const t = e.target, d = t.dataset;
    if (d.mxkind !== undefined) { MX.items[+d.mxkind].kind = t.value; renderAll(); mezcla(); }
    else if (d.mxrole !== undefined) { const it = MX.items[+d.mxrole]; it.role = t.value; if (it.track) setTrackRole(it.track, t.value); renderAll(); mezcla(); sync(); }
    else if (d.trole !== undefined) { const tr = tracks[+d.trole]; if (tr) setTrackRole(tr, t.value); renderAll(); pistas(); mezcla(); sync(); }
    else if (d.takerole !== undefined) { MX.take.role = t.value; const v = T('voz'); if (v) setTrackRole(v, t.value); pistas(); mezcla(); }
    else if (d.mxset) MX[d.mxset] = t.value;
    else if (d.tnset) { MX.tune[d.tnset] = d.tnset === 'bpm' ? +t.value : t.value; MX.tune.confirmed = null; rTune(); }
    else if (d.abset) { MX.review.sel = +t.value; rAB(); }
  });
  /* realce visual al arrastrar sobre la zona (Qt entrega los archivos con su ruta real) */
  document.addEventListener('dragover', e => { const z = e.target.closest && e.target.closest('[data-mxdrop]'); $$('.afo-drop').forEach(x => x.classList.toggle('over', x === z)); if (z) e.preventDefault(); });
  document.addEventListener('dragleave', e => { if (!e.relatedTarget) $$('.afo-drop').forEach(x => x.classList.remove('over')); });
  document.addEventListener('drop', () => $$('.afo-drop').forEach(x => x.classList.remove('over')));
  /* las tiras se desplazan en horizontal: los cables del afinador las siguen */
  document.addEventListener('scroll', e => { if (e.target.closest && e.target.closest('#p-mezcla')) { layoutPorts(); drawCables(); } }, true);

  /* ---------------- montar en el lienzo ---------------- */
  loadLayout();   // vuelve a leer el diseño guardado, ahora con los módulos nuevos
  build();
  if (window.AFO && AFO.bridge) AFO_onMixerConnected();
})();

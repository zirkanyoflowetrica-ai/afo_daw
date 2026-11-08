/* AllForOne — puente entre PLANTILLA_DAW.html y Python (QWebChannel).
 *
 * Regla: la plantilla original no se reescribe. Este archivo se carga DESPUÉS de su script
 * y solo envuelve sus funciones globales (pistas, lane, sub, links, meters, masterP, setK)
 * o intercepta clics concretos. Cambios visibles respecto a la plantilla (documentados en
 * docs/CAMBIOS_PLANTILLA.md):
 *   - Botones "+ Audio" y "+ Tono de prueba" en la barra de Pistas.
 *   - Subtítulo "DEMO ·" en pistas cuyo sonido sigue siendo la demostración Web Audio.
 *   - Master: posición 70 = 0 dB (unidad).
 *   - Medidores y aguja VU: valores reales del motor (antes aleatorios).
 */
(function () {
  'use strict';

  const AFO = window.AFO = { bridge: null, connected: false, engineOk: false, info: null, state: null, vu: 0, lastPlaying: false };
  const log = (...a) => { console.log('[AFO]', ...a); };
  const dbToPct = db => Math.max(0, Math.min(100, (db + 60) / 60 * 100));
  const call = (name, ...args) => new Promise((resolve) => {
    if (!AFO.bridge) { resolve({ ok: false, error: 'Sin puente con Python' }); return; }
    AFO.bridge[name](...args, r => { try { resolve(typeof r === 'string' ? JSON.parse(r) : r); } catch (e) { resolve({ ok: false, error: String(e) }); } });
  });
  AFO.call = call;

  if (typeof QWebChannel === 'undefined' || !window.qt || !qt.webChannelTransport) {
    log('QWebChannel no disponible: la plantilla funciona en modo demostración del navegador.');
    return;
  }

  /* ---------- tipo de pista "audio" (archivos reales en el motor) ---------- */
  SRC.audio = 'pistas'; TN.audio = 'Audio';
  const BAR16 = () => 16 * 4 * 60 / (+$('#bpm').value || 96);   // segundos que ocupa el 100 % del carril

  const _links = links;
  links = function () { return _links().filter(l => l.f !== l.t); };   // el audio importado no tiene cable de entrada

  const _sub = sub;
  sub = function (t) {
    if (t.type === 'audio') return fmt(t.dur || 0) + ' · motor nativo';
    const s = _sub(t);
    if (AFO.engineOk && (t.type === 'inst' || t.type === 'drum' || t.type === 'ia')) return 'DEMO · ' + s;
    return s;
  };

  const _lane = lane;
  lane = function (t) {
    if (t.type !== 'audio') return _lane(t);
    let h = t.clips.map(c => `<div class="clip" style="left:${c[0]}%;width:${c[1]}%"></div>`).join('');
    const p = t.peaks || [];
    t.clips.forEach(c => {
      const n = Math.max(1, Math.round(c[1] * 3));
      for (let j = 0; j < n; j++) { const v = p[Math.floor(j / n * p.length)] || 0; h += `<i class="wf" style="left:${c[0] + c[1] * j / n}%;height:${4 + v * 44}px"></i>`; }
    });
    return h;
  };

  const _pistas = pistas;
  pistas = function () {
    _pistas();
    if (!AFO.engineOk) return;
    const tb = document.querySelector('#b-pistas .tb');
    if (tb && !tb.querySelector('[data-add="audio"]')) {
      tb.insertAdjacentHTML('afterbegin', '<button data-add="audio" title="Importar WAV/AIFF/FLAC al motor nativo">+ Audio</button><button data-afo="tone" title="Señal sintética de 440 Hz para comprobar el motor">+ Tono de prueba</button>');
      sync();
    }
  };

  const _masterP = masterP;
  masterP = function () {
    _masterP();
    const lim = $('#lim');
    if (lim && AFO.engineOk) lim.title = 'Pendiente (V0.7): este botón aún no procesa audio en el motor';
  };

  const _setK = setK;
  setK = function (e, n) {
    _setK(e, n);
    const k = e.dataset.k || '';
    if (AFO.engineOk && k.startsWith('pan')) {
      const t = tracks[+k.slice(3)];
      if (t && t.engineId) call('setTrackPan', t.engineId, (Math.max(0, Math.min(100, n)) - 50) / 50);
    }
  };

  /* Medidores reales: nivel de pico del motor (dBFS) en escala -60..0 dB. */
  meters = function () {
    const st = AFO.state, on = !!(st && st.playing);
    $$('[data-mt]').forEach(m => {
      const k = m.dataset.mt; let v = 0;
      if (on) {
        if (k === 'L') v = dbToPct(st.master[0]);
        else if (k === 'R') v = dbToPct(st.master[1]);
        else { const t = tracks[+k]; if (t && t.engineId && st.tracks[t.engineId] != null) v = dbToPct(st.tracks[t.engineId]); }
      }
      m.style.setProperty('--h', v + '%');
    });
    // VU: balística aproximada (~300 ms) sobre el pico promedio L/R. LUFS llegará en V0.7.
    const target = on ? (dbToPct(st.master[0]) + dbToPct(st.master[1])) / 2 : 0;
    AFO.vu += (target - AFO.vu) * 0.25;
    const n = $('#needle'); if (n) n.style.transform = `rotate(${-50 + AFO.vu * 1.05}deg)`;
  };

  function addAudioTrack(info) {
    const t = mk('audio', info.name);
    t.engineId = info.id; t.peaks = info.peaks || []; t.dur = info.length_seconds;
    t.vol = 70;
    t.clips = [[0, Math.max(1, Math.min(100, info.length_seconds / BAR16() * 100))]];
    tracks.push(t); pick(t);
    return t;
  }

  function syncTrackStates() {
    const list = tracks.filter(t => t.engineId).map(t => [t.engineId, !!t.mute, !!t.solo]);
    if (list.length) call('setTrackStates', JSON.stringify(list));
  }

  function applyState(st) {
    AFO.state = st;
    if (st.playing !== AFO.lastPlaying) {
      AFO.lastPlaying = st.playing;
      $('#play').textContent = st.playing ? '❚❚ Pausa' : '▶ Reproducir';
      $('#cables').classList.toggle('on', st.playing);
    }
    if (st.playing) {
      // El motor es el reloj: el cursor y la demo Web Audio siguen su posición.
      const target = Math.floor(st.position * (+$('#bpm').value || 96) / 15) % 256;
      let guard = 0;
      if (step < 0 || ((target - step + 256) % 256) > 8) step = (target + 255) % 256;
      while (step !== target && guard++ < 16) { step = (step + 1) % 256; tick(); }
    }
    meters();
  }

  /* ---------- clics: capturamos antes que la plantilla solo donde hay motor ---------- */
  document.addEventListener('click', async e => {
    const b = e.target.closest('button'); if (!b || !AFO.engineOk) return;
    const d = b.dataset;
    if (b.id === 'play') {
      e.stopImmediatePropagation();
      const r = await call('togglePlay'); if (!r.ok) toast(r.error);
    } else if (b.id === 'stop') {
      call('stop');                                   // la plantilla reinicia cursor y tiempo
    } else if (b.id === 'exp') {
      e.stopImmediatePropagation();
      toast('Renderizando mezcla…');
      const r = await call('exportMix');
      toast(r.ok ? 'Exportado: ' + r.path : (r.cancelled ? 'Exportación cancelada' : r.error));
    } else if (d.add === 'audio') {
      e.stopImmediatePropagation();
      const r = await call('importAudio');
      if (r.ok) { r.tracks.forEach(addAudioTrack); toast(r.tracks.length + ' archivo(s) en el motor'); }
      else if (!r.cancelled) toast(r.error);
    } else if (d.afo === 'tone') {
      e.stopImmediatePropagation();
      const r = await call('addTestTone');
      if (r.ok) { addAudioTrack(r.track); toast('Tono de prueba 440 Hz (sintético) añadido'); } else toast(r.error);
    } else if (d.del !== undefined) {
      const t = tracks[+d.del]; if (t && t.engineId) call('removeTrack', t.engineId);
    }
  }, true);

  document.addEventListener('click', e => {      // después de la plantilla
    const b = e.target.closest('button'); if (!b || !AFO.engineOk) return;
    if (b.dataset.m !== undefined || b.dataset.s !== undefined) syncTrackStates();
  });

  document.addEventListener('input', e => {
    if (!AFO.engineOk) return;
    const t = e.target;
    if (t.dataset.v !== undefined) { const tr = tracks[+t.dataset.v]; if (tr && tr.engineId) call('setTrackVolume', tr.engineId, +t.value); }
    else if (t.id === 'mv') call('setMasterVolume', +t.value);
    else if (t.id === 'bpm' && +t.value >= 40) call('setTempo', +t.value);
  });

  /* ---------- conexión ---------- */
  new QWebChannel(qt.webChannelTransport, async channel => {
    AFO.bridge = channel.objects.afo;
    AFO.connected = true;
    const info = AFO.info = await call('hello');
    log('conectado', JSON.stringify(info));
    if (!info.engine) { toast('Motor nativo no disponible: ' + (info.error || 'desconocido')); return; }
    AFO.engineOk = true;
    AFO.bridge.stateChanged.connect(s => { try { applyState(JSON.parse(s)); } catch (err) { log('estado inválido', err); } });
    master = 70;                                                // 70 = 0 dB
    call('setMasterVolume', master); call('setTempo', +$('#bpm').value || 96);
    masterP(); refresh();
    const dev = info.device || {};
    toast(dev.open ? `Motor nativo listo · ${dev.type} · ${dev.output}` : 'Motor nativo listo · sin dispositivo de salida abierto');
  });
})();

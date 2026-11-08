# Interfaz nativa (Qt Quick) — sin HTML ni Chromium

Objetivo: que AllForOne sea una app de escritorio 100 % nativa conservando la imagen y el
funcionamiento de `PLANTILLA_DAW.html`, que pasa a ser la **referencia visual**.

Se conserva tal cual: motor C++ (`native/`), `EngineHost`, el Mezclador V4.2 y su adaptador, la
importación de audio y el `Bridge` de Python (sus métodos son slots de Qt: QML los llama
directamente, igual que antes JavaScript por QWebChannel). Solo cambia la capa que dibuja.

```
python -m allforone --nativo            # abrir la interfaz nativa
python -m allforone --nativo --selftest # autoprueba con el motor real
python tools/native_compare.py [--oscuro]   # comparación píxel a píxel con la interfaz web
```

## Fases

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Ventana, cabecera (transporte, tempo, zoom, Ver todo, Restaurar diseño, tema), lienzo infinito con puntos, 12 módulos movibles (13 con Efectos) y redimensionables, cables con curva, conectores y cuadrados de curva arrastrables, diseño y tema guardados, módulo **Pistas** con el motor real, arrastrar audios a la ventana | **Hecha** |
| 1 | Audios, Mezcla (consola, faders, rol de voz, MEZCLAR AUTOMÁTICAMENTE), Mezcla final (VU, master, exportar) | **Hecha** |
| 2 | Afinador, Master IA, Antes / Después | **Hecha** |
| 3 | Piano roll, Instrumentos, Batería, Pistas con IA, con sonido del motor (hoy son la demo Web Audio) | **Hecha** |
| 4 | Grabador de cintas grabando con el motor, configuración de audio (drivers, ASIO), módulo Efectos (Biblioteca nativa, Hito 1) | **Hecha** |
| 5 | Interfaz nativa como predeterminada y retirar Qt WebEngine | Pendiente |

Los módulos de fases pendientes muestran en su cuerpo que aún no están migrados y dónde usarlos.

## Fase 0: cómo se hizo

- `app/allforone/qml/`: `Main.qml` (ventana, cabecera, lienzo, cables, conectores), `ModulePanel.qml`
  (módulo), `TracksBody.qml` (Pistas), `NeoButton.qml` (botón con sombra dura), `Theme.qml`
  (colores claro / oscuro de la plantilla y de `afo_theme_dark.css`), `layout.js` (la matemática del
  lienzo portada de la plantilla: `anchor`, `cableShape`, `nearestPin`, `fit`).
- `app/allforone/native_ui.py`: carga fuentes y QML, expone `afo` (Bridge) y `layoutStore`
  (diseño en `datos/diseno_nativo.json`, sin almacenamiento del navegador).
- **Fuente:** Qt no lee WOFF2 y aplica mal los grosores de una fuente variable, así que Space
  Grotesk (OFL 1.1) va como tres TTF estáticos (500, 600, 700) generados de la misma fuente.
- **Símbolos** (■ ▶ ◐ ✕): no están en Space Grotesk; se dibujan con Segoe UI Symbol, como hace el
  navegador en Windows.

## Comparación medida (1600×900, datos limpios)

| Zona | Píxeles distintos | Qué explica la diferencia |
|---|---|---|
| Cabecera, tema claro | 8,0 % | Posiciones iguales a ±1 px; el resto es el suavizado del texto (Chromium y Qt rasterizan distinto) |
| Cabecera, tema oscuro | 8,1 % | Igual |
| Lienzo | 30 % (claro) / 18 % (oscuro) | Cuerpos de los módulos de las fases 1–4 y pistas DEMO de la plantilla, que la nativa no muestra |

Encuadre inicial: zoom 0,6157 (web 0,6159).

## Fase 1: cómo se hizo

- `Mixer.qml` + `mixdata.js`: el estado del Mezclador V4.2 (antes `AFO_MX` en `afo_panels.js`):
  fichas de audio, tipo y rol de voz, plantilla, escalón L/R, espacio vocal, progreso, historial y
  las decisiones reales por tira. Habla con Python por el mismo `afo.mixer(...)`.
- `AudiosBody.qml`: contador, zona para soltar, + Audios / + Referencia / ⇢ Crear pistas / Vaciar,
  lista con tipo y rol editables. Soltar audios en cualquier parte de la ventana crea ficha, pista
  y tira (los WAV de 64 bits se convierten en segundo plano y se enlazan al llegar).
- `MixBody.qml`: una tira por pista con tipo, rol, LCD de la decisión del mezclador (ganancia y
  posición medidas), Pan, fader y medidor del motor; debajo, MEZCLAR / REMEZCLAR, progreso, estado e
  historial. Al terminar, faders y paneo se mueven a lo que decidió el mezclador.
- `MasterBody.qml`: VU con balística ~300 ms sobre el pico L/R del motor (no mide sonoridad), fader
  master (70 = 0 dB) con medidores L/R reales y Exportar mezcla. **Saturación, Tono y Limitador
  siguen sin procesar audio**: lo dicen al pasar el ratón y al usarlos.
- Controles nuevos: `Knob.qml`, `Fader.qml`, `Meter.qml`, `Select.qml`, `Lcd.qml`.
- Rol de voz también en cada fila de Pistas; cambiarlo en Audios, Pistas o la consola lo cambia en
  los tres.

Comprobado con `--nativo --selftest` (motor real): soltar 3 audios (uno en 64 bits) → 3 fichas,
pistas y tiras; clasificación por nombre; MEZCLAR en ~2,4 s; faders en 59 / 51 / 53, idénticos a la
web; medidores del master con el nivel del motor. Con los 10 stems reales de PPPP: 10 tiras con su
rol (P, L, R) deducido del nombre.

Comparación por módulo a zoom 1 tras importar y mezclar (compensando desplazamientos de ±4 px):
Mezcla final 11,8 %, Audios 21,8 %, cabecera de Mezcla 6,6 %. Lo que queda es el rayado de fondo
desfasado unos píxeles, el suavizado del texto y alguna línea que parte distinto. El bloque de mezcla
automática no es comparable: la web tiene encima 3 tiras DEMO de la plantilla que la nativa todavía
no muestra (fase 3).

## Fase 2: cómo se hizo

- `TuneBody.qml` (Afinador): pantalla CONFIRMADO / SIN CONFIRMAR con tonalidad y BPM, modos
  Automático / Asistido / Manual, Tónica, Escala, BPM, Analizar música, ✔ Confirmar, estado,
  Intensidad, voces a afinar (P, L, R, _B) y la lista de tiras conectadas. Con intensidad > 0 % sale
  **un cable a la tira exacta** de cada voz con ese rol; los cables siguen a las tiras al desplazar
  la consola. La curva de tono antes/después sigue pendiente y el módulo lo dice.
- `MasteringBody.qml` (Master IA): los 4 masters del V4.2 + «Según referencia» con LUFS, true peak
  y limitación medidos; escucha A (sin master) / B (master) en el motor a la misma posición;
  → Enviar a Pistas, Exportar sesión ZIP (en segundo plano) y Abrir carpeta.
- `ReviewBody.qml` (Antes / Después): selector de pista, ▶ A original / ▶ B procesada / ■ en el
  motor, y las decisiones del mezclador para esa pista.
- `Mixer.qml` añade el estado del afinador (la confirmación se anula si cambian los audios, los
  roles o la tonalidad) y las acciones de escucha. `Note.qml` es el recuadro de notas.
- Un botón con RichText informa `lineCount = 1` aunque tenga dos líneas: `NeoButton` cuenta las
  líneas por la altura del contenido.

Comprobado con `--nativo --selftest` (motor real): cable del Afinador a la tira de la voz P;
confirmar F menor 91 BPM en modo manual; **REMEZCLAR con afinación al 60 %: la mezcla sale
«afinada»**; master enviado a Pistas; escucha B del master, A/B de una pista y parada en el motor.

Diferencias que quedan con la web: el texto de la curva pendiente no sale estirado (en la web el
SVG lo deforma), y en Master IA los tres botones caben en una fila porque el texto nativo es algo
más estrecho.

## Fase 3: cómo se hizo

**Sonido en el motor C++ (JUCE + Tracktion), no en el navegador ni en Python.**

- `native/src/AfoSynth.*`: la DSP del sonido de la plantilla (osciladores, lowpass según el Brillo,
  envolvente exponencial; batería con barridos, cuadradas y ruido filtrado), voz a voz.
- `AfoSynthPlugin` (en `AfoEngine.cpp`): plugin propio de Tracktion. Cada pista de Instrumento o
  Batería es una pista del motor con ese plugin y **un clip MIDI** en tiempos de compás. El plugin
  toca las notas en el callback de audio: editar una nota solo rehace el clip (sin renderizar), y la
  pista tiene fader, paneo, mute/solo, medidores y exportación como cualquier otra.
- Escuchar al pulsar (teclado, rejilla, instrumento, golpe) usa la misma DSP por el reproductor de
  escucha del motor, sin tocar el transporte.
- Nuevo en `afo_audio` (API 3): `add_synth_track`, `set_synth_settings`, `set_synth_notes`,
  `audition_synth`. `engine_host.pattern_notes` convierte piano roll / patrón + clips en notas,
  igual que el reloj de la plantilla.

**Interfaz:** `Sequencer.qml` (pistas, pista activa por módulo, piano roll, patrón, IA),
`PianoBody.qml`, `InstBody.qml`, `DrumsBody.qml`, `IaBody.qml`, `TrackTabs.qml`. Pistas muestra
los clips con sus notas o golpes, un cable desde el módulo de origen hasta la fila de cada pista, y
la consola una tira por pista con el color de su módulo. Arranca con las 3 pistas de la plantilla
(Acordes, Bajo, Batería 1), que ahora suenan de verdad.

**Lo que se dice tal cual:** el sonido es la síntesis básica de la plantilla, no instrumentos
muestreados (el subtítulo lo pone: «síntesis»). Reverb y Swing no los usaba la plantilla y siguen
sin cambiar el audio (lo avisan). Pistas con IA sigue siendo una DEMO: clips de ejemplo, sin audio,
y lo indica en la pista, en la tira y en el módulo. Quitar Instrumentos o Batería del lienzo
desconecta sus pistas (no suenan), como en la plantilla.

Comprobado: render real del motor (nota La a 440 Hz exactamente en su tiempo, silencio antes;
batería en negras; rehacer el patrón sustituye el clip); `--nativo --selftest`: las 3 pistas de la
plantilla suenan en el render, editar el piano roll cambia el patrón, escuchar una nota, + Instrumento
crea pista con sintetizador, IA sin audio, desconectar silencia. Vista inicial frente a la web:
cabecera 8 %, lienzo 20 % (antes 30 %).

## Fase 4: cómo se hizo

**Grabar lo hace el motor.** Tracktion graba desde la entrada del dispositivo (`WaveInputDevice`)
y escribe el WAV en su hilo; la interfaz solo arma, manda grabar o parar y lee el medidor real de
la entrada. Nunca pasa audio por el puente.

- `afo_audio` (API 5): `record_inputs`, `add_record_track`, `arm_track(track, input, monitor)`,
  `start_recording`, `stop_recording(discard)`, `record_state` (incluye el nivel de entrada en dB).
- `CintaBody.qml` (Cinta RX-2, como la plantilla): bobinas que giran mientras graba o suena la toma,
  contador LCD, pestañas de pistas de voz, entrada, **Monitor** (oír la entrada) y medidor de entrada;
  ● Grabar, ■ Parar, ▶ Escuchar toma. «+ Voz» en Pistas crea la pista; la toma se ve como onda
  donde empezó y entra en la consola como cualquier audio. Quitar el Grabador del lienzo desarma.
- **Configuración de audio** (botón «Audio» de la cabecera y del Grabador, `AudioSettings.qml`):
  driver (Windows Audio, exclusivo, baja latencia, DirectSound, **ASIO**), salida, entrada,
  frecuencia, búfer con su latencia en ms y el **panel propio del driver ASIO**. Funciona con
  cualquier driver ASIO instalado: ASIO4ALL 2.x, los de cada interfaz, FL Studio ASIO… Si un driver
  no abre, el motor vuelve al dispositivo anterior: nunca te deja sin audio. El ajuste se guarda.

**Efectos.** Módulo «Efectos» (Rack FX-96, `FxBody.qml`): elegir la pista o el master, cadena en el
orden de la señal con bypass, mover y quitar; editor con perillas y listas mapeadas al rango real
de cada parámetro, medidores de entrada/salida, reducción de ganancia, la curva real del EQ y el
espectro del Analizador; navegador con las 6 secciones y 20 carpetas de la Biblioteca. Detalle en
`docs/BIBLIOTECA_NATIVA.md`.

Comprobado: `tests/test_engine_fx.py` (13 pruebas de señal + dispositivo + grabación real) y
`--nativo --selftest`: «+ Voz», armar en una entrada real (si el dispositivo no tiene entradas, la
autoprueba cambia a ASIO4ALL como lo haría el usuario y al final vuelve al de antes), grabar 1 s y
ver la onda; insertar EQ y Analizador en una pista, espectro real del tono, bypass y quitar.
Vista inicial frente a la web: cabecera 12 % (los botones «Audio» y «Efectos», que la web no
tiene; el chip de Efectos va en la primera fila para no añadir otra fila de chips), lienzo 20 %.


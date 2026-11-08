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
| 0 | Ventana, cabecera (transporte, tempo, zoom, Ver todo, Restaurar diseño, tema), lienzo infinito con puntos, 12 módulos movibles y redimensionables, cables con curva, conectores y cuadrados de curva arrastrables, diseño y tema guardados, módulo **Pistas** con el motor real, arrastrar audios a la ventana | **Hecha** |
| 1 | Audios, Mezcla (consola, faders, rol de voz, MEZCLAR AUTOMÁTICAMENTE), Mezcla final (VU, master, exportar) | **Hecha** |
| 2 | Afinador, Master IA, Antes / Después | **Hecha** |
| 3 | Piano roll, Instrumentos, Batería, Pistas con IA, con sonido del motor (hoy son la demo Web Audio) | Pendiente |
| 4 | Grabador de cintas grabando con el motor; autoprueba completa sobre QML; retirar Qt WebEngine | Pendiente |

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

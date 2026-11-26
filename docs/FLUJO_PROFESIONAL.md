# Flujo profesional de AllForOne (26-11-2026)

Manda sobre `docs/DISENO_DAW.md` §2 y §4. Las reglas de color, contraste y «nada falso» siguen.

## 0. Por qué otra vez

El usuario: «aún parece un recorte de cosas, no entiendo el flujo; las herramientas de IA son paneles
aparte y no están integradas en el flujo». Tiene razón. Hoy la IA vive en cinco sitios sueltos:

| Hoy | Problema |
|---|---|
| Botón **Crear IA** (vista F8, `LabView`) con su propia lista de pistas | Una segunda «aplicación» dentro de la aplicación |
| **Navegador › IA** (`IaBody`): formulario grande de canción / MIDI | Generar no está donde se trabaja: en la pista y en el tiempo |
| **Inspector › Asistente IA** (`MixAiBody` + `MasteringBody` + `ReviewBody`) | La mezcla y el master automáticos lejos del Mezclador y del master |
| Barra del Arreglo: «Rehacer con IA», «Versión con IA», «Alinear voz», casi siempre apagados | Botones fijos que dependen de la selección: ruido visual |
| **Detalle › Afinador** con el editor de tono dentro de un efecto | El editor de tono es un editor de clip, no un efecto |

Además: pestañas en las tres zonas (el usuario tiene que saber en qué pestaña está cada cosa), una
cabecera con botones mezclados (Restaurar zonas, Tema, Crear IA, Abrir…) y un panel de abajo con
pestañas en vez de seguir a la selección.

## 1. Lo que hacen los cinco DAW (investigado 26-11-2026)

| | Pantalla | Editor de abajo | IA dentro del flujo |
|---|---|---|---|
| **Pro Tools** | Ventana Edición (pistas y clips) y ventana Mezcla, con una tecla (Ctrl+=) | Editor MIDI y Melodyne (ARA) sobre el clip | Speech to Text local: **clic derecho en el clip o pista** → la transcripción sale en un carril bajo la onda. Splice: arrastrar un clip del timeline al buscador |
| **Logic Pro** | Biblioteca/Inspector a la izquierda, pistas al centro, navegadores a la derecha, editores abajo (E), mezclador (X) | Piano roll, editor de audio, Flex Pitch: siguen a la región elegida | **Stem Splitter**: región → menú → elegir stems → pistas nuevas. **Session Players**: son un *tipo de pista*; la región sigue la pista de acordes y se ajusta en el inspector de región. **Mastering Assistant**: un efecto en la salida estéreo |
| **Studio One** | Inspector a la izquierda, Arreglo al centro, Navegador a la derecha (F5), Edición abajo (F2), Consola (F3) | Editor de notas o de audio (Melodyne ARA) del evento elegido | **Separar stems**: clic derecho en el evento → Audio → elegir stems → carpeta bajo la pista original, que queda apagada. Splice dentro del Navegador, a la tonalidad y tempo del tema |
| **Cubase** | Zona izquierda (Inspector), zona derecha (medios), zona inferior (Editor / MixConsole / Pads de acordes) | Editor de teclas o de muestras en la zona inferior; **VariAudio** en el inspector del editor | Pista de acordes, Chord Assistant y detección de tonalidad dentro del proyecto |
| **Ableton Live** | Navegador a la izquierda, Arreglo/Sesión, **Vista de detalle** abajo (clip + dispositivos apilados) | La vista de detalle es el editor del clip elegido | **Stem Separation** (local): clic derecho en el clip → pistas en un grupo nuevo; solo procesa lo que hay entre los marcadores del clip. **Generadores y Transformaciones MIDI**: pestañas del propio clip |

Fuentes: [Logic Stem Splitter](https://support.apple.com/guide/logicpro-ipad/lpip1bba4539/ipados),
[Logic Session Players (SOS)](https://www.soundonsound.com/techniques/logic-pro-session-players),
[Studio One Pro 7 (SOS)](https://www.soundonsound.com/reviews/presonus-studio-one-pro-7?amp),
[Pro Tools 2025.6](https://www.avid.com/resource-center/whats-new-in-pro-tools-20256),
[Cubase 14 (SOS)](https://soundonsound.com/reviews/steinberg-cubase-pro-14),
[VariAudio en la zona inferior](https://forums.steinberg.net/t/access-variaudio-and-others-in-bottom-editor-window/669342),
[Ableton Stem Separation](https://www.ableton.com/en/manual/stem-separation/),
[Ableton Live 12](https://www.ableton.com/live/all-new-features/),
[ReaScript (Python en REAPER)](https://www.reaper.fm/sdk/reascript/reascript.php).

**Lo común, y lo que AllForOne adopta:**

1. **Ninguna IA tiene panel propio.** Es una orden sobre lo elegido: clic derecho en el clip o la
   pista, el menú de la barra o un tipo de pista. El resultado entra como pistas, clips o tomas
   que se editan y se deshacen como cualquier otra cosa.
2. **Una zona de abajo que sigue a la selección**, sin pestañas: clip de audio → editor de audio
   (con su modo Tono), clip MIDI → piano roll, efecto → su editor.
3. **El master automático es un efecto en el master** (Logic), no un panel.
4. **Inspector a la izquierda, Navegador a la derecha** (Logic, Studio One, Cubase).
5. **Menús de verdad** (Archivo, Editar, Pista, Clip, Mezcla, Ver, Ayuda): cada orden está en un
   menú con su atajo; los botones solo para lo que se usa a cada rato.

## 2. Pantalla nueva

```
┌ Archivo  Editar  Pista  Clip  Mezcla  Scripts  Ver  Ayuda ─────────────────────────────────────────────┐
│ ■ ▶ ● ⟲ │ 001.1.1  00:00,0 │ 120 BPM  4/4  Do mayor │ Artista › Canción ●guardado │      CPU ▮▮▯  ⌕ Ctrl+K │
├───────────┬────────────────────────────────────────────────────────────────────────┬───────────────────┤
│ INSPECTOR │ Regla · marcadores · pista de ACORDES (detectada o escrita)            │ NAVEGADOR         │
│ (de lo    │ ┌cabecera─┐┌clips───────────────────────────────────────────────┐      │ ⌕ buscar          │
│ elegido)  │ │Voz  M S ●││▒▒▒▒ toma 1 ▒▒▒▒   ▒▒▒ toma 2 ▒▒▒                    │      │ Instrumentos      │
│ Pista:    │ │Bajo M S ●││████████████████████                                 │      │ Efectos           │
│ vol, pan, │ │Bat. M S ●││▌▌▌▌▌▌▌▌▌▌▌▌▌▌▌▌                                     │      │ Sonidos y bucles  │
│ envíos,   │ │+ pista   ││                                                     │      │ Archivos          │
│ inserts,  │ └──────────┘└─────────────────────────────────────────────────────┘      │ (plegable, F5)    │
│ rol de voz│            ARREGLO  ⇄  MEZCLADOR (Tab / F3)                            │                   │
├───────────┴────────────────────────────────────────────────────────────────────────┴───────────────────┤
│ EDITOR (F2) — sigue a la selección, sin pestañas:                                                       │
│   clip de audio → onda (cortes, fundidos, ganancia) · modo Tono (notas: AF-64)                          │
│   clip MIDI → piano roll · clip de batería → patrón · efecto elegido → su editor · pista → su cadena    │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Barra de estado: qué pasa (grabando, generando 40 %, mezclando) y qué hace lo que está bajo el ratón    │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Inicio (F4) sigue siendo la pantalla de entrada con artistas y recientes; dentro del proyecto no hay
botón «Inicio» en la cabecera (está en Archivo). Doble flujo (F7) se mantiene.

## 3. Dónde vive cada función (y desaparece su panel)

### Clic derecho en un clip de audio (y menú **Clip**)

| Orden | Hoy | Qué hace |
|---|---|---|
| Separar en pistas… (voz, batería, bajo, otros) | botón en la pista | Diálogo corto con casillas; pistas nuevas en una carpeta bajo la original, que se silencia (no se borra). Solo procesa el clip |
| Rehacer con IA… | botón fijo del Arreglo | Sobre el clip o el rango elegido; pide el texto en un cuadro junto al clip. El resultado entra como **toma nueva** en la misma pista |
| Versión con IA… | botón fijo del Arreglo | Igual, con la fuerza; entra como toma |
| Alinear a la guía… | botón fijo del Arreglo | Elige la pista guía en el propio menú |
| Editar tono | Detalle › Afinador | Abre el Editor de abajo en modo Tono sobre ese clip |
| Analizar tonalidad y acordes | Afinador › Detectar | Escribe la tonalidad del proyecto y la pista de acordes (Python, ver §4) |

### Pista nueva (menú **Pista**, `+ pista` y clic derecho en la zona vacía)

Diálogo único, como en Logic: Audio · Instrumento · Batería · **Intérprete IA** · **Generar con IA**.

- **Intérprete IA** (MIDI-LLM): pista de instrumento cuyo clip lo escribe la IA. Sigue la pista de
  acordes y el tempo. Estilo, densidad y «Regenerar» están en el Inspector cuando el clip está
  elegido, como los Session Players. Es MIDI normal: se edita en el piano roll.
- **Generar con IA** (ACE-Step): canción o parte en audio. El texto, la letra y la duración se
  piden en el diálogo. Se elige un rango en la regla para generar solo esa parte. Las variantes
  entran como **tomas** de la pista (carriles de tomas), no como discos en otra vista. Elegir una
  toma = escucharla en contexto.
- **Crear IA (Lab)** desaparece como vista: sus familias son «Generar con IA → parte» con el
  instrumento elegido, y sus variantes son tomas.

### Mezcla y master

| Hoy | Nuevo sitio |
|---|---|
| Inspector › Asistente IA › Mezcla IA | Menú **Mezcla › Mezcla automática…** y botón en la barra del Mezclador; ajustes en un diálogo; el resultado son los efectos «IA» de cada tira |
| Inspector › Asistente IA › Master IA | **Efecto «Master IA» en la tira MASTER** (como el Mastering Assistant de Logic); su editor sale abajo al elegirlo |
| Antes / Después | Botón A/B en la tira MASTER y en el editor del Master IA |
| Versiones del master | Archivo › Versiones del master |
| Inspector › Grabar (Cinta) | Botón ● de la cabecera de pista + entrada y monitor en el Inspector de la pista |
| Navegador › IA, › Añadir | Diálogo Pista nueva; el Navegador queda para instrumentos, efectos, sonidos y archivos |

La cabecera pierde: Crear IA, Restaurar zonas, Tema, Abrir, Inicio (van a Archivo y Ver).

### 3.1 Un solo mezclador, un solo aspecto (petición del usuario, 26-11-2026)

«La mixer de IA no es la misma que la mixer normal, no entiendo». Por debajo ya es la misma: la
Mezcla IA (V4.2) solo mueve faders, paneo, envíos y pone efectos en las tiras reales. Pero se ve
como otro aparato:
- perillas «Escalón L/R» y «Espacio vocal» propias;
- una barra de progreso tipo LCD;
- botones gigantes MEZCLAR / REMEZCLAR;
- su propio A/B, en una pestaña del Inspector.

Regla general: **una función = un sitio y un aspecto**. Lo que hace la IA se ve con los mismos
controles que lo hecho a mano, y lleva solo una marca «IA».

- La Mezcla automática es una orden del Mezclador (botón en su barra + menú Mezcla). Sus dos
  ajustes van en el diálogo de la orden. El progreso va en la barra de estado, como cualquier
  proceso.
- Lo que cambia se ve **en las tiras**: fader y paneo movidos, efectos con la marca «IA». Deshacer
  (Ctrl+Z) vuelve a la mezcla de antes.
- A/B «con / sin mezcla automática» es un conmutador en la barra del Mezclador.
- Lo mismo para el resto: el Master IA es un efecto con el mismo marco que los demás. Afinar con
  IA pone el AF-60 en la cadena. Las tomas generadas son tomas normales. Los instrumentos del
  Intérprete IA son pistas de instrumento normales.
- Fuera los estilos propios de módulo (LCD, botones gigantes, colores sueltos). Todo sale de
  `Theme.qml` y de los controles comunes de `controls/`.

## 4. Python: el DAW inteligente

El programa ya coordina en Python (`bridge.py`, `engine_host.py`). Se usa para tres cosas, siempre
fuera del hilo de audio (AGENTS.md §2) y con deshacer:

1. **Análisis del proyecto** (al importar audio y bajo demanda): tempo, tonalidad, acordes y
   secciones. Escribe la pista de acordes y los marcadores. Lo usan el Intérprete IA, la afinación,
   la Mezcla IA y el buscador de sonidos (a la tonalidad del tema, como Splice en Studio One).
2. **Paleta de órdenes (Ctrl+K)**: un registro único de acciones en Python (`actions.py`) del que
   salen los menús, los clics derechos, los atajos y la paleta. Así cada orden existe una vez y
   está en todas partes. Es lo que arregla el «recorte de cosas».
3. **Scripts del usuario** (como ReaScript): archivos `.py` en `scripts/` con una API `afo`
   (pistas, clips, efectos, análisis, transporte, deshacer). Salen en el menú **Scripts** y en la
   paleta. Se ejecutan en un proceso aparte; las órdenes vuelven al hilo principal por el puente.
   Un script no puede tocar audio en tiempo real ni bloquear la interfaz. Se incluyen ejemplos
   útiles: normalizar todas las voces, colorear por tipo, exportar stems, crear marcadores por
   sección.

## 5. Etapas (cada una deja el programa usable y pasa el selftest)

| Etapa | Qué | Hecho cuando |
|---|---|---|
| F1 | Registro de acciones (`actions.py`) + barra de menús + paleta Ctrl+K + clic derecho en clip y pista | Todas las órdenes de hoy están en menú, paleta y clic derecho con su atajo; prueba recorre el registro |
| F2 | Cabecera limpia; Inspector a la izquierda, Navegador a la derecha, sin pestañas en las zonas | Capturas en los 3 temas; nada de pestañas; contraste y objetivos en el selftest |
| F3 | Editor de abajo que sigue a la selección (audio + modo Tono, MIDI, batería, efecto, cadena) | Elegir clip/efecto/pista cambia el editor; el editor de tono sale del Afinador |
| F4 | IA sobre el clip: separar, rehacer, versión, alinear, entran como tomas o carpeta | Los botones fijos del Arreglo desaparecen; proyecto completo: separar + rehacer + deshacer |
| F5 | Pista nueva: Intérprete IA y Generar con IA con tomas; se retiran Navegador › IA y Crear IA | Generar crea tomas en la pista; regenerar desde el Inspector |
| F6 | Un solo mezclador (§3.1): Mezcla automática como orden del Mezclador, Master IA como efecto del master, A/B en la barra; fuera los estilos propios | Inspector sin Asistente IA; ningún control de IA con aspecto propio; proyectos completos siguen pasando |
| F7 | Análisis Python: tempo, tonalidad, acordes, secciones → pista de acordes y marcadores | Con `song_factory`, acierta tonalidad y acordes en 4 géneros |
| F8 | Scripts del usuario (`scripts/`, API `afo`, proceso aparte) + ejemplos | Los ejemplos corren sobre un proyecto completo y se deshacen con Ctrl+Z |

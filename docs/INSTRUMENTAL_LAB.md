# Instrumental Lab IA, adaptado a AllForOne (23-11-2026)

El usuario trajo una especificación escrita por ChatGPT sin el contexto del proyecto, más una imagen
de referencia (tres paneles: configuración, filas de variantes en discos de vinilo, pistas, y
preescucha abajo). Este documento la adapta a lo que AllForOne es y a lo que sus motores pueden
hacer de verdad. Si choca con `AGENTS.md`, manda `AGENTS.md`.

## 1. Qué se mantiene de la idea

- Se construye la instrumental **por piezas**. Cada fila es un instrumento con N variantes (4 por
  defecto). Se escucha, se elige, se bloquea y se regenera el resto. Se arrastra a las pistas.
- **Contexto musical común** a todas las variantes: tempo, compás, tonalidad, escala, duración en
  compases, género, estilo e intensidad.
- **Historial** que no se borra solo, y resultados guardados (audio, MIDI y parámetros) para reutilizarlos.

## 2. Qué cambia y por qué

| Especificación original | En AllForOne | Motivo |
|---|---|---|
| C++20 + Qt + JUCE para todo | QML dibuja → `bridge.py` → servicio Python → motores en **procesos aparte** (`ace-synth`, `afo-demucs`, `llama-server`) → motor C++ para reproducir | Arquitectura vigente (`AGENTS.md` §2). La generación nunca toca el hilo de audio |
| Pestañas CREAR IA / PISTAS / MEZCLAR / MASTER / PLUGINS | **Crear IA** es una vista principal más, junto a Arreglo y Mezclador, dentro de la distribución fija de `docs/DISENO_DAW.md`. El panel derecho de pistas es el de verdad | Una ventana con zonas fijas; sin segunda estructura de pistas |
| Rosa, púrpura y naranja neón; modos Normal y Pixel Art | Colores de `Theme` (tema sobrio X12): un color apagado por familia y un acento. No existe modo Pixel Art; existen los **temas** | El usuario pidió quitar los colores llamativos. Contraste ≥ 4,5:1 |
| Discos con ilustraciones (montañas, olas…) | Discos dibujados en QML a partir del **propio audio** de la variante: surcos según su envolvente y su espectro, en el color de la familia. Giran al sonar | Nada falso: dos variantes distintas se ven distintas porque suenan distinto. Sin imágenes inventadas |
| Kick, Snare, Clap, Hi-hat generados por separado | ACE-Step genera **batería** (`drums`), que se divide en Bombo, Caja / Clap y Platos (bandas, `stems.split_drums`). Los golpes sueltos (one-shots) para los pads de Batería se cortan de esas partes por ataques | ACE-Step no genera one-shots fiables; la división se midió (bombo 13,9 dB SDR) |
| Controles de edición avanzada (Pitch, ADSR, Punch, Densidad…) | Fase final y solo con lo que el motor ya hace (efectos nativos, ganancia, recorte y fundidos de clip, Piano Roll para MIDI). Lo que no exista no se dibuja | `AGENTS.md` §4: sin controles de adorno |
| Cambiar de variante «sin clics» con el transporte | Cada familia es una **pista real** del proyecto marcada «Lab (borrador)». Elegir otra variante cambia el audio de esa pista (`setTrackAudio`) en la misma posición, con fundidos de 5 ms en el clip. Suena en el motor y sincronizado, sin renderizar nada | Se usa el motor existente para reproducir y sincronizar |

## 3. De dónde sale cada variante (motores reales)

| Fila | Clase de ACE-Step | Notas |
|---|---|---|
| Piano / teclados | `keyboard` | |
| Batería → Bombo, Caja / Clap, Platos | `drums` | Se divide al recibirla |
| Percusión | `percussion` | |
| Bajo / 808 | `bass` | «808» se añade a la descripción |
| Guitarras | `guitar` | |
| Cuerdas | `strings` | |
| Vientos | `brass` / `woodwinds` | |
| Sintes, Pads, Leads, Arpegios | `synth` | El tipo va en la descripción |
| Texturas / FX | `fx` | |
| Personalizado | La clase más cercana | La descripción la pone el usuario |

1. **Guía (Kit completo).** Se compone una guía con ACE-Step `text2music` (el modelo turbo, con la
   descripción, el género, el tempo, la tonalidad y la duración). Demucs la separa, y cada fuente
   (con la batería dividida) es la **V1** de su familia. Así todas las V1 nacen de la misma canción
   y encajan.
2. **Variantes V2…Vn de una familia.** Se generan con ACE-Step `lego` (modelo base) de esa clase
   sobre el **contexto**: la mezcla de las variantes elegidas en las demás familias, o la guía sin
   esa familia. Cada variante usa otra semilla, así que el resultado es distinto de verdad. La
   prueba lo mide: correlación < 0,5 entre variantes.
3. **Regenerar.** Se hace lo mismo para las variantes no bloqueadas, con semillas nuevas. Las
   anteriores pasan al historial.
4. **«Parecida a esta».** Se usa ACE-Step `cover` con la variante como fuente y una fuerza
   moderada: conserva el carácter y cambia los detalles.
5. **Instrumento de referencia.** Si una familia se marca como referencia, siempre entra en el
   contexto de las siguientes generaciones.
6. **Modo Patrones (MIDI).** MIDI-LLM (`midi_ai.py`) compone notas por instrumento al tempo y en la
   tonalidad del contexto. Suenan con el sintetizador interno o un VST3 y se editan en el Piano Roll.
7. **Modo Instrumento y patrón.** Es el audio de ACE-Step: sonido e interpretación van juntos.

**Longitud y alineación.** La duración se fija en compases. Todas las variantes se recortan o
completan a la longitud exacta (compases × compás × 60 / BPM) y empiezan en el compás 1. Cambiar de
variante nunca desplaza el ritmo.

**Tiempos medidos en este equipo (RX 7800 XT):**
- `lego`: unos 10 s por cada 16–30 s de audio.
- Demucs (CPU): unos 5 s por cada segundo de audio.
- Por eso la guía avisa de cuánto tardará, y cada variante aparece en cuanto está lista.

## 4. Persistencia

- Cada sesión del laboratorio vive en `datos/media/lab/<fecha>_<nombre>/`:
  - `lab.json` con el contexto, las familias, las variantes, la semilla, el modelo, la petición,
    el estado (elegida, bloqueada, favorita) y el historial;
  - un WAV por variante, y un `.mid` si es MIDI.
- Nada va a carpetas temporales.
- Quitar una variante la mueve a `.papelera` de la sesión.
- Las favoritas se ven en el Navegador › IA › Laboratorio para usarlas en otros proyectos (enlaza
  con la Biblioteca, X10).

## 5. Reparto y fases

| ID | Dueño | Qué |
|---|---|---|
| C8 | Claude | `lab.py`: sesión, contexto, cola cancelable (un motor de IA a la vez), guía (`text2music`) + Demucs → V1, variantes `lego`, bloquear, regenerar, «parecida», historial y `lab.json`. Slots `lab*` en `bridge.py`. Pruebas con proyectos completos de hip-hop, trap, lo-fi, house y cinematográfica: longitud exacta, variantes distintas, alineadas con el contexto, bloqueadas conservadas al regenerar y recarga desde disco |
| C9 | Claude | Preescucha con pistas reales «Lab (borrador)»: cambiar de variante, solo y mute por familia, «Enviar al proyecto» (quita la marca de borrador) y «Descartar». Golpes sueltos para los pads de Batería |
| X18 | Codex | `LabView.qml`: los tres paneles de la referencia con los colores del tema, discos dibujados del audio que giran al sonar, filas por familia, «Regenerar (N variantes)», barra de preescucha, y arrastrar un disco a una pista, a una pista nueva o a una posición del Arreglo |
| X19 | Codex | Editar variante: solo controles que actúen de verdad (efectos nativos y clip); MIDI al Piano Roll |

Cada fase deja el laboratorio usable y pasa el selftest. Lo que aún no exista se dice en la propia
vista: «Patrones MIDI: próximamente» o similar, nunca un botón que no hace nada.

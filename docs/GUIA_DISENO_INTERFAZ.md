# Guía de diseño de interfaz de AllForOne

Resumen de estudio (noviembre 2026) aplicado a un DAW modular. Cada regla dice de dónde sale y cómo se
comprueba en AllForOne. Lo que se puede medir, se mide en `--selftest` (contraste y tamaño de los
botones); lo demás se revisa con esta lista antes de dar un módulo por terminado.

Fuentes:
- Jakob Nielsen, *10 Usability Heuristics* — nngroup.com/articles/ten-usability-heuristics
- Ben Shneiderman, *Eight Golden Rules of Interface Design* — cs.umd.edu/~ben/goldenrules.html
- W3C, WCAG 2.2: 1.4.3 *Contrast (Minimum)* y 2.5.8 *Target Size (Minimum)*
- NN/g, *Progressive Disclosure* y *Visual Hierarchy*
- Laws of UX: Fitts, Hick y Proximidad — lawsofux.com
- Manual de Ableton Live 12, cap. 23 (*Working with Instruments and Effects*): convenciones de la vista
  de dispositivos.

## 1. Estado siempre visible (Nielsen 1, Shneiderman 3)

- **Barra de estado fija** abajo: dispositivo de audio (driver, salida, frecuencia, búfer y latencia),
  proyecto y si hay cambios sin guardar, y la ayuda del sitio donde está el ratón. Sin salida de audio,
  la barra lo dice en rojo, con texto e icono (no solo color), y lleva a «⚙ Audio».
- Toda acción responde al momento. Las menores, con un cambio en el propio control; las importantes
  (guardar, masterizar, exportar), con un aviso que dice el resultado («Guardado: canción.afo»).
- Las tareas largas (mezcla automática, master, búsqueda de plugins) muestran progreso y terminan con
  un cierre claro (Shneiderman 4).

## 2. El lenguaje del músico (Nielsen 2)

- Términos de estudio: pista, canal, rack, cadena, envío, master, bypass, preset. Nada de nombres
  internos (`fx~2`, `uid`, códigos de error).
- **Cada valor con su unidad** junto al control: dB, Hz, kHz, ms, s, %, BPM, LUFS.
- Mapeo natural: el orden de la cadena en pantalla es el orden de la señal (izquierda → derecha); los
  cables siguen el camino del sonido.

## 3. Control, deshacer y prevención de errores (Nielsen 3 y 5, Shneiderman 5 y 6)

- Lo destructivo y sin deshacer (borrar una pista, una versión de master) pide **confirmación en el
  mismo sitio**: el primer clic convierte el botón en «¿Borrar?», el segundo lo hace; si no, vuelve solo.
- Las ediciones de clip tienen deshacer / rehacer (Ctrl+Z / Ctrl+Y). Esc cierra o restaura.
- Los campos numéricos solo aceptan valores válidos (validador y rango); lo que no se puede hacer se
  desactiva y su ayuda dice por qué.
- Un error del programa nunca deja la interfaz rota: el puente devuelve `{"ok": false}` y el aviso
  dice qué pasó y qué hacer (Nielsen 9), y el detalle va a `logs/allforone.log`.

## 4. Consistencia (Nielsen 4, Shneiderman 1)

- Todos los módulos tienen la misma cabecera: color del módulo, título, modelo, □ maximizar, ✕ cerrar.
- Todos los dispositivos de efecto tienen la misma cabecera (como en Ableton): activador (círculo
  encendido = procesa; apagado = la señal pasa sin tocar), nombre, mover ◀ ▶, detalle ≡ y quitar ✕;
  doble clic en el nombre lo pliega.
- Mismo icono, color y sitio para el mismo concepto en todas partes. Colores reservados: el acento
  para la acción principal y la selección; el rojo, solo para grabar, recortes y errores.
- Colores y medidas salen del tema (`Theme.qml`), nunca fijos en un módulo.

## 5. Reconocer mejor que recordar (Nielsen 6, Shneiderman 8)

- Lo necesario para decidir está a la vista: el rack muestra de qué canal es; el master, su LUFS.
- Ayudas emergentes en todo botón con símbolo: qué hace y su atajo de teclado entre paréntesis.
- Estados vacíos con la acción siguiente visible («Sin efectos. + Agregar efecto»).

## 6. Expertos y principiantes (Nielsen 7, Shneiderman 2)

- Atajos estándar: Espacio reproducir / pausa, Ctrl+S guardar, Ctrl+O abrir, Ctrl+Z / Ctrl+Y
  deshacer / rehacer, Supr borrar, Ctrl+D duplicar, S dividir, Esc salir del maximizado.
- Los atajos nunca son la única vía: todo tiene botón.

## 7. Jerarquía, espacio y revelación progresiva (Nielsen 8, NN/g)

- **Rejilla de 4 px**: márgenes y separaciones en 4, 8, 12, 16, 24.
- **Tres tamaños de texto** por vista: etiqueta (11–12 px), valor / cuerpo (13–14 px) y título
  (16–19 px). Pesos 500–700.
- Proximidad: más espacio entre grupos que dentro de un grupo; el título de un grupo pegado a él. Un
  recuadro solo cuando el espacio no basta.
- Primero lo frecuente; lo avanzado (presets propios, automatización, latencia) en el detalle (≡).
  Como mucho dos niveles.
- Prueba del entrecerrado: con la vista desenfocada se ve primero lo más importante del módulo.

## 8. Contraste y tamaño (WCAG 2.2 AA) — se mide

- Texto normal ≥ **4,5 : 1** con su fondo; texto grande (≥ 24 px, o ≥ 18,5 px en negrita) ≥ 3 : 1.
  Sin redondear. Nada de bajar la opacidad del texto por debajo de eso.
- Controles e indicadores sin texto (bordes de campos, perillas, medidores) ≥ 3 : 1 con lo de al lado.
- **Objetivos de clic ≥ 24 × 24 px**; los de uso continuo (transporte) ≥ 32 px de alto.
- `--selftest` calcula el contraste de los pares de cada tema (texto sobre fondo, cabecera, cuerpo de
  cada módulo, dispositivos, campos) y falla si alguno no llega.

## 9. Fitts y Hick

- Lo frecuente, grande y cerca: transporte arriba a la izquierda; acciones de un módulo dentro de él.
- Pocas opciones a la vez y una recomendada (el botón principal lleva el acento).

## Lista de revisión de un módulo

1. ¿Dice lo que pasa (estado, progreso, resultado)?
2. ¿Usa palabras de músico y unidades en cada valor?
3. ¿Lo destructivo se confirma o se deshace?
4. ¿Su cabecera y sus controles son iguales a los demás?
5. ¿Tiene estado vacío con la acción siguiente?
6. ¿Cada botón de símbolo tiene ayuda (y atajo si lo hay)?
7. ¿Respeta la rejilla de 4 px, tres tamaños de texto y la proximidad?
8. ¿Contraste ≥ 4,5 : 1 y botones ≥ 24 px en los tres temas?
9. ¿Funciona igual en AllForOne, AllForOne Oscuro y Professional?

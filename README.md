# AllForOne

DAW modular gratuito para Windows: la interfaz original `templates/AllForOne/PLANTILLA_DAW.html` convertida en una
aplicación de escritorio nativa (Qt Quick, sin navegador interno) con motor de audio nativo C++ (JUCE + Tracktion Engine), lógica en Python
y el Mezclador Automático V4.2 integrado por fases.

**Versión actual: 0.3.0 (beta).** La interfaz nativa (sin navegador interno) se describe en `docs/INTERFAZ_NATIVA.md`.

## Compilar y abrir (Windows 11 x64)

1. Doble clic en **`build_and_run.bat`**: prepara todo dentro de esta carpeta (Python portátil en
   `.toolchains` si hace falta, `.venv`, JUCE y Tracktion en `.deps`), compila el motor, ejecuta las
   pruebas (incluidas las 27 originales del Mezclador V4.2) y abre AllForOne.
2. Doble clic en **`package_windows.bat`**: genera el programa en **`EXE\AllForOne.exe`**, crea el
   acceso directo `AllForOne.lnk` en esta carpeta y el ZIP para publicar en `release\`.
   Tus mezclas y ajustes quedan en `EXE\datos` y se conservan al actualizar.

Todo lo que AllForOne escribe (datos, registros, cachés, temporales) queda dentro de esta carpeta.

## Uso rápido

1. Arrastra tus audios al módulo **Audios**. Cada uno crea **su pista** y, con ella, **su tira en
   la consola**. Si el motor no sabe leer el formato (p. ej. WAV de 64 bits), se convierte una
   copia y te avisa; tu archivo original no se toca.
2. Ajusta el **rol de voz** (P, B, L, R, B_L, B_R) donde te venga mejor: en Audios, en Pistas o en
   la tira de la consola.
3. En **Mezcla** elige la plantilla trap/rap y pulsa **MEZCLAR AUTOMÁTICAMENTE**. La mezcla es
   **en vivo**: el Mezclador V4.2 decide y deja en cada pista su fader, su paneo y una cadena de
   efectos real (EQ, de-esser, compresión, saturación, espacio, eco) que puedes abrir y ajustar en
   **Efectos**; no se renderiza ningún WAV. La mezcla automática solo mezcla: el master va aparte.
4. Para afinar voces: **Afinador** → Analizar música → Confirmar → sube la intensidad (sus cables
   te muestran a qué tiras está conectado).
5. **Flujo del sonido** (los cables lo muestran): Instrumentos → Piano roll → Pistas; Pistas con IA,
   Grabador de voz y Audios → Pistas; Pistas → Mezcla (una tira con su rack por pista) → Efectos y
   Antes / Después; Mezcla → **Mastering** (VU, LUFS / RMS / pico, fader, saturación, tono, limitador)
   → **Efectos master** (la cadena del master y, abajo, **MASTERIZAR AUTOMÁTICAMENTE**: mide la
   sesión en el motor, sin archivos, y pone la cadena) → **Rebobinado**, donde quedan las versiones
   de master (automáticas y las que guardas con «Guardar versión»): eliges una y exportas.
   Las tiras de Mezcla miden en **dB, LUFS o RMS** (a elegir).
   **Temas:** el selector «Tema» de la cabecera cambia el aspecto (AllForOne, AllForOne Oscuro,
   Professional). Cada tema es una carpeta de `templates/` con un `theme.json`; para compartir uno,
   copia su carpeta en la carpeta `templates` de tu amigo (📁 la abre) y pulsa ↻.

6. **Grabar voz:** «+ Voz» en Pistas y, en el **Grabador de cintas**, elige la entrada y pulsa
   ● Grabar (graba el motor). Si tu dispositivo no tiene entradas, pulsa **Audio** en la cabecera y
   elige otro driver (por ejemplo ASIO4ALL).
7. **Efectos:** clic en el nombre de una tira de Mezcla y el módulo **Efectos** muestra su rack:
   la cadena a la izquierda (activar, ordenar, quitar, **+ Agregar efecto** sin límite) y una
   tarjeta por efecto con su gráfica, preset y perillas. **Efectos master** es el mismo rack para el
   master. En el detalle (≡) de cada efecto: medidores, presets propios y **Automatización** (dibuja
   la curva de un parámetro sobre los 16 compases; suena al reproducir y al exportar).
8. **Proyecto:** **Guardar** / **Abrir** en la cabecera (Ctrl+S / Ctrl+O) guardan y recuperan la
   sesión entera en un archivo `.afo`: pistas, notas, tomas, cortes de audio, efectos con su
   automatización, plugins VST3 con su estado y master.
9. **Menú lateral (☰):** *Módulos* lleva a cada módulo (miniatura en vivo; doble clic en el nombre
   para renombrarlo; **+** agrega otro rack de Efectos o una pista), *Instrumentos* (sintetizador del
   motor, Drum pad, voz, audio y tus instrumentos VST3) y *Efectos* (la Biblioteca nativa por
   familias y tus efectos VST3; se agregan al rack elegido). **Buscar plugins** explora las carpetas
   VST3 de Windows en un proceso aparte (si un plugin se cuelga o rompe la búsqueda, se salta y se
   sigue; AllForOne no se cierra) y guarda la lista.
10. **Pistas como en un DAW:** □ en la cabecera de un módulo (o doble clic) lo maximiza al visor; Esc
   vuelve. En Pistas: mover clips (con rejilla), recortar por los bordes, dividir (S o herramienta
   Cortar), duplicar (Ctrl+D), borrar (Supr), volumen por clip (arrastra la etiqueta dB o Vol −/+),
   normalizar, fundidos de entrada y salida, deshacer / rehacer (Ctrl+Z / Ctrl+Y) y zoom. Los módulos
   chocan entre sí: al arrastrar uno se detiene antes de pisar otro. Su tamaño es fijo: solo cambia
   si lo cambias tú (asas de las esquinas), y se guarda.

**Interfaz (Qt Quick, sin navegador interno):** `python -m allforone` desde `app/`. Funcionan el
lienzo, Pistas, Audios, la consola Mezcla con la mezcla automática, Mezcla final, Afinador, Master
IA, Antes / Después, Piano roll, Instrumentos, Batería (con el sintetizador del motor), Pistas con
IA (demo), el **Grabador de cintas** (graba el motor), la
**configuración de audio** (botón «Audio»: Windows Audio, DirectSound o cualquier driver ASIO como
ASIO4ALL) y el módulo **Efectos** con la Biblioteca nativa (Hito 1: Gain, Channel Strip, Parametric
EQ, Compressor, Gate, De-Esser, Saturator, Space, Digital Delay y Spectrum Analyzer, con presets y
automatización), y Abrir / Guardar proyecto
(`docs/INTERFAZ_NATIVA.md`, `docs/BIBLIOTECA_NATIVA.md`).

## Estructura

```
templates/<Tema>/theme.json  temas (AllForOne, AllForOne Oscuro, Professional; copiar = compartir)
templates/AllForOne/PLANTILLA_DAW.html  interfaz original (referencia visual, no se edita)
CMakeLists.txt, cmake/      motor nativo y dependencias fijadas
native/src/                 AfoEngine (fachada sobre Tracktion Engine) y AfoSynth (sintetizador)
native/src/fx/              Biblioteca nativa AFO: DSP compartida y efectos (plugins de Tracktion)
native/bindings/            extensión Python afo_audio (pybind11)
native/tests/               pruebas nativas (ctest)
app/allforone/              aplicación Python (PySide6): coordina motor, mezclador e interfaz
app/allforone/qml/          interfaz Qt Quick: Main.qml y theme/, controls/, modules/, state/, assets/
tests/                      pruebas Python (pytest)
app/allforone/mixer_v42/    Mezclador Automático V4.2 original (sin cambios)
app/allforone/mixer_service.py  adaptador del mezclador para los paneles
app/allforone/audio_import.py    formatos que el motor no lee (WAV de 64 bits): copia convertida
app/allforone/project.py    proyecto .afo (guardar / abrir); fx_presets.py: presets de efectos
tools/                      build.ps1, package.ps1, native_compare.py (plantilla vs interfaz)
docs/                       especificación, cambios de la plantilla e interfaz nativa
```

## Licencia

AllForOne es software libre bajo la **GNU AGPL v3** (`LICENSE`). Componentes de terceros en
`THIRD_PARTY_NOTICES.md`.

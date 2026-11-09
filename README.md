# AllForOne

DAW modular gratuito para Windows: la interfaz original `templates/PLANTILLA_DAW.html` convertida en una
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
   **Efectos**; no se renderiza ningún WAV. Al terminar, Master IA masteriza en vivo (opcional).
4. Para afinar voces: **Afinador** → Analizar música → Confirmar → sube la intensidad (sus cables
   te muestran a qué tiras está conectado).
5. **Master IA:** un clic en un preset (Dinámico, Comercial, Fuerte, Plataformas o según tu
   referencia) mide la sesión en el motor —en memoria, sin archivos— y pone la cadena del master;
   la ves en **Efectos master**. **Antes / Después:** dos pantallas en vivo, la señal que entra a una
   cadena y la que sale, conectables al rack del canal o al master. Las tiras de Mezcla miden en
   **dB, LUFS o RMS** (a elegir); Master IA muestra las tres del master. El botón **◐** cambia al
   tema oscuro.

6. **Grabar voz:** «+ Voz» en Pistas y, en el **Grabador de cintas**, elige la entrada y pulsa
   ● Grabar (graba el motor). Si tu dispositivo no tiene entradas, pulsa **Audio** en la cabecera y
   elige otro driver (por ejemplo ASIO4ALL).
7. **Efectos:** clic en el nombre de una tira de Mezcla y el módulo **Efectos** muestra su rack:
   la cadena a la izquierda (activar, ordenar, quitar, **+ Agregar efecto** sin límite) y una
   tarjeta por efecto con su gráfica, preset y perillas. **Efectos master** es el mismo rack para el
   master. En el detalle (≡) de cada efecto: medidores, presets propios y **Automatización** (dibuja
   la curva de un parámetro sobre los 16 compases; suena al reproducir y al exportar).
8. **Proyecto:** **Guardar** / **Abrir** en la cabecera (Ctrl+S / Ctrl+O) guardan y recuperan la
   sesión entera en un archivo `.afo`: pistas, notas, tomas, efectos con su automatización y master.

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
templates/PLANTILLA_DAW.html  interfaz original (referencia visual, no se edita)
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

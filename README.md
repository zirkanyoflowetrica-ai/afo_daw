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
3. En **Mezcla** elige la plantilla trap/rap y pulsa **MEZCLAR AUTOMÁTICAMENTE**: verás las tiras
   encenderse y los faders colocarse en los niveles que decide el mezclador.
4. Para afinar voces: **Afinador** → Analizar música → Confirmar → sube la intensidad (sus cables
   te muestran a qué tiras está conectado).
5. Escucha y compara en **Master IA** y **Antes / Después**. El botón **◐** cambia al tema oscuro.

6. **Grabar voz:** «+ Voz» en Pistas y, en el **Grabador de cintas**, elige la entrada y pulsa
   ● Grabar (graba el motor). Si tu dispositivo no tiene entradas, pulsa **Audio** en la cabecera y
   elige otro driver (por ejemplo ASIO4ALL).
7. **Efectos:** en el módulo **Efectos** elige la pista o el master e inserta los de la biblioteca.

**Interfaz (Qt Quick, sin navegador interno):** `python -m allforone` desde `app/`. Funcionan el
lienzo, Pistas, Audios, la consola Mezcla con la mezcla automática, Mezcla final, Afinador, Master
IA, Antes / Después, Piano roll, Instrumentos, Batería (con el sintetizador del motor), Pistas con
IA (demo), el **Grabador de cintas** (graba el motor), la
**configuración de audio** (botón «Audio»: Windows Audio, DirectSound o cualquier driver ASIO como
ASIO4ALL) y el módulo **Efectos** con la Biblioteca nativa (Hito 1: Gain, Channel Strip, Parametric
EQ, Compressor, Gate, Saturator, Space, Digital Delay y Spectrum Analyzer)
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
tools/                      build.ps1, package.ps1, native_compare.py (plantilla vs interfaz)
docs/                       especificación, cambios de la plantilla e interfaz nativa
```

## Licencia

AllForOne es software libre bajo la **GNU AGPL v3** (`LICENSE`). Componentes de terceros en
`THIRD_PARTY_NOTICES.md`.

# AllForOne

DAW modular gratuito para Windows: la interfaz original `PLANTILLA_DAW.html` convertida en una
aplicación de escritorio con motor de audio nativo C++ (JUCE + Tracktion Engine), lógica en Python
y el Mezclador Automático V4.2 integrado por fases.

**Versión actual: 0.3.0 (beta)** — ver `docs/INFORME_V0.3.md` (qué funciona, qué no y cómo se probó).

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

## Estructura

```
PLANTILLA_DAW.html          interfaz original (referencia, no se edita)
Mezclador_Automatico.zip    mezclador V4.2 original (referencia)
CMakeLists.txt, cmake/      motor nativo y dependencias fijadas
native/src/                 AfoEngine (fachada sobre Tracktion Engine)
native/bindings/            extensión Python afo_audio (pybind11)
native/tests/               pruebas nativas (ctest)
app/allforone/              aplicación Python (PySide6 + Qt WebEngine + QWebChannel)
app/allforone/ui/           index.html (= plantilla + 3 líneas), afo_bridge.js, fuentes locales
tests/                      pruebas Python (pytest)
app/allforone/mixer_v42/    Mezclador Automático V4.2 original (sin cambios)
app/allforone/mixer_service.py  adaptador del mezclador para los paneles
app/allforone/audio_import.py    formatos que el motor no lee (WAV de 64 bits): copia convertida
tools/                      build.ps1, package.ps1, visual_compare.py
docs/                       especificación, auditoría, cambios de la plantilla, informes
```

## Licencia

AllForOne es software libre bajo la **GNU AGPL v3** (`LICENSE`). Componentes de terceros en
`THIRD_PARTY_NOTICES.md`.

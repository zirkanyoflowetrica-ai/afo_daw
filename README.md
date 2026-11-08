# AllForOne

DAW modular gratuito para Windows: la interfaz original `PLANTILLA_DAW.html` convertida en una
aplicación de escritorio con motor de audio nativo C++ (JUCE + Tracktion Engine), lógica en Python
y el Mezclador Automático V4.2 integrado por fases.

**Versión actual: 0.1** — ver `docs/INFORME_V0.1.md` (qué funciona, qué no y cómo se probó).

## Compilar y abrir (Windows 11 x64)

1. Doble clic en **`build_and_run.bat`**.
   Detecta Python 3.12, Git y Visual Studio Build Tools (ofrece instalarlos con winget si faltan),
   crea `.venv` con versiones fijadas, descarga JUCE y Tracktion Engine en `.deps`, compila
   `afo_audio.pyd`, ejecuta las pruebas y abre AllForOne. La primera vez tarda 15–40 min.
2. Doble clic en **`package_windows.bat`** para crear `dist\AllForOne\AllForOne.exe`
   (carpeta standalone; no necesita Python ni este código fuente) y `dist\AllForOne-0.1.0-win64.zip`.
3. Doble clic en **`install_windows.bat`** para instalarlo en `%LOCALAPPDATA%\Programs\AllForOne`
   con accesos directos en el menú Inicio y el escritorio (sin administrador).
   Desinstalar: `powershell -ExecutionPolicy Bypass -File tools\install.ps1 -Uninstall`.

Si no hay Python 3.12, el script descarga uno portátil oficial (python.org vía NuGet) en
`.toolchains`; si no hay Git, descarga MinGit. Visual Studio Build Tools (C++) sí debe estar instalado
(el script ofrece instalarlo con winget, requiere administrador).

Registros en `logs\`. Datos del usuario en `%LOCALAPPDATA%\AllForOne`.

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
tools/                      build.ps1, package.ps1, visual_compare.py
docs/                       especificación, auditoría, cambios de la plantilla, informes
```

## Licencia

AllForOne es software libre bajo la **GNU AGPL v3** (`LICENSE`). Componentes de terceros en
`THIRD_PARTY_NOTICES.md`.

# Componentes de terceros y licencias

> Esto es un resumen técnico, no asesoría legal. Revísalo antes de publicar AllForOne.

## Consecuencia principal

AllForOne enlaza **JUCE 8** (AGPLv3 o licencia comercial) y **Tracktion Engine** (GPLv3+ o licencia
comercial). Por eso **AllForOne se publica bajo la AGPLv3** (`LICENSE`), como proyecto gratuito y
de código abierto en GitHub. Requisito práctico: cada binario que se distribuya (por ejemplo el ZIP
de una release) debe ir acompañado del código fuente correspondiente, lo que se cumple publicando
el repositorio y etiquetando cada versión.

| Componente | Versión | Licencia | Uso |
|---|---|---|---|
| JUCE | commit `19edd538` (8.0.6+19) | AGPLv3 / JUCE 8 EULA comercial | Audio, dispositivos, formatos, hosting VST3 |
| Tracktion Engine | v3.2.0 | GPLv3 o posterior / comercial | Motor DAW (Edit, pistas, transporte, render) |
| pybind11 | 3.1.0 | BSD-3-Clause | Extensión `afo_audio` |
| Qt / PySide6 (incl. Qt WebEngine, Chromium) | 6.12.0 | LGPLv3 (Qt), licencias de Chromium | Ventana, interfaz HTML, QWebChannel. Se distribuye como DLL separadas (sustituibles) |
| NumPy | 2.5.4 | BSD-3-Clause | Verificación y análisis |
| soundfile / libsndfile | 0.14.0 | BSD-3-Clause / LGPL-2.1 | Lectura de audio en Python |
| Nuitka (runtime) | 4.3.4 | Apache-2.0 | Empaquetado del ejecutable |
| Space Grotesk | fontsource 5.2.10 | SIL OFL 1.1 (`app/allforone/ui/fonts/OFL-SpaceGrotesk.txt`) | Tipografía de la interfaz |
| VST3 SDK (incluido en JUCE) | — | GPLv3 / MIT según versión del SDK en JUCE | Hosting VST3 |
| Steinberg ASIO SDK | 2.3.4 (2025-10-15) | Doble licencia: propietaria de Steinberg **o GPLv3** (`LICENSE.txt` del SDK); aquí se usa bajo **GPLv3**, compatible con la AGPLv3 de AllForOne | Drivers ASIO (ASIO4ALL, los de cada interfaz…). Se descarga al compilar (`cmake/deps.cmake`, SHA-256 fijado); no se guarda en el repositorio |

Mezclador Automático V4.2 (se integra en V0.5): `pedalboard` (GPLv3), `praat-parselmouth` (GPLv3),
`pyloudnorm` (MIT), `scipy` (BSD), `librosa` (ISC). Los pesos opcionales de DrumSep tienen términos
no aclarados y no se distribuirán. ASIO está activado con el SDK de Steinberg bajo GPLv3 (ver la
tabla); también se usan WASAPI y DirectSound. «ASIO» es una marca de Steinberg Media Technologies
GmbH. AllForOne no incluye ni redistribuye ningún driver ASIO (ASIO4ALL se instala aparte).

No se redistribuyen plugins VST comerciales de terceros.

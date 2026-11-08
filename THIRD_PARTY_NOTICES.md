# Componentes de terceros y licencias

> Esto es un resumen técnico, no asesoría legal. Revísalo antes de publicar AllForOne.

## Consecuencia principal

AllForOne enlaza **JUCE 8** (AGPLv3 o licencia comercial) y **Tracktion Engine** (GPLv3+ o licencia
comercial). Sin licencias comerciales, distribuir AllForOne —aunque sea gratis— obliga a publicarlo
bajo una licencia compatible (en la práctica **AGPLv3**) y a ofrecer el código fuente completo
correspondiente a cada binario distribuido. **Decisión pendiente del propietario:** elegir y añadir
el archivo `LICENSE` del proyecto antes de la primera publicación.

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

Mezclador Automático V4.2 (se integra en V0.5): `pedalboard` (GPLv3), `praat-parselmouth` (GPLv3),
`pyloudnorm` (MIT), `scipy` (BSD), `librosa` (ISC). Los pesos opcionales de DrumSep tienen términos
no aclarados y no se distribuirán. ASIO está desactivado (requiere el SDK de Steinberg con su propia
licencia); se usan WASAPI y DirectSound.

No se redistribuyen plugins VST comerciales de terceros.

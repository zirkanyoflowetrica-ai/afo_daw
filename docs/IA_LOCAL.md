# IA local: canciones (audio) y composiciones MIDI dentro de AllForOne

El módulo **Pistas con IA** tiene dos modos, que se eligen arriba del módulo y no se mezclan:

- **Canción (audio)**: ACE-Step genera una canción entera, instrumental o **con voz cantando tu letra**,
  como un WAV (las secciones de abajo).
- **Solo MIDI**: MIDI-LLM compone **solo las notas**. Cada instrumento entra como su propia pista de
  Instrumento o Batería, editable, que suena con el sintetizador del motor o con el VST3 que elijas
  (sección «Composición MIDI» al final). También importa archivos `.mid`.

## Canción en audio (ACE-Step)

El modo **Canción (audio)** (Cerebro AI-1) compone y sintetiza canciones de verdad en tu equipo,
sin internet (salvo para bajar los modelos una vez) y sin programas aparte. El resultado es un WAV
estéreo de 48 kHz que entra como **pista de audio** en Pistas: se mezcla, se le ponen efectos y se
masteriza como cualquier otra.

## Cómo funciona

| Pieza | Dónde | Qué hace |
|---|---|---|
| Motor | `EXE\motores\acestep\` (`ace-lm.exe`, `ace-synth.exe`, DLL de GGML con Vulkan) | [acestep.cpp](https://github.com/ServeurpersoCom/acestep.cpp) (MIT), commit `973517b`, compilado con `tools\build_acestep.bat` |
| Modelos | `EXE\modelos\acestep\` | GGUF de [Serveurperso/ACE-Step-1.5-GGUF](https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF), descargados desde el módulo |
| Servicio | `app/allforone/ai_music.py` | Rutas, paquetes de modelos, descarga reanudable, petición y avance |
| Puente | `bridge.py`: `aiStatus`, `aiDownload`, `aiCancelDownload`, `aiGenerate`, `aiCancel`; señal `aiEvent` | Solo viajan textos de estado; el audio nunca pasa por el puente |
| Interfaz | `qml/modules/IaBody.qml`, `qml/state/Sequencer.qml` (sección «Pistas con IA») | Descripción, estilo, tonalidad, duración, tempo, voz, avance e historial |

Generar son dos procesos del motor, uno tras otro (si uno falla o se cancela, AllForOne sigue):

1. `ace-lm` (el compositor, un LM de 4B o 1,7B) escribe la estructura, la letra si la hay y los
   códigos de audio a 5 por segundo.
2. `ace-synth` (DiT turbo de 8 pasos + VAE) convierte esos códigos en audio.

El avance sale del registro de cada proceso (`progress_of`: pasos del compositor, pasos del DiT,
VAE) y llega a la barra del módulo y a la barra de estado («● IA generando 42 %»). En una RX 7800 XT
(16 GB, Vulkan) 30 s de música tardan unos 12 s con los modelos ya en caché del disco.

Cada generación se guarda en `datos\media\ia\` como `<fecha>_<estilo>_<descripción>.wav` y un `.json`
con lo que pediste y lo que decidió el compositor (tempo, tonalidad, duración, semilla). El módulo
lista las últimas y «+ Pista» las vuelve a añadir al proyecto. Si algo falla, el registro de cada
paso queda en `datos\media\ia\.trabajo_<nombre>\` (`lm.log`, `synth.log`).

## Modelos

| Paquete | Archivos | Tamaño | Para |
|---|---|---|---|
| Calidad | Qwen3-Embedding-0.6B-Q8_0, acestep-5Hz-lm-4B-Q8_0, acestep-v15-turbo-Q8_0, vae-BF16 | 7,6 GB | tarjetas de 12 GB o más |
| Ligero | igual, con acestep-5Hz-lm-1.7B-Q8_0 | 5,3 GB | tarjetas de 8 GB |

El módulo recomienda uno según la memoria de la tarjeta (registro de Windows). La descarga escribe en
`<archivo>.parte` y, si se corta o la pausas, «Reanudar» pide solo lo que falta (cabecera `Range`);
al terminar se comprueba el tamaño exacto. `package.ps1` conserva `EXE\modelos` al actualizar.

## Qué se le pide al modelo

`build_request` traduce el módulo a la petición de ACE-Step:

- **Descripción + estilo** → `caption` (el estilo añade etiquetas en inglés, como se entrenó el modelo).
- **Tonalidad** → `keyscale` («La elige la IA» la deja libre).
- **Tempo** → `bpm` del proyecto o libre.
- **Duración** → 30 s a 3 min (`duration`, límite 10–240 s).
- **Creatividad** → `lm_temperature` de 0,60 a 1,10.
- **Instrumental** → `lyrics: "[Instrumental]"`; **Con voz** canta tu letra o, vacía, la que escriba el compositor.

## Pruebas

`tests/test_ai_music.py`: la petición, el avance leído del registro, nombres sin acentos, estado de
los paquetes, la descarga reanudable contra un servidor local que corta la conexión a mitad, y una
**generación real** de 10 s en la GPU (se salta si el motor o los modelos no están instalados) que
comprueba WAV estéreo de 48 kHz, duración, que no es silencio, avance siempre hacia delante y que el
compositor respetó tempo y tonalidad. `--selftest` comprueba que el estado se lee y que «+ IA» lleva
al generador sin crear pistas vacías.

## Composición MIDI (MIDI-LLM)

| Pieza | Dónde | Qué hace |
|---|---|---|
| Motor | `motores\llama\llama-server.exe` + DLL de GGML (Vulkan) | llama.cpp v1.0.0 (MIT), compilado con `tools\build_llama.bat`; proceso aparte que solo escucha en 127.0.0.1 |
| Modelo | `modelos\midi\MIDI-LLM_Llama-3.2-1B.Q8_0.gguf` (1,84 GB) | Llama 3.2 1B con 55 030 fichas de notas (vocabulario de Anticipatory Music Transformer); se descarga desde el módulo, reanudable |
| `app/allforone/midi_ai.py` | | arranca el servidor con la primera composición (y lo cierra al salir), pide las fichas en tandas para avisar del avance y poder cancelar, las decodifica y guarda el `.mid` |

- **Qué se le pide**: la frase de MIDI-LLM («You are a world-class composer…» + tu descripción) y la
  ficha de inicio de música; muestreo con temperatura 0,7–1,2 según «Creatividad» y top-p 0,98. Entiende
  mejor descripciones en inglés.
- **Qué devuelve**: tríos (tiempo en centésimas de segundo, duración, instrumento·128 + nota). Se
  descartan las fichas sueltas, se quitan notas repetidas y, si sale algo roto (más de 64 notas a la
  vez, como en el MIDI-LLM original), se vuelve a intentar con otra semilla.
- **En el DAW**: una pista por instrumento General MIDI. Las familias van al sonido más cercano del
  sintetizador (pianos → Piano de cola, bajos → Bajo sintético, cuerdas y metales → Cuerdas, coros →
  Voz coral…) y la percusión del canal 10 a los 8 carriles de la Batería (bombo, caja, hi-hats…).
  Los segundos se conservan al tempo del proyecto. Las notas llevan **duración y velocidad propias**:
  el motor tiene `set_synth_midi` y el sintetizador sostiene la nota hasta el note-off (con el release
  de cada sonido); las pistas de la rejilla de 16 pasos siguen sonando como siempre.
- **Edición**: una pista con MIDI no se edita en la rejilla de 16 pasos (lo avisa); se le puede poner
  cualquier VST3 como instrumento, mezclar y automatizar como las demás. El proyecto guarda las notas.
- Las composiciones quedan en `datos\media\ia\*.mid` (con un `.mid.json` al lado) y «+ Pistas» las
  vuelve a añadir.

Pruebas: `tests/test_midi_ai.py` (vocabulario, decodificación, reparto en pistas, `.mid` de ida y
vuelta, render del motor con notas largas, release y velocidad, y el puente) y `--selftest`
(importar un `.mid` crea una pista por instrumento).

## Pendiente

- Separar una instrumental en pistas (batería, bajo…) con el modo `extract` de ACE-Step: necesita el
  modelo DiT *base* (2,4 GB más).
- Rehacer un fragmento (`repaint`) o hacer una versión de un audio (`cover`) desde Pistas.
- Un editor de piano roll libre (notas de cualquier duración) para las pistas MIDI: hoy se ven en
  Pistas y suenan, pero se cambian con un VST3 o regenerando.
- MIDI-LLM no sabe de tempo ni de compases: sus notas no caen en la rejilla del proyecto.

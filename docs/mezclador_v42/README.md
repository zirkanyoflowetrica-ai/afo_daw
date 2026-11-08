# Mezclador Automático V4.2 · Guías artísticas por stem

La V4.2 **añade criterios de mezcla, no recetas fijas**. Conserva el motor V4.1 con afinación vocal individual PSOLA, tonalidad y BPM confirmados, espacio vocal según rol, escalón L/R de 5–10 dB y cuatro masters.

## Plantillas disponibles

| Plantilla | Objetivo principal |
|---|---|
| Trap oscuro · contundente | 808 controlado, batería incisiva y texturas densas sin tapar voces |
| Trap melódico · atmosférico | Melodía emotiva, más profundidad armónica y voz clara |
| Trap latino · urbano | Dicción al frente, groove, guitarras/piano y percusión equilibrados |
| Rage / hypertrap · energético | Sintes intensos sin aspereza excesiva, kick y voz distinguibles |
| Drill · tenso y rítmico | 808 glides, snare seco y melodías oscuras |
| Rap moderno · voz dominante | Rap claro, dinámica, instrumentales abiertos |
| Boom bap · orgánico | Breaks con carácter, samples, bajo cálido y rap natural |
| Guitar trap · emo rap | Varias guitarras con roles diferentes y vocal íntima |
| Trap minimalista · espacio y silencio | Menos capas simultáneas, automatización y contraste |

## Cómo usar las guías

1. Extrae el ZIP en `E:` y ejecuta `iniciar_windows.bat`.
2. Sube los stems; abre **Guías de mezcla · Trap y rap (orientativas)**.
3. Selecciona una plantilla y pulsa **Revisar guías de mis stems**. Se actualiza la lista al cambiar archivos o plantilla.
4. Lee las recomendaciones por **cada stem**: voces, dobles, L/R, _B, coros, 808, kick, snare/clap, hats, percusión, sinte lead, arpegio, pad, piano, guitarras rítmicas/lead/acústicas, cuerdas y FX.
5. **Solo guía** (por defecto) deja intacto el audio; **Guía + balance muy sutil** aplica pequeñas compensaciones de ganancia por perfil/agrupación con límite absoluto de ±1 dB por stem, conservando todos los procesadores dinámicos y mediciones existentes. Estos sesgos no se aplican a apoyos vocales para no modificar el escalón L/R.
6. Analiza y **confirma** la tonalidad/BPM como en V4.1 antes de mezclar.
7. Al finalizar encontrarás `guia_mezcla_por_stems.md` y `.json` en **sesion_completa.zip** y entre las descargas, con el inventario real y las decisiones ejecutadas por el motor.

## Capas musicales y cautelas

- Puedes tener varios sintes, guitarras, pianos, voces, hats y claps sin que el panel colapse todas las recomendaciones en una única pista. Cada stem recibe su indicación y un contador «capa i de N» para su familia.
- **No aplica cortes de frecuencia predeterminados ni fuerces todos los elementos a un mismo LUFS.** El balance sigue siendo adaptativo y moderado.
- Los archivos cuyos nombres no identifican claramente el instrumento pueden mostrarse como `Otro` en la vista previa; el motor sigue examinando su audio en el render. La guía final usa la clasificación real de la mezcla.
- La aplicación **no crea ni detecta automáticamente la intención del arreglo**: tener tres sintes no implica poder saber cuál debe liderar; la guía recomienda comprobar su papel escuchando.
- Para obtener guías más precisas, nombra tus stems: `Synth_Lead.wav`, `Synth_Pad.wav`, `Synth_Arp.wav`, `Guitar_Rhythm_L.wav`, `Guitar_Lead.wav`, `Piano.wav`, `808.wav`, `Voz_B_L.wav`, etc.

## Criterios técnicos investigados

Las recomendaciones son una síntesis y adaptación de criterios de mezcla: manejo del enmascaramiento, jerarquía de voz contra beat, kick-808, panoramización, compatibilidad mono, profundidad vocal y capas de instrumentos. **No afirman replicar mezclas específicas de artistas.** Fuentes:

- iZotope — *8 Tips for Mixing Rap and Hip-Hop*: https://www.izotope.com/community/blog/8-tips-for-mixing-rap-and-hip-hop
- iZotope — *7 tips for mixing the low end* (2025): https://www.izotope.com/community/blog/7-tips-for-mixing-the-low-end
- Waves — *How to Mix 808s* (2026): https://www.waves.com/808-mixing-tips
- Universal Audio — *How to Use Guitar in Hip-Hop Production*: https://www.uaudio.com/blogs/ua/how-to-use-guitar-in-hip-hop-production
- Universal Audio — *Mixing in Stereo*: https://www.uaudio.com/blogs/ua/studio-basics-mixing-stereo
- FabFilter — *Learn Mixing*: https://www.fabfilter.com/learn/mixing

## Pruebas V4.2

La batería de pruebas de regresión pasó. Hay pruebas adicionales de perfiles, detección de capas y voces, límites de ganancia, exportación y **audio idéntico** entre dos perfiles al utilizar «Solo guía». Se comprobó además una exportación integral a ZIP con los cuatro masters y las guías. Las guías no son una evaluación auditiva de los stems reales; escucha A/B antes de dar por terminado un lanzamiento.

---

## Documentación anterior (V4.1 y anteriores)

# Mezclador Automático V4.1 — Análisis musical híbrido y confirmación

V4.1 — ANALISIS HIBRIDO DE TONALIDAD Y BPM / CONFIRMACION ANTES DE AFINAR

1) Integracion real (opcional) de Essentia KeyExtractor con perfiles
   krumhansl, temperley, edmm y RhythmExtractor2013 (multifeature),
   mediante Python Linux o WSL en Windows. No existe binding nativo
   oficial Python Essentia para Windows: usar instalador WSL opcional.
2) Integracion real (opcional) de Beat This! File2Beats. Usa PyTorch,
   necesita checkpoint y puede requerir una descarga la primera vez.
   No esta preinstalado ni se incluyen los pesos en el proyecto.
3) Librosa sigue disponible como respaldo incluso sin los otros modelos.
   Se comparan resultados de archivos instrumentales por separado
   (piano, guitarra, synth, bajo y bateria), nunca las voces.
4) En vez de un 100% engañoso, se muestra el acuerdo cualitativo de
   los analizadores, candidatos alternativos y el metodo consultado.
   No confundir correlacion/acuerdo con probabilidad de acierto.
5) Tres modos: Automático, Manual y Asistido. En los tres hay un botón
   «Confirmar tonalidad y BPM para esta mezcla». La afinación y el
   delay usan la eleccion confirmada. En modo Automático se analiza el
   audio aunque se priorice la referencia conocida.
6) CONFIGURACION INICIAL DE ESTA CANCION: F (Fa) + Menor natural, 91 BPM,
   modo Automático, «Priorizar referencia» activado. Si Essentia, Beat
   This o Librosa sugieren otros datos, no se cambian esos valores sin
   confirmacion expresa. Para otras canciones cambia la referencia.
7) Se comprueba identidad, tamaño y fecha de los archivos y todos los
   parametros al confirmar. Cambios posteriores invalidan la aprobacion.
8) Se conserva PSOLA por voz individual, los interruptores de principal,
   L y R, el escalon vocal, reverb/delay de V3.9, la mezcla y el mastering.
   El análisis no escribe sobre el instrumental ni modifica stems.

INSTALACIÓN (WINDOWS)
- El mismo iniciar_windows.bat sigue iniciando la mezcla básica.
- Beat This!: instalar_beat_this_opcional_windows.bat requiere conexión
  y puede consumir varios GB al descargar PyTorch/checkpoint.
- Essentia WSL: instalar_essentia_wsl_opcional_windows.bat requiere WSL
  con Ubuntu y python3-venv (instalable con sudo apt install python3-venv).
  Los dos instaladores opcionales se pueden omitir y el mezclador
  usa Librosa. El reporte indica los motores realmente utilizados.
- Los paquetes de Essentia están bajo AGPL-3.0 y Beat This! MIT. Para
  distribución comercial revisar sus licencias por separado.

RUTA DE USO
1. Cargar stems y opcionalmente beat de referencia solo para analizar.
2. Dejar modo Automático, F menor, 91 BPM, «Priorizar referencia» marcado.
3. Pulsar «Analizar tonalidad y BPM antes de mezclar».
4. Leer resultados por instrumento y «Confirmar tonalidad y BPM».
5. Elegir voces a afinar, intensidad, escalón, FX y mezclar.
6. Si cambias archivos o los valores musicales, repite la confirmación.

NO se garantizan detecciones del 95%-100% ni ausencia total de artefactos
vocales. Los detectores opcionales no se pudieron ejecutar con modelos
reales en el entorno de construcción; su código se verificó por pruebas
simuladas y deben probarse en el Windows/WSL del usuario.


---

# Mezclador Automático V4.0 — Afinación por stem y análisis de instrumentos

**Nuevo en V4.0:** el afinador PSOLA sigue procesando cada archivo vocal individualmente ANTES de mezclar. Añadí análisis del BPM y la tonalidad musical de piano, guitarra, sintetizadores, pads y bajo. El tempo toma también información de baterías. Se excluyen las voces para estimar la tonalidad.

1. Carga stems sincronizados. Si tienes el instrumental completo separado, puedes incluirlo en **«Análisis musical · BPM y tonalidad»** como referencia (no se suma a la mezcla). Para afinar varias voces, utiliza **un stem por toma vocal** (`Voz_Principal.wav`, `Voz_L.wav`, `Voz_R.wav`, etc.). Un único estéreo que ya combina varias voces no puede afinarlas de forma independiente.
2. Opcional: pulsa **«Analizar tonalidad y BPM antes de mezclar»**. La estimación mostrará confianza y archivos examinados.
3. En **Afinación vocal**, elige `Automático` para detectar tónica/escala desde instrumentos o `Manual` para elegir tónica y escala, incluidas escalas que el estimador no reconoce. Usa los interruptores de principal, L, R y apoyos como antes.
4. **Seguridad:** si la tonalidad no tiene confianza suficiente, el motor **no afina automáticamente**. No supone que la canción está en Do. Selecciona el modo Manual si sabes la escala correcta.
5. En **Espacio vocal**, activa la detección automática de BPM para sincronizar el delay. El campo de BPM manual, si es distinto de 0, tiene prioridad; si desactivas autodetección y dejas 0 usa delay libre.
6. Un BPM detectado de 70 puede equivaler musicalmente a 140; revisa el resultado especialmente en trap. El análisis no promete identificar modos, modulaciones ni todas las escalas: detecta solo mayor y menor natural. En las demás utiliza el modo Manual.
7. No cambiaron PSOLA, balance L/R de 5–10 dB, perfiles de reverb/delay, EQ, compresión ni mastering.

La dependencia nueva `librosa` se incluye en `requirements.txt`. Ejecuta `iniciar_windows.bat` desde una carpeta de E: para instalarla y abrir la app. El análisis se ejecuta localmente y **no** envía audio a la nube.

---

# Mezclador Automático V3.9 · Profundidad vocal con reverb y delay por rol

**Nuevo V3.9:** se preserva la mezcla, mastering, afinación PSOLA V3.8 y escalón de voces L/R. Se sustituye el bloque de FX vocales compartidos por **cinco envíos auxiliares separados** después de afinar y mezclar cada grupo:

| Voz | Posición de espacio | Predelay | Reverb y delay |
|---|---|---|---|
| Principal | Delante, inteligible | 62 ms | Ambiente corto y delay contenido; duck de FX hasta 3 dB |
| L/R, incluidas `_B_L`/`_B_R` | Más ancho, de fondo | 20 ms | Más ambiente, ecos laterales filtrados; después del escalón 5–10 dB |
| Apoyos `_B` al centro | Segundo plano | 25 ms | Ambiente intermedio y eco discreto |
| Dobles | Cerca de la principal, menos dominantes | 38 ms | Ambiente corto y slap/delay discreto |
| Coros | Más detrás y envolventes | 18 ms | Reverb de tamaño mayor y reflexiones con menos predelay |

**Panel «Espacio vocal»:** activar/desactivar todos los FX vocales; **profundidad 0–100** (45 por defecto, conservadora); **BPM opcional**: 0 equivale a slap/eco libre, y 55–230 activa ecos sincronizados a 1/8 y 1/4. No se detecta el BPM automáticamente: introduce el BPM real del beat para delays musicales. Los valores de reverb `room_size` son parámetros del algoritmo Pedalboard, NO segundos garantizados de decay. El delay está implementado en taps con realimentación limitada a dos repeticiones, sin feedback infinito.

Los efectos son **100 % wet sobre buses auxiliares**, tienen filtro de graves/agudos, separación predelay y ducking según actividad vocal; no se aplica reverb a la voz cruda antes de afinar. Los retornos se exportan por rol en `buses_finales/` para poder inspeccionarlos o equilibrarlos aparte. Ninguna fuente vocal seca se reescribe con la reverb/delay; nivel final de los FX se limita en relación al RMS del rol. El ducking de FX no altera el escalón L/R.

Fuentes de criterio: [Sound On Sound sobre profundidad](https://www.soundonsound.com/techniques/creating-sense-depth-your-mix), [Sound On Sound: producción vocal](https://www.soundonsound.com/techniques/vocal-production), [iZotope: reverberación en voces](https://www.izotope.com/en/learn/essential-tips-for-using-reverb-on-vocals), [iZotope: uso de delays](https://www.izotope.com/community/blog/how-to-sit-vocals-in-a-mix). Son puntos de partida técnicos, no presets universales ni resultados garantizados.

## Historial de V3.8

# Mezclador Automático V3.8 · Panel de afinación por voz

La afinación PSOLA ahora tiene **su propio panel**, separado de los controles de mezcla. En él eliges tónica, escala, intensidad (0–100 %) e **interruptores independientes**:

- **Voz principal · centro:** activado de forma predeterminada.
- **Voces L · izquierda:** desactivado de forma predeterminada. Incluye `_B_L`.
- **Voces R · derecha:** desactivado de forma predeterminada. Incluye `_B_R`.
- **Dobles/coros/_B · centro:** desactivado de forma predeterminada. No incluye los L/R.

La intensidad **0 % desactiva el afinador completo**, aun si alguna casilla está marcada. Los interruptores afectan solamente a la afinación, nunca a la limpieza, EQ, compresión, saturación, aire, paneo o escalón vocal L/R (5–10 dB). El orden sigue siendo **afinación → limpieza vocal → mezcla**; PSOLA conserva sus protecciones contra artefactos.

**Nombres recomendados:** `Voz_principal.wav`, `Voz_L.wav`, `Voz_R.wav`, `Voz_B.wav`, `Voz_B_L.wav`, `Voz_B_R.wav`. Los instrumentos con `_L`/`_R` no se afinan por esos sufijos. Se mantienen los valores de afinación anteriores de la API para compatibilidad con sesiones externas.

## Instalación y prueba

Extrae el ZIP completo en una carpeta de E: y ejecuta `iniciar_windows.bat`. En el nuevo panel elige escala/intensidad y activa las voces que quieres afinar. Comienza con principal activada y L/R desactivadas; después compara con cada canal por separado. Recarga los stems originales (no los masters ya generados).

## Historial de la versión anterior

# Mezclador Automático V3.7 · Afinación vocal con PSOLA

**Novedad:** afinación por escala mediante PSOLA (Praat), antes de cualquier procesamiento. De forma predeterminada se afina solamente la voz principal. Dobles, coros y L/R se dejan intactos a menos que marques «Afinar también dobles, coros y voces L/R». El escalón L/R de 5–10 dB y toda la mezcla V3.6 siguen presentes.

- La corrección utiliza los pulsos de la voz, no fragmentos del espectro que luego se mezclan.
- Se omiten correcciones cuando la nota es inestable, la corrección supera un semitono o hay verdadero audio estéreo no coherente; estos casos aparecen en el informe.
- Se incluyen pruebas de consonantes/silencios, tonos y cobertura de voces secundarias.
- **No hay promesa de cero artefactos**, sobre todo si la toma ya lleva reverberación, voces superpuestas o pitch processing previo.
- Si `praat-parselmouth` falta o falla, el motor deja la voz sin afinar, en vez de volver al motor anterior que producía artefactos.
- Para comparar con los WAV antiguos, es necesario cargar nuevamente **los stems originales**, porque el master antiguo ya contiene la afinación dañada.

## Cambios anteriores

# Mezclador Automático V3.6

## Nuevo: escalón automático de acompañamientos vocales L/R
- `Voz_L.wav` y `Voz_R.wav`, así como voces con los sufijos `_L`/`_R` y un nombre vocal reconocible, se tratan como **voces laterales secundarias**: paneadas a su lado original.
- `Voz_B_L.wav` y `Voz_B_R.wav` conservan su paneo al **50 %** y pasan al mismo grupo de voces laterales.
- `Voz_B.wav` continúa al centro con su propio balance moderado.
- El grupo L/R completo se coloca por defecto **7 dB bajo la voz principal** (ajustable de 5 a 10 dB desde la interfaz), con EQ de separación suave y ducking de hasta 1 dB durante las frases principales.
- La reducción de nivel se aplica **después de afinar, limpiar, ecualizar, comprimir y dar saturación/aire** a las tomas; los FX vocales se generan después del escalón. No afecta al paneo de guitarras, percusiones u otros instrumentos.
- Si una voz secundaria llega demasiado baja, se permiten como máximo +2 dB de recuperación para no amplificar ruido de fondo; no se garantiza que un archivo casi inaudible alcance el objetivo.
- **Nota:** los stems `pistas_procesadas_pre_bus` son pre-bus y no reflejan este balance final. El audio de mezcla y los buses finales sí reflejan el escalón.
- Los WAV de la canción ya mezclados no permiten reajustar individualmente L/R: para aplicar estos cambios hay que volver a cargar los archivos vocales separados.


Actualización de V3.4 que reduce artefactos de afinación, manteniendo la mezcla anterior y su afinación por escala y edición conservadora por pista, revisión A/B y un master adicional para plataformas. Se conserva la estructura de mezcla, los perfiles de instrumentos, referencia, separación de batería y clasificación opcional. No necesita modelos nuevos para estas mejoras.


## Nuevo en V3.4: error de disco y afinación por escala

El error observado ocurrió con C: lleno: los WAV y el ZIP ya estaban guardados en E:, pero la preparación de descargas usaba temporales en C:. Ahora Gradio, los temporales del proceso y pip usan carpetas locales al proyecto. El iniciador registra la consola y el motor guarda excepciones en `logs/errores.log`. Se comprueba espacio estimado antes de procesar. Los resultados individuales se conservan dentro del ZIP y en `salida/`; la lista de descargas muestra solo los principales, evitando copiar todos los stems al cache de una vez. El ZIP usa compresión ligera. El medidor y limitador 4x ahora trabajan por bloques para evitar arrays gigantes.

### Afinación vocal

- **Tónica:** C=Do, C#=Do#, D=Re, D#=Re#, E=Mi, F=Fa, F#=Fa#, G=Sol, G#=Sol#, A=La, A#=La#, B=Si. Los bemoles equivalentes se eligen con su sostenido equivalente (por ejemplo, Bb = A#).
- **Escala:** cromática, mayor, menor natural, menor armónica y pentatónicas mayor/menor.
- **Intensidad 0–100:** 0 desactiva; valores intermedios acercan parcialmente a las notas; 95–100 buscan una corrección completa en notas fiables con transiciones suavizadas. El 100 busca corregir completamente el desvío estimado en tramas fiables, con límite de dos semitonos por trama y cambios suavizados para reducir artefactos. No es el plugin comercial Auto-Tune ni garantiza afinación perfecta si la detección falla.

El afinador sigue la melodía, no solo una nota global. Usa YIN entre 65–900 Hz y Rubber Band a través de Pedalboard, con preservación de formantes. Conserva duración e inicio de la pista, deja pasar regiones no tonales y alinea los solapes con ajustes locales de hasta 8 ms para evitar cancelaciones. Está diseñado para voces monofónicas aisladas; coros polifónicos, voz muy ronca, ruido, reverberación impresa o una escala incorrecta pueden producir errores. La escala no se adivina: debes elegirla. Empieza con 35–60 si buscas naturalidad; usa 100 si buscas un efecto evidente. La intensidad inicial es 0 para mantener el comportamiento sin afinar hasta que la ajustes.

### Aire, recortes y densidad

Se conserva un solo filtro de graves vocal adaptativo, el de-esser y la EQ dinámica. Se agrega una estantería de aire a 10 kHz de hasta **+1.4 dB** en principal y **+0.8 dB** en apoyos. Se omite si ya hay brillo, no hay contenido alto útil o el nivel persistente sugiere ruido. Solo se recortan agudos vocales a 18.5 kHz cuando se detecta un exceso claro de energía extrema; en master, el filtro a 20 kHz también es condicional.

La saturación vocal va en paralelo al 8 % (4.5 % en apoyos), con sobremuestreo 2x y compensación moderada. La compresión paralela suma hasta 10 % en principal, 6 % en apoyos e instrumentales; se omite si el material ya está denso. En master ambas aportan solo **2.5 %**, antes de la limitación. Un control final de eses de hasta 1 dB protege el brillo añadido. Los porcentajes son proporciones de mezcla seca/procesada, no un aumento equivalente de volumen. Son ajustes moderados y condicionados, no una garantía de estilo o calidad comercial.

Las fuentes consultadas incluyen la API oficial de Pedalboard (curva de tono y preservación de formantes), los ejemplos de compresión paralela de iZotope y su documentación de saturación/sibilancia. No se agregaron paquetes nuevos.

## Inicio

1. Instala Python 3.12 de 64 bits y extrae la carpeta completa.
2. Abre `iniciar_windows.bat`; instala dependencias la primera vez.
3. Carga hasta 30 stems sincronizados desde el mismo punto. La referencia es opcional.
4. Pulsa **Mezclar y preparar masters**. La afinación se elige con tónica, escala e intensidad.
5. Escucha la mezcla y **Plataformas**. En **Revisar cada pista**, selecciona una toma para escuchar original/procesada al mismo volumen.
6. Descarga `sesion_completa.zip`, o cualquiera de los archivos por separado.

Si la versión anterior sigue abierta, ciérrala y vuelve a ejecutar el iniciador para cargar el código nuevo. Las mezclas anteriores de `salida/` se conservan.

Instalación manual: `python -m pip install -r requirements.txt` y `python app.py`. Las versiones directas usadas en pruebas están en `requirements-tested.txt`; las dependencias transitivas no están bloqueadas. La instalación inicial y los modelos opcionales requieren internet. La mezcla básica funciona localmente.

## Mejoras de V3.3

- **Análisis largo corregido:** hasta ocho fragmentos repartidos, conservando la frecuencia de muestreo original. Los agudos ya no se pliegan a otras frecuencias por saltar muestras. La energía estéreo se analiza por canales para evitar que la oposición L/R se confunda con ausencia de sonido.
- **Un solo filtro de graves vocal:** 55–110 Hz según el rango fiable, o 75/90 Hz de respaldo. Se eliminan los filtros vocales duplicados y los recortes estáticos de cuerpo/presencia que ya cubre la EQ dinámica.
- **Nivelación por frases:** hasta −3/+1.5 dB antes del compresor, con curva suave y protección de silencios. No normaliza cada sílaba ni sustituye decisiones artísticas.
- **Limpieza prudente:** repara impulsos aislados de una muestra solo bajo criterios estrictos; atenúa golpes graves breves hasta 3 dB. Advierte muestras cercanas al techo e intervalos de aire/respiración candidatos. Estos últimos no se eliminan porque pueden ser consonantes. No incluye un restaurador neuronal, de-clipping o eliminación general de ruido.
- **Resonancias:** un recorte adicional como máximo, hasta 1.2 dB y Q=3, cuando sobresale una banda estrecha entre 500 Hz y 6.5 kHz. Se omite en contenido demasiado tonal y en kick/bajo/platillos. Es una heurística, no identifica con certeza resonancias indeseadas.
- **Balance contextual:** variación vocal lenta hasta ±0.8 dB según la densidad instrumental; solo con principal identificada. No detecta automáticamente nombres de secciones ni cambia paneo.
- **Kick/bajo:** ducking de hasta 2 dB solo en los graves coincidentes; banda y relajación se adaptan al contenido y anchura del golpe. Conserva mejor las armónicas del bajo.
- **Antes de V3.9:** reverb corta para principal y eco filtrado; varios grupos compartían una ruta de FX. **Ahora V3.9:** cinco retornos de reverb/delay independientes, con BPM opcional.
- **Master con presupuesto de limitación:** enlace estéreo, sobremuestreo 4×, anticipación aproximada de 3 ms y relajación de 100 ms. Informa reducción máxima, P95 y actividad; no incrementa indefinidamente el drive para perseguir LUFS. Se conserva la EQ/compresión previa del motor.
- **Entrega revisable:** pistas secas procesadas, buses finales, A/B igualado en LUFS, informe y manifiesto de sesión JSON; un ZIP reúne todos los resultados.

## Master para plataformas

`master_plataformas.wav` es un WAV PCM de 24 bits / 44.1 kHz con objetivo **−14 LUFS** y techo conservador **−2 dBTP estimado**, hasta 3 dB de reducción del limitador. Si la dinámica impide llegar al objetivo dentro del presupuesto, queda más bajo y lo informa.

No es una certificación para todos los servicios ni garantiza que suene igual en todos los reproductores. Cada plataforma puede normalizar de forma distinta. La guía oficial de Spotify recomienda −14 LUFS, menos de −1 dBTP y menos de −2 dBTP para masters más fuertes; aquí se elige −2 dBTP incluso para el objetivo −14 como margen adicional.

Se conservan tres versiones alternativas: Dinámico (−14, techo −1, presupuesto 4 dB), Comercial (−11, techo −1, presupuesto 6 dB) y Fuerte (−8.5, techo −1, presupuesto 8 dB). Los nombres expresan objetivos orientativos, no resultados garantizados. El master de referencia sigue siendo opcional y su objetivo se limita a −16/−9 LUFS. La nueva limitación puede producir niveles distintos de V3.2, especialmente con transitorios fuertes.

El informe añade crest factor, correlación estéreo y variación RMS P10–P90 entre ventanas de tres segundos. Esta variación **no es LRA ni sonoridad de corto plazo certificada**. Los picos se estiman por sobremuestreo, sin simulación de codificación AAC/Ogg ni certificación de un medidor externo.

## Paneo y voces de apoyo

| Etiqueta | Posición del sonido directo |
|---|---|
| `_B` / `_B_02` | Centro |
| `_B_L` | 50 % izquierda |
| `_B_R` | 50 % derecha |
| Otros `_L` / `_R` al final | Extremo correspondiente; si es voz, se coloca en grupo lateral secundario |
| Sin sufijo | Mono al centro; estéreo conserva canales |

`_B` es un token exacto; `_BASS` y `_Brillo` no cuentan. El paneo 50 % usa potencia constante (0.924/0.383 o su inversa). Las voces `_B` se convierten a mono antes de panear. El apoyo central `_B` se controla a 6 LU de distancia respecto de la principal, y las voces laterales en conjunto a 7 LU por defecto (control de 5–10). Hay ducking adicional de hasta 1 dB durante la voz principal. Sin principal, referencia orientativa −26 LUFS. Esto se mide antes de integrar FX y compresión compartida; los efectos pueden abrir el estéreo. Nombra la principal `Voz_Principal.wav` para evitar ambigüedad.

## Qué contiene una sesión

- `mezcla_sin_master.wav`: mezcla estéreo PCM 24 bits.
- `master_*.wav`: cuatro masters y uno de referencia si corresponde, PCM 24 bits.
- `pistas_procesadas_pre_bus/`: cada archivo de entrada tras sus ajustes individuales, ganancia y paneo, **sin** balance/EQ de buses, ducking compartido ni FX. FLOAT 32 bits conserva margen sin recortar muestras que superen 0 dBFS. En batería combinada se entrega el kit procesado y sus piezas derivadas aparte.
- `buses_finales/`: familias y retornos FX con los ajustes compartidos y la curva de referencia. FLOAT 32 bits; todos comienzan alineados y su suma reconstruye la mezcla sin master dentro de la precisión numérica. Para reconstruir, importa todos a ganancia unidad, sin paneo, plugins ni normalización adicional.
- `comparacion/`: copias A/B al mismo LUFS y con margen común. Se usan solo para escuchar; no reemplazan las pistas de producción. También se incluye referencia/master al mismo volumen si hay referencia.
- `drums_separados_aproximados/`: piezas DSP/neuronal opcional. La separación DSP no garantiza aislamiento; usa stems reales individuales si los tienes.
- `informe.txt`, `sesion.json`, `sesion_completa.zip`.

La exportación individual anterior a buses permite continuar editando en un DAW, pero esas pistas no suman exactamente la mezcla final. Usa los buses si quieres reconstrucción. La interfaz permite escuchar cada pista y comparar sus ajustes automáticos; no es un editor manual por notas, regiones o automatizaciones.

## Afinación y funciones opcionales

La afinación inicial es 0; consulta la sección V3.4 para elegir escala e intensidad. El modo global prudente antiguo se conserva solo como compatibilidad interna.

De-esser vocal (hasta 4 dB), EQ dinámica de cuerpo/dureza y espacio vocal en instrumentos, detección de fase y referencia tonal se conservan. Las alertas de fase no alinean ni invierten automáticamente pistas. La comparación entre stems solo revisa sus primeros 30 segundos y puede tener falsos positivos.

CLAP y DrumSep experimental conservan los instaladores originales y son independientes de las funciones nuevas. No se validaron sus pesos en esta actualización; si no están disponibles, siguen funcionando las heurísticas y la separación DSP. Se mantienen las notas del instalador experimental sobre términos de los pesos de terceros.

## Pruebas

```text
python tests/test_pipeline.py
python tests/test_backing_vocals.py
python tests/test_v36.py
python tests/test_v32.py
python tests/test_v33.py
python tests/test_v34.py
python tests/test_v35.py
```

Consulta `PRUEBAS.md` y `tests/RESULTADOS.txt`. Las pruebas sintéticas verifican seguridad de muestras, frecuencia, paneo, nivelación, afinación prudente, limitación, reconstrucción de buses, comparación A/B y exportación. No sustituyen escucha con grabaciones reales ni demuestran calidad artística profesional. Proyectos largos con muchos stems pueden consumir bastante RAM y espacio; A/B y buses añaden copias de audio.

## Fuentes técnicas consultadas

- Spotify: https://support.spotify.com/us/artists/article/loudness-normalization/
- SciPy y filtrado/remuestreo: https://docs.scipy.org/doc/scipy/reference/signal.html
- Pedalboard: https://spotify.github.io/pedalboard/reference/pedalboard.html
- Nivelación/edición vocal: https://www.izotope.com/community/blog/vocal-editing-101

Los módulos nuevos son `spectral_tools.py`, `track_tools.py` y `mastering_tools.py`. No se agregan dependencias base.

Fuentes adicionales:
- https://spotify.github.io/pedalboard/reference/pedalboard.html#pedalboard.time_stretch
- https://www.izotope.com/community/blog/how-to-sit-vocals-in-a-mix
- https://help.izotope.com/docs/izotope-nectar2-help.pdf


# ALLFORONE — MASTER DEVELOPMENT PROMPT
## DAW modular profesional | Python + C++ | Interfaz HTML original | VST3 | Mezcla automática | IA | Compilación Windows

# 0. INSTRUCCIÓN SUPREMA

Eres el arquitecto principal y desarrollador de AllForOne, una estación de trabajo de audio digital profesional, gratuita, modular y extensible.

Debes construir una aplicación real y funcional para Windows 11, utilizando Python como lenguaje principal de aplicación, C++ como motor de audio y la plantilla HTML proporcionada como interfaz gráfica obligatoria.

**ESTA ES LA REGLA MÁS IMPORTANTE DE TODO EL PROYECTO:**

La interfaz debe conservar fielmente el aspecto, la composición, los colores, los controles y el comportamiento de `PLANTILLA_DAW.html`.

No interpretes la plantilla como una inspiración.

No diseñes algo parecido.

No sustituyas su estética por otra.

**UTILIZA LA PLANTILLA ORIGINAL COMO BASE REAL DE LA INTERFAZ.**

El segundo archivo, `Mezclador_Automatico.zip`, es la base funcional para el procesamiento inteligente, las voces, el afinador, el análisis musical, las plantillas de mezcla y el mastering.

Debes unir ambos proyectos sin desechar el trabajo existente.

El resultado tiene que ser un DAW de escritorio compilado, con interfaz modular y motor de audio nativo.

---

# 1. ARCHIVOS PRINCIPALES Y PRIORIDADES

Tienes tres fuentes de trabajo:

## A. PLANTILLA_DAW.html

Es la fuente de verdad visual.

Contiene una interfaz de estudio musical modular con:

- Lienzo infinito.
- Cuadrícula de fondo.
- Paneles independientes.
- Paneles arrastrables.
- Paneles redimensionables.
- Zoom del lienzo.
- Conectores circulares.
- Cables curvos.
- Puntos de curvatura desplazables.
- Colores diferentes por módulo.
- Cabeceras negras.
- Bordes gruesos.
- Botones geométricos.
- Mezclador con faders.
- Piano roll.
- Instrumentos.
- Secuenciador de batería.
- Grabador.
- Generación IA.
- Editor de pistas.
- Master con medidor VU.
- Visibilidad individual de módulos.
- Restauración de posiciones.

Debes analizar su HTML, CSS y JavaScript completo.

Conserva los identificadores, componentes y funciones que sean útiles.

No transformes los elementos existentes en controles Qt genéricos.

## B. Mezclador_Automatico.zip

Contiene el mezclador automático V4.2.

Incluye, entre otros:

- `app.py`
- `mixer_engine.py`
- `scale_tuner.py`
- `vocal_dsp.py`
- `vocal_space.py`
- `track_tools.py`
- `sonic_tools.py`
- `spectral_tools.py`
- `mastering_tools.py`
- `music_analysis.py`
- `music_confirmation.py`
- `mix_templates.py`
- `ai_classifier.py`
- `audio_intelligence.py`
- `drum_split.py`
- `neural_drums.py`
- Tests y documentación.

Debes inspeccionar el contenido y conservar su lógica útil.

No recrees estos algoritmos sin comprobar primero lo que ya tenemos.

## C. Proyecto existente AllForOne

Ruta inicial de búsqueda:

`E:\AFO`

Verifica la ruta.

Inspecciona `AGENTS.md`, `CMakeLists.txt`, el código C++ existente, los submódulos, las dependencias y el estado de compilación.

Conserva la estructura y el trabajo ya realizado.

Si los archivos adjuntos están fuera del proyecto, ubícalos en el área de trabajo sin sobrescribir originales.

### Orden de prioridades

1. Fidelidad visual con la plantilla.
2. Conservación del código existente.
3. Funcionamiento real.
4. Estabilidad y compilación.
5. Integración modular.
6. Rendimiento.
7. Ampliación de funciones.

Las seis últimas prioridades no autorizan a ignorar la primera.

---

# 2. ARQUITECTURA TECNOLÓGICA OBLIGATORIA

El DAW debe utilizar la siguiente arquitectura.

## CAPA 1 — INTERFAZ ORIGINAL

Tecnologías:

- HTML5.
- CSS3.
- JavaScript.
- PySide6.
- Qt WebEngine.

La interfaz HTML original debe visualizarse dentro de la aplicación de escritorio.

Utiliza `QWebEngineView` como superficie principal de la interfaz y carga la plantilla adaptada desde los recursos locales.

No dependas de un servidor web externo para abrirla.

No es necesario que el usuario tenga instalado Chrome.

El programa incluirá los componentes de Qt WebEngine requeridos durante la distribución.

La interfaz debe poder trabajar sin conexión a Internet.

Empaqueta fuentes y recursos locales cuando corresponda.

## CAPA 2 — PUENTE JAVASCRIPT/PYTHON

Utiliza Qt WebChannel mediante `QWebChannel`.

Crea un puente de comunicación entre la interfaz y Python.

El puente debe permitir:

- Crear pistas.
- Importar archivos.
- Solicitar formas de onda.
- Reproducir.
- Grabar.
- Modificar faders.
- Cambiar paneo.
- Abrir plugins.
- Gestionar racks.
- Ejecutar análisis.
- Aplicar mezcla automática.
- Aplicar afinación.
- Guardar proyectos.
- Cargar proyectos.
- Exportar audio.
- Consultar estados y errores.

JavaScript administra la representación visual.

Python administra la lógica de aplicación y coordina las operaciones.

No hagas pasar bloques de audio de alta frecuencia continuamente por QWebChannel.

Utiliza mensajes de estado, comandos, eventos y datos visuales compactos.

Para formas de onda grandes, usa cachés, archivos preparados o mecanismos eficientes de transferencia.

## CAPA 3 — PYTHON

Tecnologías:

- Python 3 estable y compatible.
- PySide6.
- NumPy.
- SoundFile.
- Bibliotecas existentes del mezclador V4.2.
- Otras dependencias justificadas.

Python se encargará de:

- Administración de proyectos.
- Organización de tracks.
- Control de módulos.
- Análisis musical.
- Mezcla automática.
- Afinación offline.
- Herramientas de IA.
- Automatización de procesos.
- Gestión de archivos.
- Preferencias.
- Presets.
- Comunicación con C++.

## CAPA 4 — MOTOR C++ NATIVO

Tecnologías:

- C++20.
- JUCE.
- Tracktion Engine.
- CMake.
- MSVC.
- pybind11.

Responsabilidades:

- Audio en tiempo real.
- Reproducción.
- Grabación.
- Dispositivos de audio.
- MIDI.
- Hosting VST3.
- Buses.
- Routing.
- Plugins.
- Procesamiento multicanal.
- Compensación de latencia.
- Renderización.
- Sincronización.

No ejecutes Python dentro del callback crítico de audio.

## CAPA 5 — EXTENSIÓN NATIVA

Crear un módulo compilado:

`afo_audio.pyd`

Este módulo conectará Python con las clases y operaciones nativas necesarias.

Utiliza pybind11 y una API estable que permita ampliar las funciones sin modificar continuamente la interfaz.

---

# 3. COMPILACIÓN — REQUISITO FUNDAMENTAL

AllForOne NO debe necesitar abrir un archivo `.py` o `.html` manualmente para utilizarse.

El resultado final debe ser una aplicación de escritorio de Windows.

## OBJETIVO

Generar:

`AllForOne.exe`

Con todos los componentes necesarios.

La distribución será de Windows 11 x64 inicialmente.

## SISTEMA DE CONSTRUCCIÓN

### Primera fase: compilar el motor

Utilizar CMake y MSVC para:

1. Configurar JUCE.
2. Configurar Tracktion Engine.
3. Compilar la infraestructura nativa.
4. Compilar las clases adaptadoras.
5. Compilar las bindings de pybind11.
6. Obtener `afo_audio.pyd`.
7. Ejecutar pruebas nativas.

### Segunda fase: conectar Python

Preparar un entorno Python compatible.

Instalar dependencias automáticamente.

Verificar que Python puede importar `afo_audio`.

Comprobar comunicación real.

### Tercera fase: integrar la interfaz

Cargar `PLANTILLA_DAW.html` mediante Qt WebEngine.

Inicializar QWebChannel.

Conectar eventos JavaScript con Python.

Verificar controles reales.

### Cuarta fase: empaquetar

Evaluar Nuitka con PySide6 y Qt WebEngine.

Crear preferentemente una distribución standalone en carpeta durante el desarrollo.

Incluir:

- Ejecutable.
- Módulo C++ compilado.
- DLL necesarias.
- Componentes Qt.
- Recursos Qt WebEngine.
- Plantilla HTML.
- JavaScript.
- CSS.
- Fuentes locales.
- Recursos gráficos.
- Plantillas de proyecto.
- Archivos de configuración.

No asumir que un ejecutable único tendrá mejor compatibilidad.

Primero conseguir una aplicación standalone estable.

Después evaluar un instalador convencional.

### Quinta fase: verificación independiente

La aplicación empaquetada debe abrirse desde la carpeta de distribución sin depender de rutas absolutas del entorno de desarrollo.

Comprobar también su funcionamiento en un entorno Windows limpio compatible, mediante prueba real o máquina virtual.

No afirmar portabilidad si solamente funciona dentro del entorno Python original.

---

# 4. INSTALACIÓN AUTOMÁTICA DE DEPENDENCIAS

Crear un lanzador:

`build_and_run.bat`

Y un sistema de configuración reproducible.

Debe detectar:

- Python.
- Git.
- MSVC.
- Visual Studio Build Tools.
- Windows SDK.
- CMake.
- Ninja.
- JUCE.
- Tracktion Engine.
- pybind11.
- PySide6.
- Qt WebEngine.
- Dependencias de audio.

Si una dependencia no existe, obtenerla desde su fuente oficial cuando su instalación esté permitida.

Utiliza versiones fijadas y compatibles.

No utilices referencias Git inventadas.

No borres instalaciones previas funcionales.

No modifiques PATH global si puedes trabajar con rutas locales.

No descargues dependencias repetidamente si ya existen y son válidas.

Si una instalación requiere privilegios de administrador, informa de ello y solicita la autorización necesaria.

## Funcionamiento del lanzador

El usuario ejecuta:

`build_and_run.bat`

El script:

1. Verifica el entorno.
2. Detecta dependencias.
3. Configura Python.
4. Configura CMake.
5. Compila C++.
6. Verifica `afo_audio.pyd`.
7. Ejecuta pruebas rápidas.
8. Inicia AllForOne.
9. Registra errores.

Al terminar debe quedar una aplicación funcional.

Crear también:

`package_windows.bat`

Para generar la distribución final.

---

# 5. FIDELIDAD VISUAL ABSOLUTA

La plantilla tiene una identidad neo-brutalista concreta.

Debe conservarse.

## COLORES ORIGINALES

Mantener las variables existentes y los colores originales de los módulos.

Entre ellos:

- Fondo crema `#fff1c9`.
- Amarillo de pistas `#ffc233`.
- Violeta de piano `#b79bff`.
- Verde de mezcla `#5ee0b0`.
- Coral de instrumentos `#ff7a70`.
- Azul de IA `#6ab8ff`.
- Rosa de master `#ff9ee0`.
- Verde lima de batería `#d4f26a`.
- Gris de grabación `#c9ccd2`.

No sustituirlos por azul neón, degradados futuristas o glassmorphism.

## ELEMENTOS A CONSERVAR

- Fondo de puntos.
- Bordes negros de 3 píxeles donde corresponda.
- Sombras sólidas.
- Tipografía Space Grotesk.
- Cabeceras negras.
- Colores por módulo.
- Botones rectangulares.
- Perillas circulares.
- Medidores analógicos.
- Faders.
- Cables curvos.
- Puertos redondos.
- Tiradores de redimensionado.
- Posicionamiento libre.

Se permite ajustar pequeños detalles de legibilidad o accesibilidad cuando sea necesario.

No se permite reinterpretar la composición general.

## REGLA DE MODIFICACIÓN

Antes de cambiar el CSS, explica qué problema estás solucionando.

Evita reemplazar hojas de estilo completas.

Prefiere cambios mínimos y localizados.

Mantén el CSS original como referencia verificable.

---

# 6. LIENZO MODULAR INFINITO

El centro de AllForOne debe seguir siendo el lienzo modular de la plantilla.

No sustituyas este sistema por pestañas convencionales.

No conviertas todos los módulos en una cuadrícula fija.

No reemplaces el lienzo por una colección de ventanas Qt tradicionales.

## MOVIMIENTO

Cada módulo debe poder:

- Arrastrarse.
- Reposicionarse.
- Redimensionarse horizontalmente.
- Redimensionarse verticalmente.
- Minimizarse u ocultarse.
- Restaurarse.
- Enfocarse.
- Maximizarse.
- Entrar en pantalla completa.
- Recuperar su tamaño anterior.

El módulo maximizado debe mantener su funcionalidad.

## ZOOM

Implementar tres zooms independientes.

### Zoom del lienzo

Afecta la vista general del estudio.

Debe poder:

- Acercar.
- Alejar.
- Ajustar todos los módulos.
- Enfocar módulo.
- Restaurar vista.

### Zoom horizontal de pistas

Afecta únicamente la escala temporal.

Sirve para ver más o menos segundos, compases y clips.

### Zoom vertical de pistas

Afecta únicamente la altura de las pistas.

Permite visualizar muchas pistas a la vez sin que crezcan desproporcionadamente.

Debe existir una vista compacta.

## PANTALLA COMPLETA

Cada módulo tendrá una opción para expandirse a toda el área de trabajo.

Opcionalmente, permitir pantalla completa real del monitor.

La aplicación debe restaurar correctamente el módulo al salir.

## PERSISTENCIA

Guardar posiciones, tamaños y visibilidad.

Guardar también:

- Zoom.
- Desplazamiento del lienzo.
- Puntos de los cables.
- Distribución por espacio de trabajo.

El archivo de proyecto debe poder guardar su propia distribución.

La configuración general puede conservar una distribución predeterminada independiente.

---

# 7. CABLES MODULARES REALES

La plantilla ya dispone de conectores circulares, cables de Bézier y puntos de curvatura.

Conserva esos mecanismos visuales.

Pero ahora los cables deben representar conexiones reales.

## TIPOS DE SEÑAL

- Audio.
- MIDI.
- Control.
- Sidechain.
- Envíos a buses.

Diferenciar los tipos cuando sea necesario sin alterar el lenguaje visual.

## COMPORTAMIENTO

Permitir arrastrar conectores.

Permitir cambiar la posición del conector sobre el perímetro de un módulo.

Permitir ajustar la curva de los cables.

Distinguir claramente entre:

1. Mover un puerto visual.
2. Crear una conexión de audio.
3. Modificar una conexión.
4. Desconectar una conexión.

La conexión real debe sincronizarse con el motor de audio.

Rechazar conexiones incompatibles y ciclos inválidos.

La interfaz no debe mostrar un cable operativo si el motor no tiene esa conexión.

## CONEXIONES AUTOMÁTICAS

Al crear una pista, debe quedar conectada automáticamente a su canal del mezclador.

El mezclador debe conectarse al master por defecto.

Las pistas no requieren que el usuario conecte cables manualmente para escucharlas.

Los cables permiten modificar rutas o visualizar el flujo.

**Ocultar un módulo visual no debe silenciarlo ni desconectarlo automáticamente.**

Silenciar, apagar, desconectar y ocultar son operaciones diferentes.

---

# 8. CATÁLOGO COMPLETO DE MÓDULOS

Mantener todos los módulos originales y agregar los necesarios para el mezclador automático.

Los módulos deben compartir la misma estructura visual de la plantilla.

## MÓDULO 01 — PISTAS DE PRODUCCIÓN

Editor multipista dedicado a:

- Instrumentales.
- Batería.
- Bajo.
- Sintetizadores.
- Guitarras.
- Piano.
- Stems.
- MIDI.
- Audio generado por IA.

Todos los resultados instrumentales deben integrarse en este editor.

No crear un panel de timeline independiente por cada instrumento.

## MÓDULO 02 — PISTAS VOCALES

Editor multipista para:

- Voz principal.
- Dobles.
- Laterales.
- Armonías.
- Adlibs.
- Tomas.
- Grabación.
- Comping progresivo.

Roles editables:

`P / B / L / R / B_L / B_R`

Las pistas pueden tener roles distintos sin perder su identidad individual.

Los dos editores deben compartir el mismo proyecto, transporte y motor.

## MÓDULO 03 — MEZCLADOR

Conservar el aspecto de la consola de la plantilla.

Agregar funcionamiento real:

- Faders.
- Paneo.
- Mute.
- Solo.
- Buses.
- Sends.
- Routing.
- Inserciones.
- Indicadores de nivel reales.
- Compensación de latencia.

Los valores de los faders deben modificar la ganancia real del motor.

No utilizar medidores con valores aleatorios.

## MÓDULO 04 — MEZCLADOR AUTOMÁTICO

Este panel utilizará el código original de `Mezclador_Automatico.zip`.

Debe incluir:

- Importación y análisis de stems.
- Detección de tipos de pistas.
- Clasificación de instrumentos.
- Revisión manual de clasificación.
- Análisis espectral.
- Análisis de dinámica.
- Balance automático.
- Tratamiento vocal.
- Control de dobles.
- Manejo de laterales.
- Control de bajos.
- Kick/bass ducking cuando corresponda.
- EQ correctiva.
- Compresión.
- Saturación.
- Procesamiento estéreo.
- Comparación con referencia.
- Generación de reportes.
- Aplicación de mezcla.

Incluir el botón:

**MEZCLAR AUTOMÁTICAMENTE**

Y también:

**REMEZCLAR**

La segunda opción debe permitir ejecutar nuevos ajustes sin perder el estado anterior.

La mezcla automática debe producir audio real.

Sus operaciones más pesadas pueden ejecutarse offline.

No bloquear el hilo de audio en tiempo real.

## MÓDULO 05 — AFINADOR

Utiliza `scale_tuner.py` y las funciones pertinentes del mezclador.

Crear un módulo independiente con:

- Selección de pista.
- Selección de voces.
- Tonalidad.
- Escala.
- Detección de notas.
- Cantidad de corrección.
- Control de intensidad de 0 a 100 %.
- Afinación natural.
- Afinación intensa.
- Activar/desactivar por voz.
- Vista antes/después.
- Comparación de pitch original y corregido.

La intensidad 0 debe representar ausencia de corrección.

La intensidad 100 debe representar la máxima intensidad disponible, sin prometer resultados perfectos.

Permitir corrección individual por stem.

No mezclar señales de distintas voces antes de analizarlas.

Preservar la alineación temporal y analizar artefactos.

## MÓDULO 06 — ANÁLISIS MUSICAL

Reutilizar `music_analysis.py` y `music_confirmation.py`.

Funciones:

- Detectar BPM.
- Estimar tonalidad.
- Elegir escala.
- Analizar instrumentos.
- Mostrar confianza.
- Distinguir resultados por fuente.
- Permitir corrección manual.
- Confirmar resultados antes de afinar.

Ofrecer:

- Automático.
- Manual.
- Asistido.

No inventar confianza ni resultados.

## MÓDULO 07 — RACK DE EFECTOS

Cada pista debe disponer de su propia cadena.

Crear un inspector real.

Mostrar:

- Plugin.
- Tipo.
- Orden.
- Estado.
- Bypass.
- Parámetros.
- Automatizaciones.
- Latencia.
- Preset.
- Entrada y salida.

Permitir:

- Arrastrar efectos.
- Reordenar.
- Copiar.
- Guardar.
- Eliminar.
- Abrir editor VST3.

Los cambios deben reflejarse en el motor.

## MÓDULO 08 — ANTES Y DESPUÉS

Crear un analizador independiente.

Mostrar:

- Forma de onda original.
- Forma de onda procesada.
- Espectro antes.
- Espectro después.
- RMS.
- Picos.
- LUFS.
- Balance estéreo.
- Diferencias.
- Comparación A/B.
- Igualación de sonoridad cuando sea apropiado.

Permitir comparar:

- Un efecto individual.
- Una cadena completa.
- Una pista.
- Una mezcla.
- El master.

Las mediciones deben proceder del audio real.

## MÓDULO 09 — MASTERING

Integrar el procesamiento existente de `mastering_tools.py` y `mixer_engine.py`.

Conservar el medidor VU de la plantilla.

Agregar:

- Medición LUFS.
- True peak.
- Limitador.
- Saturación.
- EQ.
- Balance.
- Referencias A/B.
- Presets.
- Exportación.

Distinguir claramente visualización VU y mediciones de sonoridad.

Crear exportaciones WAV y formatos adicionales compatibles.

Conservar los formatos y presets del mezclador original cuando sea apropiado.

## MÓDULO 10 — INSTRUMENTOS VST3

Mantener el diseño del banco de instrumentos de la plantilla.

Sustituir su generación de ejemplo por hosting real cuando el motor esté preparado.

Permitir:

- Detectar instrumentos.
- Abrir editor original.
- Seleccionar presets.
- Enviar MIDI.
- Recibir audio.
- Grabar salida.
- Enrutar al mezclador.

No fingir que una lista de sintetizadores de ejemplo es un banco real de VST.

## MÓDULO 11 — PIANO ROLL

Conservar su apariencia.

Implementar MIDI real:

- Notas.
- Duración.
- Velocidad.
- Octavas.
- Cuantización.
- Edición.
- Reproducción.
- Comunicación con VST3.

## MÓDULO 12 — BATERÍA

Conservar el secuenciador de 16 pasos de la plantilla.

Integrar:

- Sampler.
- Samples por pad.
- Secuencias.
- Velocity.
- Swing.
- Salidas.
- MIDI.
- Routing al mezclador.

## MÓDULO 13 — GRABADOR

Conservar la identidad visual del grabador de cintas.

Utilizar el motor de grabación nativo.

Permitir:

- Seleccionar entrada.
- Armar pista.
- Grabar.
- Detener.
- Escuchar.
- Monitorizar.
- Guardar tomas.
- Ver formas de onda reales.

## MÓDULO 14 — GENERACIÓN IA

Conservar el módulo azul de IA.

Permitir integrar progresivamente:

- Generación de instrumentales.
- Creación de stems.
- Separación de pistas.
- Análisis.
- Generación MIDI.
- Procesamiento de audio.

Cada resultado debe importarse automáticamente al editor multipista correspondiente.

Los modelos no disponibles deben figurar como no instalados.

No simular generación con clips aleatorios sin identificarlo como demostración.

## MÓDULO 15 — REFERENCIAS

Permitir importar una canción de referencia.

Funciones:

- Comparación espectral.
- Balance tonal.
- Sonoridad.
- Dinámica.
- Comparación A/B.
- Separación opcional de stems.

## MÓDULO 16 — ADMINISTRADOR DE PROYECTOS

Permitir:

- Nuevo proyecto.
- Abrir.
- Guardar.
- Guardar como.
- Plantillas.
- Historial.
- Recuperación.
- Gestión de medios.
- Archivos faltantes.

---

# 9. INTEGRACIÓN TOTAL DEL MEZCLADOR V4.2

El mezclador original no debe convertirse en un sistema aislado que requiera abrir otra aplicación.

Sus funciones deben distribuirse entre los módulos correspondientes de AllForOne.

## INVENTARIO OBLIGATORIO

Inspeccionar cada archivo Python existente.

Elaborar un inventario de:

- Funciones.
- Clases.
- Dependencias.
- Parámetros.
- Entradas.
- Salidas.
- Procesamientos.
- Tests existentes.

Determinar qué componentes ya están listos, cuáles requieren adaptación y cuáles son experimentales.

## MOTOR DE MEZCLA

Reutilizar `mixer_engine.py`.

Conservar:

- Reconocimiento de tipos.
- Procesamiento por stems.
- Cadenas adaptativas.
- Balance de voces.
- Tratamiento de pistas laterales.
- Gestión de enmascaramiento.
- Referencias.
- Mastering.
- Reportes.

## AFINACIÓN

Reutilizar `scale_tuner.py`.

No sustituir el algoritmo PSOLA por otro sin una prueba comparativa que demuestre la conveniencia del cambio.

## ESPACIO VOCAL

Reutilizar `vocal_space.py`.

Conservar tratamientos diferenciados de reverb y delay para cada rol vocal.

## DSP VOCAL

Reutilizar `vocal_dsp.py`.

Incorporar los procesos correspondientes al panel de mezcla automática y a las cadenas de efectos.

## PLANTILLAS MUSICALES

Reutilizar `mix_templates.py`.

Conservar las nueve guías disponibles en V4.2:

1. Trap oscuro y contundente.
2. Trap melódico y atmosférico.
3. Trap latino y urbano.
4. Rage / hypertrap.
5. Drill.
6. Rap moderno de voz dominante.
7. Boom bap.
8. Guitar trap / emo rap.
9. Trap minimalista.

Respetar su filosofía original: guías contextuales, no presets rígidos.

Preservar los modos originales, entre ellos:

- Solo guía.
- Guía con ajustes sutiles.

Mantener los reportes por stem.

## PRUEBAS

Ejecutar los tests suministrados.

No declarar que las funciones siguen funcionando si la integración rompe pruebas anteriores.

Crear adaptadores cuando sea necesario, evitando reescribir algoritmos estables.

---

# 10. MEZCLA AUTOMÁTICA COMO PROCESO NO DESTRUCTIVO

La mezcla automática debe integrarse con el motor del proyecto.

No mantengas dos sesiones de audio incompatibles.

El motor nativo gestiona la sesión.

Los procesos Python analizan el audio y devuelven:

- Propuestas de parámetros.
- Procesamiento renderizado.
- Reportes.
- Stems corregidos.
- Ajustes.
- Automatizaciones cuando puedan representarse correctamente.

Permitir comparar resultados.

Nunca sobrescribir de forma irreversible el audio original.

Agregar historial y posibilidad de deshacer.

Las mejoras offline no tienen que ejecutarse dentro del callback del motor C++.

---

# 11. VST3 — HOST REAL

JUCE y Tracktion Engine deben encargarse de alojar los plugins.

Implementar:

- Escaneo.
- Categorías.
- Plugins favoritos.
- Instrumentos.
- Efectos.
- Presets.
- Automatización.
- Estado persistente.
- Carga y descarga.
- Envíos.
- Procesamiento real.

El escaneo debe ejecutarse fuera del hilo de audio.

Preferiblemente en un proceso auxiliar.

Registrar plugins que provoquen fallos.

Las interfaces originales de VST pueden requerir ventanas nativas independientes.

No intentes incrustar indiscriminadamente cualquier GUI VST dentro de HTML.

Gestiona sus ventanas mediante el sistema nativo de Windows y Qt, respetando las limitaciones de cada plugin.

Cuando el plugin se cierre, la interfaz principal debe seguir funcionando siempre que el fallo pueda aislarse.

No afirmar aislamiento total de plugins si solamente está implementado el escaneo aislado.

---

# 12. AUDIO Y HARDWARE

El sistema debe detectar los dispositivos de audio disponibles.

Hardware de prueba esperado:

- Windows 11.
- AMD Ryzen 5 5600X.
- 16 GB RAM.
- Behringer UMC22.

No asumir que todos los dispositivos exponen el mismo controlador.

Estudiar:

- ASIO.
- WASAPI.
- Configuración de buffers.
- Frecuencias de muestreo.
- Selección de entradas y salidas.

Implementar pruebas con diferentes buffers.

Evitar interrupciones, bloqueos y asignaciones impredecibles en el hilo crítico.

La IA y la mezcla offline no deben interferir innecesariamente con la reproducción.

---

# 13. PERSISTENCIA DEL PROYECTO

Crear formato de proyecto AllForOne.

Propuesta:

`.afo`

Guardar:

- Tracks.
- Clips.
- Audio.
- MIDI.
- BPM.
- Tonalidad.
- Roles.
- Buses.
- Routing.
- Plugins.
- Estado de VST.
- Racks.
- Automatizaciones.
- Afinación.
- Mezclas automáticas.
- Referencias.
- Layout.
- Posiciones de paneles.
- Zoom.
- Cables.
- Presets.

No limitar el guardado a `localStorage` de la plantilla.

Crear una estructura versionada.

Permitir migraciones futuras.

Garantizar que ocultar un módulo no elimina sus pistas ni su procesamiento.

---

# 14. DOS PLANTILLAS DE ARRANQUE OBLIGATORIAS

## PROYECTO VACÍO

Debe abrir AllForOne sin contenido musical.

Los módulos están disponibles.

No hay pistas ficticias.

El usuario puede añadir y organizar contenido.

## PROYECTO DEMOSTRACIÓN

Debe incluir archivos de prueba legales.

Contendrá:

- Pistas de audio.
- Una voz de prueba si se dispone de material permitido.
- Instrumental.
- Batería.
- Formas de onda reales.
- Mezclador conectado.
- Racks demostrativos.
- Un ejemplo de procesamiento.
- Una comparación antes/después.

No marcar como funcional una característica cuya prueba solo muestra datos inventados.

---

# 15. AUDITORÍA DE LA PLANTILLA ACTUAL

La plantilla original contiene elementos demostrativos que deben convertirse en funcionalidades reales.

Debes identificarlos y sustituir únicamente su lógica simulada, conservando su apariencia.

Ejemplos que requieren atención:

- Reproducción de instrumentos mediante osciladores Web Audio de demostración.
- Secuenciación mediante temporizadores JavaScript.
- Medidores que utilizan valores aleatorios.
- Generación IA que crea clips de ejemplo.
- Exportación que muestra mensajes sin exportar realmente.
- Grabación que puede generar una toma simulada si falla el micrófono.
- Pistas sin integración completa con archivos reales.

No elimines los componentes visuales correspondientes.

Conecta esos controles al motor o marca claramente la función como pendiente hasta que se implemente.

El usuario debe poder distinguir una prueba sintética de una operación real.

---

# 16. COMPILACIÓN Y PRUEBAS DE INTEGRACIÓN

No basta con ejecutar la aplicación desde el entorno de desarrollo.

Debes comprobar:

1. Que C++ compila.
2. Que Python importa la extensión.
3. Que PySide6 abre la interfaz.
4. Que Qt WebEngine carga la plantilla sin errores.
5. Que JavaScript puede comunicarse con Python.
6. Que Python puede comunicarse con C++.
7. Que el motor produce audio real.
8. Que el transporte funciona.
9. Que se importan archivos WAV.
10. Que los medidores reaccionan a audio real.
11. Que se pueden guardar y abrir proyectos.
12. Que un plugin VST3 de prueba procesa audio.
13. Que el ejecutable empaquetado inicia.
14. Que los recursos visuales están incluidos.
15. Que la aplicación funciona sin depender del código fuente situado en `E:\AFO`.

Registrar errores y resultados.

Si una prueba depende de un dispositivo físico, identificarlo.

No declarar aprobada una prueba sin ejecutarla.

---

# 17. PRUEBAS DE FIDELIDAD VISUAL

La apariencia debe probarse de manera explícita.

## COMPARACIÓN

Abrir `PLANTILLA_DAW.html` original.

Capturar su apariencia con un tamaño de ventana conocido.

Abrir AllForOne con la misma distribución y resolución.

Comparar:

- Colores.
- Tipografía.
- Posiciones.
- Tamaños.
- Bordes.
- Sombras.
- Fondo.
- Controles.
- Cabeceras.
- Faders.
- Piano roll.
- Cables.
- Conectores.
- Espaciados.
- Comportamiento de zoom.

No considerar suficiente que ambas interfaces tengan los mismos nombres de módulos.

## CRITERIO

La estructura visual original debe permanecer reconocible y sustancialmente idéntica.

Las diferencias permitidas son las necesarias para agregar funciones reales o mejorar su adaptación a distintas resoluciones.

Documentar cualquier diferencia intencional.

No aprobar una versión si reemplaza la plantilla por otra interfaz.

---

# 18. PLAN DE DESARROLLO POR VERSIONES

Cada versión debe incluir varios componentes relacionados y entregar un resultado funcional.

## V0.1 — PLANTILLA NATIVA COMPILADA

- Auditar `E:\AFO`.
- Conservar el proyecto.
- Preparar Python.
- Preparar PySide6 y Qt WebEngine.
- Abrir la plantilla original.
- Configurar QWebChannel.
- Compilar una extensión C++.
- Conectar el transporte.
- Reproducir audio de prueba.
- Generar ejecutable Windows standalone.

**Resultado:** AllForOne.exe abre con la apariencia original y reproduce audio real.

## V0.2 — PISTAS Y PROYECTOS

- Importación de audio.
- Editor multipista.
- Formas de onda.
- Zoom horizontal.
- Zoom vertical.
- Mixer conectado.
- Persistencia.
- Plantilla vacía.
- Plantilla demo.

**Resultado:** importar, reproducir, editar y guardar audio real.

## V0.3 — VST Y RACKS

- Escaneo VST3.
- Instrumentos.
- Efectos.
- Racks.
- Inspector de efectos.
- Estados.
- Comparador antes/después.

**Resultado:** cargar un plugin, procesar sonido y recuperar su estado.

## V0.4 — GRABACIÓN Y MIDI

- Grabación nativa.
- Monitorización.
- Entradas.
- Piano roll.
- Notas MIDI.
- Instrumentos VST.
- Batería.

**Resultado:** grabar audio y producir una pista instrumental con MIDI.

## V0.5 — INTEGRACIÓN DEL MEZCLADOR AUTOMÁTICO

- Incorporación de V4.2.
- Clasificación por pista.
- Análisis musical.
- Mezcla automática.
- Plantillas trap/rap.
- Remezclar.
- Reportes.
- Comparación A/B.

**Resultado:** ejecutar el mezclador existente desde paneles de AllForOne y escuchar su salida.

## V0.6 — AFINACIÓN Y TRATAMIENTO VOCAL

- Panel afinador.
- Procesamiento PSOLA.
- Roles vocales.
- Reverb/delay.
- Balance de dobles.
- Tratamiento por stem.
- Comparación.

**Resultado:** afinar voces individualmente y aplicar procesamiento verificable.

## V0.7 — MEZCLA FINAL Y MASTERING

- Master real.
- Buses.
- Medición.
- Exportación.
- Referencias.
- Presets.
- Reportes.

## V0.8 — IA

- Análisis avanzado.
- Separación de stems.
- Modelos opcionales.
- Integración de resultados.
- Trabajos asíncronos controlados.

## V0.9 — OPTIMIZACIÓN

- Benchmarks.
- Estabilidad.
- Carga con múltiples pistas.
- Pruebas VST.
- Recuperación ante errores.
- Optimización de interfaz.
- Evaluación de buffers.

## V1.0 — DISTRIBUCIÓN INTEGRADA

- Aplicación empaquetada.
- Instalador si procede.
- Dependencias.
- Documentación.
- Plantillas.
- Sistema de recuperación.
- Tests.
- Licencias.
- Publicación.

---

# 19. REGLAS DE LICENCIAMIENTO

Revisar las condiciones de JUCE, Tracktion Engine, pybind11 y demás dependencias antes de distribuir.

El usuario pretende ofrecer AllForOne gratuitamente.

Sin embargo, distribuirlo gratis no elimina las obligaciones de licencia.

Verificar si el conjunto puede publicarse cumpliendo los términos de las versiones elegidas.

Mantener los avisos correspondientes.

No redistribuir VST comerciales de terceros.

No incorporar bibliotecas incompatibles sin advertirlo.

---

# 20. SEGURIDAD Y RECUPERACIÓN

Antes de modificar:

- Crear copia de seguridad.
- Verificar Git.
- Registrar cambios existentes.
- Crear checkpoint.

Después de cada versión:

- Compilar.
- Ejecutar.
- Probar.
- Guardar logs.
- Registrar errores.
- Crear checkpoint.
- Documentar cambios.

No sobrescribir archivos originales sin una estrategia de recuperación.

No borrar datos del usuario.

No utilizar datos temporales como única copia de proyectos reales.

---

# 21. INFORME DE ENTREGA

Cada versión debe incluir:

### Implementado

Funciones reales y verificadas.

### No implementado

Funciones pendientes.

### Pruebas

Comandos ejecutados y resultados.

### Compilación

Archivos compilados, estado y ubicación del ejecutable.

### Interfaz

Comparación de fidelidad con la plantilla.

### Rendimiento

Mediciones cuando estén disponibles.

### Errores conocidos

Problemas pendientes y posibles soluciones.

### Git

Checkpoint recuperable.

### Siguiente versión

Funciones relacionadas que se implementarán.

---

# 22. PROHIBICIONES ABSOLUTAS

NO convertir AllForOne en un DAW web dependiente del navegador.

NO reemplazar la plantilla HTML original.

NO crear una interfaz Qt diferente sin autorización.

NO crear módulos visualmente incompatibles.

NO sustituir el mezclador V4.2 sin analizarlo.

NO presentar botones decorativos como funciones terminadas.

NO generar medidores falsos.

NO usar clips aleatorios como si fueran IA real.

NO inventar resultados de pruebas.

NO declarar que un VST está cargado cuando no existe una instancia real.

NO perder los datos del proyecto al cambiar el layout.

NO usar la ocultación visual para silenciar involuntariamente una pista.

NO ejecutar análisis Python pesado dentro del hilo de audio.

NO distribuir el proyecto sin revisar las licencias.

NO abandonar el proyecto existente en `E:\AFO`.

NO entregar únicamente código fuente sin compilar cuando el entorno permita construir y probar el programa.

---

# 23. PRIMERA EJECUCIÓN DEL AGENTE

Comienza inmediatamente.

## PASO 1

Localiza y analiza:

- `PLANTILLA_DAW.html`.
- `Mezclador_Automatico.zip`.
- `E:\AFO`.

## PASO 2

Haz un inventario de los componentes existentes, distinguiendo implementación real, demostración y funcionalidad pendiente.

## PASO 3

Verifica las herramientas de compilación de Windows.

## PASO 4

Prepara el motor C++ y sus bindings Python.

## PASO 5

Construye la aplicación PySide6 con Qt WebEngine.

**Carga la plantilla original. No la rediseñes.**

## PASO 6

Conecta QWebChannel y Python.

## PASO 7

Conecta Python con el motor nativo mediante pybind11.

## PASO 8

Implementa transporte y reproducción de audio real.

## PASO 9

Compila el ejecutable standalone.

## PASO 10

Abre, prueba y compara visualmente AllForOne con la plantilla original.

## PASO 11

Corrige errores encontrados.

## PASO 12

Conserva el resultado mediante un checkpoint.

---

# OBJETIVO FINAL INNEGOCIABLE

AllForOne debe ser un DAW profesional construido sobre un motor de audio nativo C++, controlado mediante Python, y presentado con la interfaz modular original de `PLANTILLA_DAW.html`.

El afinador, mezclador automático, racks, pistas, master, instrumentos, efectos, grabación e inteligencia artificial deben aparecer como módulos del mismo lienzo, siguiendo exactamente la identidad visual suministrada.

La interfaz debe representar operaciones reales.

La aplicación debe poder compilarse y ejecutarse en Windows.

El proyecto debe ser extensible, estable, recuperable y verificable.

**NO QUIERO UNA INTERFAZ INSPIRADA EN MI PLANTILLA.**

**QUIERO MI PLANTILLA CONVERTIDA EN UN DAW REAL.**

**NO QUIERO UN MEZCLADOR NUEVO QUE IMITE AL ANTERIOR.**

**QUIERO LAS FUNCIONES DE MI MEZCLADOR AUTOMÁTICO INTEGRADAS EN ALLFORONE.**

**NO QUIERO UNA APLICACIÓN QUE SOLAMENTE SE EJECUTE DESDE PYTHON.**

**QUIERO UN PROGRAMA COMPILADO QUE PUEDA ABRIR COMO CUALQUIER DAW DE WINDOWS.**

Comienza por construir y probar la versión 0.1. No te limites a describir cómo hacerlo.
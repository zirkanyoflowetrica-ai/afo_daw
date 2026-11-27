"""Registro único de órdenes de AllForOne (F1, docs/FLUJO_PROFESIONAL.md §4.2).

Cada orden existe una vez aquí y de aquí salen la barra de menús, el clic derecho en clips y pistas,
la paleta (Ctrl+K) y el atajo que muestran. La interfaz (Main.qml, `runAction`) la ejecuta; el
selftest comprueba que ninguna orden de la lista se quede sin hacer nada.

Campos: id, label, menu (uno de MENUS), group (separador dentro del menú), keys (el atajo tal como se
muestra; vacío si no tiene), tip (qué hace, ≤ 1 frase), ctx («clip», «track» o ambos: sale en ese clic
derecho), ai (True: lo hace la IA en tu equipo; lleva la marca «IA»).
"""
from __future__ import annotations

MENUS = ("Archivo", "Editar", "Transporte", "Pista", "Clip", "Mezcla", "Scripts", "Ver")

_A = [
    # Archivo
    ("file.home", "Inicio: artistas y recientes", "Archivo", 1, "F4", "Vuelve a la pantalla de inicio con tus canciones"),
    ("file.open", "Abrir proyecto…", "Archivo", 1, "Ctrl+O", "Abre un proyecto .afo"),
    ("file.save", "Guardar", "Archivo", 2, "Ctrl+S", "Guarda el proyecto"),
    ("file.saveAs", "Guardar como…", "Archivo", 2, "Ctrl+Shift+S", "Guarda el proyecto con otro nombre"),
    ("file.import", "Importar audio…", "Archivo", 3, "", "Añade archivos de audio como pistas nuevas"),
    ("file.export", "Exportar mezcla…", "Archivo", 3, "", "Escribe la mezcla con el master en un WAV"),
    ("file.audio", "Ajustes de audio…", "Archivo", 4, "Ctrl+,", "Tarjeta de sonido, frecuencia y búfer"),
    # Editar
    ("edit.undo", "Deshacer", "Editar", 1, "Ctrl+Z", "Deshace la última edición de clips; en el Mezclador, la mezcla automática"),
    ("edit.redo", "Rehacer", "Editar", 1, "Ctrl+Y", "Rehace lo deshecho"),
    ("edit.analyze", "Analizar el proyecto", "Editar", 3, "", "Tempo, tonalidad, acordes y secciones del audio que suena: pista de acordes y marcadores en el Arreglo (Ctrl+Z lo deshace)"),
    ("edit.split", "Dividir en el cursor", "Editar", 2, "S", "Divide el clip elegido donde está el cursor de reproducción"),
    ("edit.duplicate", "Duplicar", "Editar", 2, "Ctrl+D", "Copia el clip detrás del último de su pista"),
    ("edit.delete", "Borrar", "Editar", 2, "Supr", "Quita el clip elegido"),
    ("edit.snap", "Ajustar a la rejilla", "Editar", 3, "", "Mover, recortar y cortar caen en los tiempos del compás"),
    ("edit.toolMove", "Herramienta Mover", "Editar", 3, "", "Arrastra clips para moverlos y sus bordes para recortarlos"),
    ("edit.toolCut", "Herramienta Cortar", "Editar", 3, "", "Clic en un clip lo divide en ese punto"),
    # Transporte (G1)
    ("transport.play", "Reproducir o pausar", "Transporte", 1, "Espacio", "Reproduce desde el cursor o lo pausa"),
    ("transport.stop", "Detener y volver al principio", "Transporte", 1, "Mayús+Espacio", "Para y lleva el cursor a 0"),
    ("transport.metronome", "Metrónomo", "Transporte", 2, "C", "Clic en cada tiempo, más fuerte en el primero del compás; suena por tu salida y no entra al exportar"),
    ("transport.loop", "Bucle", "Transporte", 3, "L", "Repite el tramo marcado en la regla (arrastra en la regla para marcarlo); sin tramo, toma la sección del cursor"),
    ("transport.loopSection", "Bucle en la sección del cursor", "Transporte", 3, "Ctrl+L", "Marca como bucle la sección donde está el cursor o, sin secciones, 4 compases desde su compás"),
    ("transport.prevMarker", "Ir a la sección anterior", "Transporte", 4, ",", "Lleva el cursor al principio de la sección anterior (o a 0)"),
    ("transport.nextMarker", "Ir a la sección siguiente", "Transporte", 4, ".", "Lleva el cursor al principio de la sección siguiente"),
    # Pista
    ("track.new", "Pista nueva…", "Pista", 1, "Ctrl+Shift+N", "Audio, instrumento, batería, voz, Intérprete IA o Generar con IA"),
    ("track.newAudio", "Pista nueva de audio…", "Pista", 1, "", "Importa audio en una pista nueva"),
    ("track.newInst", "Pista nueva de instrumento", "Pista", 1, "", "Pista MIDI con el sintetizador o un VST3"),
    ("track.newDrum", "Pista nueva de batería", "Pista", 1, "", "Pista de patrón de batería"),
    ("track.newVoice", "Pista nueva de voz", "Pista", 1, "", "Pista para grabar voz"),
    ("track.newAux", "Bus Aux nuevo", "Pista", 1, "", "Bus de efectos compartidos (reverb, delay)"),
    ("track.generate", "Generar con IA…", "Pista", 2, "", "Canción o parte nueva con ACE-Step, en tu equipo; entra como pista"),
    ("track.interp", "Intérprete IA…", "Pista", 2, "", "La IA escribe las notas: pistas de instrumento normales, editables"),
    ("track.regenerate", "Regenerar con IA", "Pista", 2, "", "Otra versión de la pista generada; entra como toma nueva"),
    ("track.solo", "Solo", "Pista", 3, "", "Escucha solo la pista elegida"),
    ("track.mute", "Silenciar", "Pista", 3, "", "Silencia la pista elegida"),
    ("track.stems", "Separar en pistas", "Pista", 4, "", "Demucs: batería, bajo, voz, guitarra, piano y otros, en la carpeta de la original, que queda silenciada"),
    ("track.effects", "Ver su cadena de efectos", "Pista", 4, "", "Abre la cadena de efectos de la pista en el panel de abajo"),
    ("track.consolidate", "Consolidar clips en un audio", "Pista", 4, "", "Une los clips de la pista (con su ganancia, fundidos y estiramiento) en un solo archivo; lo de antes queda como toma"),
    ("track.freeze", "Congelar pista", "Pista", 4, "", "La pista suena desde su audio con el instrumento y los efectos ya aplicados: dejan de gastar CPU. Para editarla, se descongela"),
    ("track.unfreeze", "Descongelar pista", "Pista", 4, "", "Vuelve a procesar el instrumento y los efectos en vivo para poder editarlos"),
    ("track.midiKeys", "Tocar con el teclado MIDI", "Pista", 4, "", "La pista de instrumento suena con tu teclado MIDI, el de pantalla del Piano roll o el del ordenador (A W S E D F T G Y H U J K)"),
    ("track.remove", "Quitar pista…", "Pista", 5, "", "Quita la pista con su canal y sus efectos (pide confirmación)"),
    # Clip
    ("clip.split", "Dividir en el cursor", "Clip", 1, "S", "Divide el clip donde está el cursor de reproducción"),
    ("clip.duplicate", "Duplicar", "Clip", 1, "Ctrl+D", "Copia el clip detrás del último de su pista"),
    ("clip.delete", "Borrar", "Clip", 1, "Supr", "Quita el clip"),
    ("clip.quantize", "Cuantizar notas", "Clip", 1, "Q", "Alinea el inicio de las notas de la pista de instrumento a la rejilla del Piano roll (1/16 de fábrica)"),
    ("clip.gainUp", "Subir 1 dB", "Clip", 2, "", "Sube el volumen del clip"),
    ("clip.gainDown", "Bajar 1 dB", "Clip", 2, "", "Baja el volumen del clip"),
    ("clip.normalize", "Normalizar a −1 dBFS", "Clip", 2, "", "Deja el pico del clip en −1 dBFS"),
    ("clip.fadeIn", "Fundido de entrada +0,25 s", "Clip", 3, "", "Alarga el fundido de entrada"),
    ("clip.fadeOut", "Fundido de salida +0,25 s", "Clip", 3, "", "Alarga el fundido de salida"),
    ("clip.noFades", "Quitar fundidos", "Clip", 3, "", "Quita los fundidos del clip"),
    ("clip.repaint", "Rehacer con IA…", "Clip", 4, "", "La IA vuelve a tocar el trozo con el mismo estilo; entra como toma nueva de la pista"),
    ("clip.cover", "Versión con IA…", "Clip", 4, "", "La IA hace su versión del clip en una pista de la carpeta de la original"),
    ("clip.align", "Alinear a la guía…", "Clip", 4, "", "Ajusta el tiempo de su pista a la guía sin cambiar el tono; entra como toma nueva"),
    ("clip.pitch", "Editar tono", "Clip", 4, "", "Analiza las notas de la voz y abre el editor de tono"),
    ("clip.stems", "Separar en pistas", "Clip", 4, "", "Demucs: separa la pista del clip en instrumentos, en una carpeta bajo la original"),
    ("clip.tempoKey", "Tempo y tonalidad…", "Clip", 5, "", "Detecta el tempo y la tonalidad del audio y los acomoda"),
    ("clip.toProjectTempo", "Audio al tempo del proyecto", "Clip", 5, "", "Estira el clip al tempo del proyecto sin cambiar su tono"),
    ("clip.projectToTempo", "Proyecto al tempo del audio", "Clip", 5, "", "Pone el proyecto al tempo detectado en el audio"),
    ("clip.toProjectKey", "Audio a la tonalidad del proyecto", "Clip", 5, "", "Transpone el clip a la tonalidad del proyecto sin cambiar su tempo"),
    ("clip.projectToKey", "Proyecto a la tonalidad del audio", "Clip", 5, "", "Transpone el resto del proyecto (audio e instrumentos) a la tonalidad del audio"),
    ("clip.original", "Tempo y tono originales", "Clip", 5, "", "El clip vuelve a su velocidad y su tono"),
    # Mezcla
    ("mix.auto", "Mezcla automática…", "Mezcla", 1, "", "La IA pone faders, paneo y efectos (marca «IA») en las tiras; Ctrl+Z en el Mezclador la deshace"),
    ("mix.remix", "Volver a mezclar", "Mezcla", 1, "", "Repite la mezcla automática con los ajustes de ahora"),
    ("mix.abA", "Escuchar sin mezcla automática (A)", "Mezcla", 2, "", "Puentea los efectos de la mezcla automática"),
    ("mix.abB", "Escuchar con mezcla automática (B)", "Mezcla", 2, "", "Vuelve a activar los efectos de la mezcla automática"),
    ("mix.master", "Master automático", "Mezcla", 3, "", "La IA pone la cadena del master midiendo la mezcla (dispositivo del master en Efectos; A/B en la tira MASTER)"),
    ("mix.masterFx", "Efectos del master", "Mezcla", 3, "", "Abre la cadena de efectos del master"),
    # Ver
    ("view.arrange", "Arreglo", "Ver", 1, "F5", "Pistas, clips y automatización"),
    ("view.mixer", "Mezclador", "Ver", 1, "F6", "La consola: una tira por pista y el master"),
    ("view.toggle", "Cambiar Arreglo ⇄ Mezclador", "Ver", 1, "Tab", "Pasa de una vista a la otra"),
    ("view.lab", "Instrumental por piezas…", "Pista", 2, "F8", "Familias (batería, bajo…) con variantes como tomas de su pista"),
    ("view.dual", "Doble flujo (Arreglo en otra ventana)", "Ver", 2, "F7", "El Arreglo en un segundo monitor y el Mezclador aquí"),
    ("view.nav", "Mostrar u ocultar el navegador", "Ver", 3, "Ctrl+B", "Pliega la zona del navegador"),
    ("view.insp", "Mostrar u ocultar el inspector", "Ver", 3, "Ctrl+I", "Pliega la zona del inspector"),
    ("view.detail", "Mostrar u ocultar el panel de abajo", "Ver", 3, "Ctrl+E", "Pliega el panel de detalle"),
    ("view.reset", "Restaurar zonas", "Ver", 3, "Ctrl+Shift+R", "Vuelve a la distribución de fábrica"),
    ("view.backdrop", "Fondo…", "Ver", 4, "", "Ninguno (de fábrica), una imagen tuya o capas de parallax detrás de la ventana"),
    ("view.themeOscuro", "Tema Oscuro", "Ver", 4, "", "Carbón cálido (de fábrica)"),
    ("view.themeGrafito", "Tema Grafito", "Ver", 4, "", "Gris medio, mismos colores"),
    ("view.themeClaro", "Tema Claro", "Ver", 4, "", "Fondo claro, mismos colores"),
    ("view.palette", "Buscar una orden…", "Ver", 5, "Ctrl+K", "Escribe lo que quieres hacer y pulsa Intro"),
    # Scripts (F8): encima salen los de la carpeta scripts/ (uno por archivo .py)
    ("script.folder", "Abrir la carpeta de scripts", "Scripts", 9, "", "Tus scripts .py con la API afo; los que dejes ahí salen en este menú y en Ctrl+K"),
    ("script.reload", "Volver a leer los scripts", "Scripts", 9, "", "Pone al día este menú con los archivos de la carpeta scripts"),
]

# Clic derecho: qué órdenes salen sobre un clip de audio y sobre la cabecera de una pista
CTX_CLIP = ("clip.split", "clip.duplicate", "clip.delete", "clip.gainUp", "clip.gainDown", "clip.normalize",
            "clip.fadeIn", "clip.fadeOut", "clip.noFades", "clip.repaint", "clip.cover", "clip.align",
            "clip.pitch", "clip.stems", "clip.tempoKey", "clip.toProjectTempo", "clip.projectToTempo",
            "clip.toProjectKey", "clip.projectToKey", "clip.original")
CTX_TRACK = ("track.solo", "track.mute", "track.effects", "track.consolidate", "track.freeze", "track.unfreeze", "track.stems", "track.regenerate", "track.new", "track.generate",
             "track.interp", "track.newAudio", "track.newInst", "track.newDrum", "track.remove")
# Órdenes que borran: piden un segundo clic en la misma fila (confirmación en el sitio, guía de diseño)
CONFIRM = {"track.remove": "¿Quitar la pista? Clic otra vez", "clip.delete": "¿Borrar el clip? Clic otra vez",
           "edit.delete": "¿Borrar el clip? Clic otra vez"}
AI = {"clip.tempoKey", "track.generate", "track.interp", "track.regenerate", "view.lab", "track.stems", "clip.repaint", "clip.cover", "clip.align", "clip.pitch", "clip.stems",
      "mix.auto", "mix.remix", "mix.master"}


def actions() -> list[dict]:
    out = []
    from . import script_host
    for s in script_host.list_scripts():               # F8: un script = una orden (corre aparte; Ctrl+Z lo deshace)
        out.append({"id": s["id"], "label": s["name"], "menu": "Scripts", "group": 1, "keys": "",
                    "tip": s["tip"] + " (script " + s["file"] + "; Ctrl+Z lo deshace)", "ctx": [], "ai": False, "confirm": ""})
    for aid, label, menu, group, keys, tip in _A:
        ctx = [c for c, ids in (("clip", CTX_CLIP), ("track", CTX_TRACK)) if aid in ids]
        out.append({"id": aid, "label": label, "menu": menu, "group": group, "keys": keys, "tip": tip,
                    "ctx": ctx, "ai": aid in AI, "confirm": CONFIRM.get(aid, "")})
    return out

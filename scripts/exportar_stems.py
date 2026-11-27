"""Exportar stems
Un WAV por pista (con sus efectos y el master) en la carpeta «stems» junto al proyecto.
"""
# Script de ejemplo de AllForOne (F8). El motor pone cada pista en solo y la renderiza; al terminar
# vuelven el Mute y el Solo que tenía cada una. Sin proyecto guardado van a datos/media/stems_<fecha>.
pistas = [p for p in afo.tracks() if p.clips and not p.mute]
if not pistas:
    raise ScriptError("No hay pistas con clips que suenen")
afo.export_stems(tracks=pistas)
afo.log(f"{len(pistas)} stem(s)")

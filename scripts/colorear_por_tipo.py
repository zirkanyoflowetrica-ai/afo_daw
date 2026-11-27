"""Colorear las pistas por tipo
Batería, bajo, voces, teclas, guitarras y efectos: cada familia con su color de la paleta del tema.
"""
# Script de ejemplo de AllForOne (F8). El tipo sale de la pista (voz, batería, instrumento) y, en las
# de audio, de su nombre. Los colores son los de la paleta del tema (afo.colors).
FAMILIAS = [
    ("drums", ("kick", "bombo", "snare", "caja", "clap", "palmas", "hihat", "hi-hat", "hat", "tom", "bateria", "batería", "drum", "perc", "808")),
    ("cinta", ("voz", "vocal", "coro", "voice", "vox", "adlib")),
    ("inst", ("bajo", "bass", "sub")),
    ("piano", ("piano", "keys", "teclas", "rhodes", "pad", "acordes", "synth")),
    ("audios", ("guitarra", "guitar", "gtr")),
    ("fx", ("fx", "riser", "efecto", "ambiente")),
]
POR_TIPO = {"voz": "cinta", "drum": "drums", "inst": "piano", "ia": "ia", "aux": "fx"}

n = 0
for pista in afo.tracks():
    nombre = pista.name.lower()
    color = next((c for c, palabras in FAMILIAS if any(p in nombre for p in palabras)), None)
    color = color or POR_TIPO.get(pista.type, "pistas")
    if color != pista.color:
        pista.set_color(color)
        n += 1
afo.log(f"{n} pista(s) coloreadas por tipo")

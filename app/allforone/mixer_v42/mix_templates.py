"""Guías de producción para rap/trap. Orientativas, nunca sustituyen la escucha.

Ninguna plantilla introduce cadenas de efectos fijas ni cambia el mastering.
Un ajuste OPCIONAL de balance adapta como máximo 1 dB por stem a partir
esencialmente de las medidas originales y del número de capas similares.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json
import re

DEFAULT_TEMPLATE = "trap_oscuro"
GUIDE_ONLY = "Solo guía (audio sin cambios)"
SOFT_GUIDE = "Guía + balance muy sutil"
GUIDE_MODES = [GUIDE_ONLY, SOFT_GUIDE]

# Sesgos orientativos de volumen, NUNCA dB objetivos ni EQ predeterminada.
# Los nombres se refieren a categorías del panel, no a pistas individuales.
PROFILES = {
    "trap_oscuro": {
        "name": "Trap oscuro · contundente", "tag": "808 profundo · centro estable · texturas densas",
        "intent": "Subgrave dominante, percusión precisa, voz presente y melodías sombrías sin barro.",
        "voice": "Voz principal cercana con saturación sutil; dobles y L/R detrás; efectos oscuros y cortos.",
        "low": "Da identidad al 808 y ataque al kick: busca sus frecuencias fuertes y evita que ambos ocupen exactamente la misma zona.",
        "melody": "Deja un motivo protagonista. Usa los demás sintes, guitarras y pads como capas complementarias, no como duplicados igual de fuertes.",
        "space": "Centro relativamente seco; delays filtrados en finales de frase; ambientes laterales más profundos.",
        "checks": ["Traducción del 808 en altavoces pequeños", "Voz inteligible durante los drops", "Subgrave y kick compatibles en mono"],
        "bias": {"Bajo": .45, "Kick": .25, "Voz principal": .25, "Pad / Cuerdas": -.45, "Teclados / Synth": -.15, "Hi-hat": -.20},
    },
    "trap_melodico": {
        "name": "Trap melódico · atmosférico", "tag": "armonías amplias · voz emotiva · aire",
        "intent": "Voz melódica íntima, acordes envolventes y batería sólida sin cubrir los detalles armónicos.",
        "voice": "Afinación vocal según la interpretación; prioriza consonantes y expresividad. Coros más anchos, reverbs controladas.",
        "low": "808 afinado y definido; permite respirar al bajo con un kick corto, sin imponer subgraves extra.",
        "melody": "Piano o guitarra puede llevar el motivo; sintes y pads sostienen armonía en los huecos vocales.",
        "space": "Predelay en voz para conservar claridad; delays sincronizados y fondos con mayor cola.",
        "checks": ["Colas de reverb no tapan frases nuevas", "Voz no compite con la melodía lead", "Profundidad estéreo compatible en mono"],
        "bias": {"Voz principal": .50, "Piano": .20, "Guitarra lead / solo": .20, "Pad / Cuerdas": .20, "Kick": -.10, "Hi-hat": -.20},
    },
    "trap_latino": {
        "name": "Trap latino · urbano", "tag": "voz frontal · groove · brillo controlado",
        "intent": "Rap y melodías claras, groove marcado, percusiones con presencia y capas musicales legibles.",
        "voice": "Articulación clara y voz delante del beat; armonías más profundas y delays rítmicos discretos.",
        "low": "Separa kick y 808, revisa bajo en móvil y evita acumulación en la franja baja del piano y guitarras.",
        "melody": "Guitarra, piano y synth pueden alternar protagonismo según sección; no empujes las tres capas a la vez.",
        "space": "Ambientes cortos en principal; mayor anchura en dobles y elementos armónicos, sin difuminar el groove.",
        "checks": ["Inteligibilidad del español y de consonantes rápidas", "Percusión no agresiva", "Hook distinguible del verso"],
        "bias": {"Voz principal": .50, "Percusion": .20, "Snare": .15, "Piano": .10, "Pad / Cuerdas": -.20},
    },
    "rage_hypertrap": {
        "name": "Rage / hypertrap · energético", "tag": "sintes brillantes · distorsión controlada · impacto",
        "intent": "Energía intensa con sintetizadores agresivos sin perder el centro vocal ni convertir la mezcla en ruido.",
        "voice": "Voz firme con presencia; mantén el carácter de afinación, pero vigila sibilancia y dureza.",
        "low": "Kick definido y 808 audible incluso bajo capas distorsionadas; protege el sub de saturación acumulada.",
        "melody": "Distribuye lead, arpegio y pads por función, no por ganancia máxima. Vigila dureza de sintes en medios-altos.",
        "space": "Contraste: principal seca; colas, throws y elementos laterales en partes de menor densidad.",
        "checks": ["Dureza acumulada entre hats y sintes", "Clipping intermedio en buses", "Hook potente sin aplastar la voz"],
        "bias": {"Teclados / Synth": .45, "Kick": .40, "Snare": .25, "Voz principal": .20, "Pad / Cuerdas": -.35},
    },
    "drill": {
        "name": "Drill · tenso y rítmico", "tag": "808 con deslizamientos · snares secos · espacio oscuro",
        "intent": "Ritmo incisivo, graves móviles y voz firme; el groove manda sin saturar la mezcla.",
        "voice": "Rap cercano y relativamente seco; ad-libs amplios y oscuros, sin competir con la principal.",
        "low": "No aplastes los slides del 808. Ajusta el conflicto con kick según el tiempo y las notas, no con un corte fijo.",
        "melody": "Piano, cuerdas o sinte repetitivo pueden llevar la tensión; reduce capas redundantes detrás de la voz.",
        "space": "Reverb corta y oscura en voz; espacio más profundo en texturas y efectos de transición.",
        "checks": ["Slides del 808 conservan definición", "Timbres agudos no fatigan", "Rap claro encima de los contrapuntos"],
        "bias": {"Bajo": .40, "Snare": .30, "Voz principal": .35, "Pad / Cuerdas": -.20, "Overheads / Platillos": -.20},
    },
    "rap_moderno": {
        "name": "Rap moderno · voz dominante", "tag": "dicción · dinámica · beat limpio",
        "intent": "La narración vocal es el centro; instrumental detallado y contundente, sin sobreprocesar.",
        "voice": "Rap muy inteligible con dinámica consistente y respiraciones naturales; dobles de apoyo, no una segunda principal.",
        "low": "Bajo consistente con kick diferenciado; controla la densidad sin perder transitorios.",
        "melody": "Deja huecos alrededor de la voz. Si hay varias guitarras o sintes, asigna motivos secundarios discretos.",
        "space": "Principal bastante seca con slap/throws ocasionales; fondos más amplios y oscuros.",
        "checks": ["Cada sílaba inteligible a volumen bajo", "Instrumental respira entre barras", "Compresión no borra acentos del rap"],
        "bias": {"Voz principal": .65, "Voz doble": -.15, "Pad / Cuerdas": -.40, "Teclados / Synth": -.25, "Kick": .10},
    },
    "boom_bap": {
        "name": "Boom bap · orgánico", "tag": "breaks · samples · voz natural",
        "intent": "Batería con pegada y textura; bajo cálido y rap natural sobre samples o instrumentos.",
        "voice": "Evita un brillo artificial excesivo; conserva el carácter y el aire natural de la voz.",
        "low": "Bajo redondo y kick con golpe definido; no es obligatorio exagerar el subgrave.",
        "melody": "Pianos, guitarras y samples pueden convivir con menos limpieza quirúrgica si tienen carácter.",
        "space": "Rooms cortas y delays discretos que recuerdan un espacio real; reverbs largas solo como acento.",
        "checks": ["Groove del break permanece", "Ruido/textura intencionados no se limpian de más", "Comparar master a volumen igualado"],
        "bias": {"Snare": .35, "Kick": .20, "Piano": .25, "Voz principal": .25, "Hi-hat": -.15, "Pad / Cuerdas": -.35},
    },
    "guitar_trap": {
        "name": "Guitar trap · emo rap", "tag": "guitarras por capas · 808 · voz íntima",
        "intent": "Guitarras con identidad, fondo emocional amplio y voz íntima por delante del arreglo.",
        "voice": "Conserva formantes y expresión; coros más profundos, dobles con volumen secundario.",
        "low": "El 808 sostiene la base; evita que resonancias graves de varias guitarras lo enturbien.",
        "melody": "Separa guitarra rítmica, arpegio y melodía por función y ubicación; solo panea según la toma real.",
        "space": "Reverbs de guitarra filtradas, voz frontal y ambiente amplio en coros y apoyos.",
        "checks": ["Guitarras L/R no se cancelan en mono", "Chasquidos de púa no se disparan", "Voz mantiene cercanía"],
        "bias": {"Guitarra ritmica": .35, "Guitarra lead / solo": .45, "Guitarra acustica": .25, "Voz principal": .35, "Pad / Cuerdas": -.30},
    },
    "minimal_trap": {
        "name": "Trap minimalista · espacio y silencio", "tag": "pocas capas · impacto · contraste",
        "intent": "Ritmo con espacios abiertos; cada elemento tiene un propósito identificable.",
        "voice": "Principal íntima y presente; los ad-libs entran en huecos, no constantemente detrás.",
        "low": "Ataque del kick y tono del 808 bien delimitados; no rellenar todos los silencios con subgrave.",
        "melody": "Una idea principal por sección. Silencia capas redundantes antes de intentar arreglarlas con EQ.",
        "space": "Ambiente sutil; throws y transiciones esporádicas, no efectos permanentes.",
        "checks": ["Escuchar los silencios como parte del groove", "Revisar automatización por secciones", "No añadir anchura artificial sin necesidad"],
        "bias": {"Voz principal": .45, "Kick": .25, "Bajo": .20, "Pad / Cuerdas": -.40, "Teclados / Synth": -.20},
    },
}

# Indicaciones ESPECÍFICAS para un rol dentro de cada estilo.
# Nunca convertir estas frases en un corte de EQ fijo ni un fader objetivo.
STYLE_ROLE_NOTES = {
    "trap_oscuro": {
        "lead_vocal": "Mantén la voz en primer plano cuando entren los 808 más fuertes.",
        "808": "Busca cuerpo oscuro con armonía audible, evitando subgrave sin definición.",
        "kick": "El ataque complementa al 808; no compitas por el mismo pico grave.",
        "synth_lead": "El lead puede ser áspero, pero deja espacio a las consonantes de la voz.",
        "synth_pad": "Usa la textura en el fondo y evita acumulación en 200–500 Hz.",
        "guitar_rhythm": "Trata la guitarra como textura; revisa densidad con los sintes oscuros.",
    },
    "trap_melodico": {
        "lead_vocal": "Conserva expresión y respiración; no fuerces afinación rígida en cada frase.",
        "choir": "Armonías abiertas y ambientes profundos, siempre por detrás de la principal.",
        "synth_pad": "Amplía la profundidad sin ocupar el centro de la voz.",
        "piano": "Haz que acordes y arpegios sostengan la emoción, no que tapen la melodía vocal.",
        "guitar_lead": "Automatiza respuestas instrumentales en los silencios de la voz.",
        "808": "Revisa si el subgrave cambia de nota junto a la armonía.",
    },
    "trap_latino": {
        "lead_vocal": "Prioriza claridad de sílabas, especialmente con percusiones rápidas.",
        "percussion": "Haz que el patrón apoye el groove sin subir todos los shakers.",
        "clap": "Conserva el golpe rítmico pero vigila las consonantes y el brillo vocal.",
        "guitar_rhythm": "Puede ser parte central del groove; separa ritmo de melodía.",
        "synth": "Deja un hueco claro a la voz principal y a la percusión.",
    },
    "rage_hypertrap": {
        "lead_vocal": "Compara consonantes con el lead synth agresivo; vigila dureza acumulada.",
        "synth_lead": "Fuerte sin tapar las sílabas ni quemar los medios-altos.",
        "synth_arp": "Revisa densidad y brillo durante los rolls de hi-hat.",
        "hihat": "Los agudos ya pueden venir del sinte; evita que ambos raspen.",
        "808": "Comprueba armónicos después de los saturadores del bus.",
        "kick": "Mantén el transitorio aunque el resto sea muy denso.",
    },
    "drill": {
        "lead_vocal": "Voz firme y seca; no prolongar colas detrás de cada sílaba rápida.",
        "808": "Preserva los slides de afinación y sus ataques; evita comprimir en exceso.",
        "snare": "Ataque seco y preciso; revisar interacción con contrapuntos melódicos.",
        "strings": "Tensión y profundidad sin saturar el rango medio de la voz.",
        "piano": "Repetición definida, no volumen constante por encima del rap.",
    },
    "rap_moderno": {
        "lead_vocal": "Dicción y fraseo mandan; prioriza movimientos suaves por sección.",
        "side_vocal": "No debe sonar como otra voz principal; escucha el grupo L/R al 7 dB de escalón.",
        "double_vocal": "Refuerza palabras concretas, no cada consonante de toda la toma.",
        "synth": "La melodía apoya el relato; prueba reducirla en versos densos.",
        "guitar_lead": "Llena los espacios entre barras en vez de competir con la voz.",
        "808": "Estabilidad y traducción en móvil por encima del subgrave excesivo.",
    },
    "boom_bap": {
        "lead_vocal": "Preserva transitorios naturales del rap y evita exceso de aire sintético.",
        "drumkit": "Conserva groove y textura del break; no separes quirúrgicamente si ya está mezclado.",
        "snare": "Prioriza golpe y caja, sin convertirla en una percusión electrónica dura.",
        "piano": "Respeta carácter de muestras; limpiar no significa eliminar toda la aspereza.",
        "guitar_rhythm": "Respeta medios de la guitarra/sampling y controla solo conflictos audibles.",
        "bass": "Bajo cálido que siga el ritmo; no es obligatorio llenar el subgrave extremo.",
    },
    "guitar_trap": {
        "lead_vocal": "Frontal e íntima; cuidar que la guitarra lead no compita en cada frase.",
        "guitar_rhythm": "Identificar cada toma: acordes o rasgueo, reservar huecos para las otras guitarras.",
        "guitar_lead": "El motivo puede liderar la intro y responder al vocal, automatiza su plano.",
        "guitar_acoustic": "Conserva el gesto acústico sin exagerar chasquidos y ruido de cuerda.",
        "synth_pad": "Utiliza el pad de apoyo, no para duplicar la armonía en el mismo plano.",
        "808": "No dejar que las resonancias graves de varias guitarras oculten el sub.",
    },
    "minimal_trap": {
        "lead_vocal": "Escuchar respiraciones, silencios y contraste de frase, no llenar todo con FX.",
        "synth_lead": "Un motivo claro; silencia notas repetidas si no aportan.",
        "synth_pad": "En los huecos; evitar una alfombra que neutralice el contraste.",
        "808": "Dejar respirar los espacios después de cada nota grave.",
        "hihat": "Ritmo definido; no hace falta añadir variaciones constantes.",
        "fx": "Reservar efectos para transiciones y remates.",
    },
}

# Frecuencias no son recetas de EQ. Son zonas orientativas que se deben ESCUCHAR.
ROLES = {
    "lead_vocal": ("Voz principal", "Comprobar limpieza, afinación individual, resonancias, dinámica, sibilancia y aire. Reverb breve/predelay para mantenerla delante.", "Voz principal vs melodía 1–5 kHz; verificar en el contexto del beat."),
    "side_vocal": ("Voz L/R", "Acompañante: conservar el escalón 5–10 dB bajo principal. EQ complementaria, de-esser y FX propios; nunca agrandar el centro.", "Comprobar L/R y compatibilidad mono; no igualar el volumen de cada doble a la principal."),
    "backing_vocal": ("Apoyo _B", "Al centro, un escalón detrás de la principal. Menos presencia cuando compite y más profundidad por envío.", "Evitar enmascaramiento de consonantes y graves de proximidad."),
    "double_vocal": ("Voz doble", "Alinear por oído con la principal; reducir protagonismo, filtrar graves innecesarios y vigilar sibilancias sumadas.", "No convertir cada doble en una nueva voz principal."),
    "choir": ("Coros / armonías", "Organizar armonías por registro; mayor profundidad y anchura, conservando la voz principal definida.", "No afinar por bus si hay varias notas simultáneas; revisar suma estéreo."),
    "drumkit": ("Batería completa", "Si es un único stem, tratar como kit; la separación DSP en bandas es aproximada, no una separación real de instrumentos.", "No ecualizar supuestos kick/hat separados como si fueran pistas aisladas perfectas."),
    "kick": ("Kick", "Definir ataque y peso en función del 808; compresión solo si el golpe tiene variación útil.", "Conflicto kick/808 en subgraves; comprobar fase y dinámica por secciones."),
    "808": ("808", "Comprobar nota fundamental, subgrave mono y armónicos audibles en móviles. Saturación suave solo si faltan armónicos.", "Que el kick tenga un ataque propio; no imponer cortes ni sidechain fuertes si no hay choque."),
    "bass": ("Bajo / sub", "Separar cuerpo y definición; controlar el nivel sostenido y comparar con el kick.", "Vigilar acumulación bajo 120 Hz y contra-fase entre capas de bajo."),
    "snare": ("Snare / caja", "Balancear cuerpo con ataque; conservar transiente y evaluar una room corta si falta cohesión.", "Comprobar si ya existe clap o snare adicional para evitar exceso de 2–5 kHz."),
    "clap": ("Clap", "Complementar el golpe de caja sin duplicar todos sus agudos; revisar fase y ataque junto al snare.", "Posible acumulación de presencia cuando hay varias capas de clap/snare."),
    "hihat": ("Hi-hat", "Nivel y sibilancia instrumental antes de EQ. Rolls y abiertos pueden necesitar espacio y controles distintos.", "Vigilar aspereza 4–12 kHz con voz y sintes; no abrir estéreo por defecto."),
    "cymbals": ("Platillos / overheads", "Conservar naturalidad del decaimiento, moderar agudos agresivos y eliminar graves solo cuando sean innecesarios.", "Revisar fase si hay varias capturas/platillos."),
    "toms": ("Toms", "Retener ataque y resonancia útil; ajustar graves dependiendo de afinación y arreglo.", "Evitar competir innecesariamente con el kick en los fills."),
    "percussion": ("Percusión adicional", "Dar identidad rítmica con menos protagonismo que kick y caja; dejar espacio al swing.", "No sumar demasiados shakers y hats en la misma zona brillante."),
    "piano": ("Piano / Rhodes", "Distinguir acordes, arpegio y lead; revisar resonancias bajas 150–450 Hz solo si enturbian la voz.", "Si hay múltiples pianos, reservar uno para armonía y otro para motivo/contrapunto."),
    "synth_lead": ("Sinte lead", "Priorizar motivo musical: presencia controlada y automatización entre frases vocales; delay y modulación según el espacio.", "Competencia con la inteligibilidad vocal en medios-altos."),
    "synth_arp": ("Sinte arpegiado / pluck", "Controlar picos, brillo y repetición; ubicarlo como movimiento detrás del lead principal.", "No sumar arpegios del mismo rango/ritmo al mismo volumen."),
    "synth_pad": ("Sinte pad / atmósfera", "Filtrar graves sobrantes solo si hay conflicto; revisar anchura y nivel suave durante versos.", "Más capas de pad no deben ocupar el centro vocal ni degradar mono."),
    "synth": ("Sinte / teclados", "Identificar si es lead, arpegio, pluck o textura antes de ecualizar. Complementar las demás capas.", "No usar la misma EQ, nivel y anchura para varios sintes."),
    "guitar_rhythm": ("Guitarra rítmica", "Ordenar acordes por toma; controlar cuerpo y ruidos de púa, sin imponer corte grave fijo.", "Con dobles reales L/R, comprobar coherencia y no duplicar amplitud artificial."),
    "guitar_lead": ("Guitarra lead / solo", "Conservar articulación y lugar del motivo; si canta la voz, automatizar en vez de pelear por volumen.", "Evitar competir con voz y sintes lead en medios."),
    "guitar_acoustic": ("Guitarra acústica", "Balancear cuerpo con definición de dedos/cuerda; ambiente natural sin exceso de brillo.", "En varias tomas, elegir funciones diferentes y revisar fase de capturas cercanas."),
    "strings": ("Cuerdas / textura", "Mantener profundidad y movimiento; eliminar solo el grave que compita con el bajo o piano.", "Acumulación de medios-graves entre cuerdas, pads y guitarras."),
    "fx": ("FX / transición", "Ajustar picos y colas al arreglo. Automatizar los efectos para que no tapen el drop.", "Revisar acumulación de reverb/delay y ruido antes del master."),
    "other": ("Otro / muestra", "Identificar el papel musical escuchando antes de procesar; no asumir que sea una voz o batería.", "Nombre ambiguo: renombrar el stem mejorará las recomendaciones."),
}

GROUPS = {
    "lead_vocal": "voces principales", "side_vocal": "voces L/R", "backing_vocal": "apoyos", "double_vocal": "dobles", "choir": "coros",
    "808": "bajos", "bass": "bajos", "kick": "kicks", "snare": "cajas/claps", "clap": "cajas/claps",
    "hihat": "hats", "cymbals": "platillos", "toms": "toms", "percussion": "percusiones", "drumkit": "kits",
    "synth_lead": "sintetizadores", "synth_arp": "sintetizadores", "synth_pad": "sintetizadores", "synth": "sintetizadores", "strings": "atmósferas/cuerdas",
    "piano": "pianos/teclados", "guitar_rhythm": "guitarras", "guitar_lead": "guitarras", "guitar_acoustic": "guitarras",
    "fx": "efectos", "other": "otros",
}


def role_for(name: str, kind: str = "") -> str:
    """Enrutamiento de GUÍAS, no reclasificación del audio ni nuevo paneo."""
    s = Path(name).stem.lower()
    k = (kind or "").lower()
    # Identificación vocal explícita antes de buscar palabras de instrumentos.
    if re.search(r"_b(?=_|$)", s) and re.search(r"_([lr])$", s):
        return "side_vocal"
    if re.search(r"_b(?=_|$)", s):
        return "backing_vocal"
    if ("voz" in k or "coros" in k or "vocal" in k) and re.search(r"_([lr])$", s):
        return "side_vocal"
    if "lateral" in k:
        return "side_vocal"
    if "doble" in k:
        return "double_vocal"
    if "coro" in k or "harmon" in s or "choir" in s:
        return "choir"
    if "voz" in k:
        return "lead_vocal"
    if re.search(r"(?<!\w)808(?!\w)", s) or "808" in s or "808" in k:
        return "808"
    if "bajo" in k or "bass" in s or "sub" in s:
        return "bass"
    if "kick" in k:
        return "kick"
    if "snare" in k:
        return "snare"
    if "clap" in s:
        return "clap"
    if "hi-hat" in k or "hat" in s:
        return "hihat"
    if "platillos" in k:
        return "cymbals"
    if "toms" in k:
        return "toms"
    if "percusion" in k or "perc" in s:
        return "percussion"
    if "drums" in k:
        return "drumkit"
    if "guitarra" in k or "gtr" in s or "guitar" in s:
        if "acust" in k or "acous" in s:
            return "guitar_acoustic"
        if "lead" in k or "solo" in k or "lead" in s or "solo" in s:
            return "guitar_lead"
        return "guitar_rhythm"
    if "piano" in k or "rhodes" in s:
        return "piano"
    if "pad" in k or "cuerdas" in k or "strings" in s or "violin" in s:
        return "synth_pad" if "pad" in s else "strings"
    if "synth" in k or "teclados" in k or "synth" in s or "sinte" in s:
        if any(t in s for t in ("lead", "melody", "melodia", "topline")):
            return "synth_lead"
        if any(t in s for t in ("arp", "pluck", "seq")):
            return "synth_arp"
        if any(t in s for t in ("pad", "ambient", "atmos")):
            return "synth_pad"
        return "synth"
    if k == "fx" or "riser" in s or "sfx" in s:
        return "fx"
    return "other"


def _known_type(name: str):
    # Importación diferida para evitar dependencias pesadas al mostrar guías.
    from mixer_engine import guess_type, is_lateral_voice
    kind = guess_type(name)
    if is_lateral_voice(name, kind) and kind != "Voz de apoyo (_B)":
        kind = "Voz lateral (_L/_R)"
    return kind


def inventory(names, kinds=None):
    kinds = list(kinds) if kinds is not None else [_known_type(Path(n).name) for n in names]
    if len(kinds) != len(names):
        raise ValueError('Cada stem requiere su clasificación correspondiente.')
    result = []
    for name, kind in zip(names, kinds):
        role = role_for(Path(name).name, kind)
        result.append({"name": Path(name).name, "kind": kind, "role": role,
                       "group": GROUPS[role]})
    counts = Counter(x["group"] for x in result)
    indexes = Counter()
    for x in result:
        indexes[x["group"]] += 1
        x["layer_index"] = indexes[x["group"]]
        x["layer_count"] = counts[x["group"]]
    return result


def _esc(value):
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("`", "'").replace("\n", " ")


def style_trims(template_key, item, analysis=None):
    """Devuelve pequeño sesgo OPCIONAL, no normalización ni 'preset' de EQ.

    Sin análisis no aplica trim. Sesgo total, incluyendo número de capas,
    acotado estrictamente a +/-1 dB.
    """
    if analysis is None or getattr(analysis, "silent", False):
        return 0.
    role = item['role']
    kind = item['kind']
    p = PROFILES.get(template_key, PROFILES[DEFAULT_TEMPLATE])
    bias = float(p['bias'].get(kind, 0.))
    # No duplicar balance/ducking de L/R y _B ni interferir con la voz afinada.
    if role in ('side_vocal', 'backing_vocal', 'double_vocal', 'choir'):
        bias = 0.
    if item['group'] in ('sintetizadores', 'guitarras', 'pianos/teclados', 'atmósferas/cuerdas'):
        bias -= min(.65, .22 * max(0, item['layer_count'] - 1))
    # Si el stem es casi silencioso, no elevarlo por una receta de estilo.
    rms = float(getattr(analysis, 'rms', 0))
    if rms < .0005:
        bias = min(0., bias)
    return round(max(-1., min(1., bias)), 2)


def recommendations(template_key=DEFAULT_TEMPLATE, names=(), kinds=None):
    if template_key not in PROFILES:
        raise ValueError('Plantilla de mezcla desconocida.')
    p = PROFILES[template_key]
    entries = inventory(names, kinds)
    md = [f"### {p['name']}", f"*{p['tag']}*", "", p['intent'], "",
          "**Jerarquía de mezcla sugerida**", "",
          f"- **Voz:** {p['voice']}", f"- **Kick y bajos:** {p['low']}",
          f"- **Capas musicales:** {p['melody']}", f"- **Profundidad:** {p['space']}", "",
          "**Control de calidad**: " + "; ".join(p['checks']) + ".", ""]
    if entries:
        md += [f"**Guía por stem ({len(entries)})**", "",
               "| Stem | Función detectada | Cómo revisarlo | Conflicto a comprobar |",
               "|---|---|---|---|"]
        for e in entries:
            title, action, conflict = ROLES[e['role']]
            specific = STYLE_ROLE_NOTES[template_key].get(e['role'])
            if specific:
                action += ' En este estilo: ' + specific
            if e['layer_count'] > 1:
                action += (f" Capa {e['layer_index']} de {e['layer_count']} en «{e['group']}»: "
                           "decidir si aporta motivo, armonía, ritmo o textura; no sumarlas como copias idénticas.")
            md.append(f"| `{_esc(e['name'])}` | {_esc(title)} | {_esc(action)} | {_esc(conflict)} |")
        md += ["", "**Capas detectadas:** " + ", ".join(f"{k}: {v}" for k,v in Counter(e['group'] for e in entries).items()) + ".", ""]
    else:
        md += ["Carga stems para ver una guía individual y detectar capas repetidas.", ""]
    md += ["**Importante:** el nombre solo sugiere el tipo; comprueba escuchando cada pista. "
           "Los rangos indicados son zonas de revisión, no cortes o boosts obligatorios. "
           "El panel no reemplaza el análisis acústico ni cambia la afinación confirmada."]
    return "\n".join(md), entries


def export_guide(directory, template_key, tracks):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    markdown, entries = recommendations(template_key,
        [e['name'] for e in tracks], [e['kind'] for e in tracks])
    # Se mantiene separado de decisiones reales del algoritmo.
    markdown += "\n\n### Procesamiento que ejecutó la sesión\n\n"
    for e, result in zip(entries, tracks):
        markdown += f"- **{_esc(e['name'])}:** {_esc(result.get('note',''))}\n"
    path = directory / 'guia_mezcla_por_stems.md'
    path.write_text(markdown, encoding='utf-8')
    manifest = directory / 'guia_mezcla_por_stems.json'
    manifest.write_text(json.dumps({"profile":template_key, "profile_name":PROFILES[template_key]['name'],
                                    "stems":entries},ensure_ascii=False,indent=2),encoding='utf-8')
    return str(path.resolve()), str(manifest.resolve())

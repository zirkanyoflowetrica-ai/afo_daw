"""Ejecutor aislado para Essentia (Python Linux/WSL), responde exclusivamente JSON.

Uso: python essentia_helper.py clave|ritmo /ruta/archivo.wav
No modifica el audio. Su stderr se ignora por el llamador, que captura fallos.
"""
import json
import sys


def run(mode, filename):
    import essentia.standard as es
    if mode == 'clave':
        signal = es.MonoLoader(filename=filename, sampleRate=22050)()
        results = []
        for profile in ('krumhansl', 'edmm', 'temperley'):
            try:
                key, scale, strength = es.KeyExtractor(sampleRate=22050, profileType=profile)(signal)
                if str(scale).lower() in ('major','minor'):
                    results.append(dict(key=str(key), scale=str(scale), strength=float(strength), profile=profile))
            except Exception:
                continue
        return {'keys': results}
    if mode == 'ritmo':
        signal = es.MonoLoader(filename=filename, sampleRate=44100)()
        bpm, ticks, confidence, _, intervals = es.RhythmExtractor2013(method='multifeature')(signal)
        return {'bpm':float(bpm), 'confidence_raw':float(confidence), 'beats': [float(t) for t in ticks]}
    raise ValueError('modo inválido')


if __name__ == '__main__':
    try:
        print(json.dumps(run(sys.argv[1], sys.argv[2]), allow_nan=False))
    except Exception as err:
        print(json.dumps({'error':str(err)}))
        sys.exit(2)

// AllForOne — Pitch Editor (AF-64): ver las notas de una voz y moverlas una a una.
//
// Proceso sin conexión sobre el archivo (no es un efecto de inserción). Análisis: la voz en mono se
// lleva a ~16 kHz y YIN (diferencia normalizada acumulada, umbral 0,15, interpolación parabólica)
// da el tono cada 10 ms entre 60 y 1000 Hz; los tramos con voz se cortan en notas donde el tono salta
// más de 0,7 semitonos durante 30 ms, y cada nota lleva la mediana de su tono. Edición: por nota, un
// desplazamiento (semitonos con decimales) y «enderezar» (0–1: acerca cada instante al centro de la
// nota, quita vibrato y deriva). El cambio de tono es TD-PSOLA: marcas a un periodo de distancia
// donde hay voz (cada 5 ms donde no), granos de Hann de dos periodos recolocados a periodo/razón y
// normalizados por la suma de ventanas: sin cambios la salida es la entrada exacta, y el tiempo no
// cambia. El salto de cada nota se suaviza 50 ms; el enderezado sigue al vibrato y entra en rampa de 30 ms.
#pragma once

#include <juce_core/juce_core.h>

#include <algorithm>
#include <cmath>
#include <vector>

namespace afo::fx
{

struct PitchNote
{
    double start = 0.0, end = 0.0;    // segundos del archivo
    float midi = 0.0f;                // mediana del tono (MIDI con decimales)
    float shift = 0.0f;               // semitonos a mover
    float flatten = 0.0f;             // 0–1: cuánto se endereza hacia el centro
};

struct PitchCurve
{
    double hop = 0.01;                // segundos entre valores
    std::vector<float> midi;          // tono en MIDI; 0 = sin voz
};

namespace pitch
{
// Paso bajo (sinc con ventana de Blackman) y diezmado por `d`
inline std::vector<float> decimate (const std::vector<float>& x, int d)
{
    if (d <= 1) return x;
    const int taps = 16 * d + 1, half = taps / 2;
    std::vector<float> h ((size_t) taps);
    const double fc = 0.45 / d;
    double s = 0.0;
    for (int i = 0; i < taps; ++i)
    {
        const double n = i - half, w = 0.42 - 0.5 * std::cos (2 * juce::MathConstants<double>::pi * i / (taps - 1))
                                        + 0.08 * std::cos (4 * juce::MathConstants<double>::pi * i / (taps - 1));
        const double v = n == 0 ? 2 * fc : std::sin (2 * juce::MathConstants<double>::pi * fc * n) / (juce::MathConstants<double>::pi * n);
        h[(size_t) i] = (float) (v * w); s += v * w;
    }
    for (auto& v : h) v = (float) (v / s);
    std::vector<float> y (x.size() / (size_t) d);
    for (size_t o = 0; o < y.size(); ++o)
    {
        const long long c = (long long) o * d;
        double acc = 0.0;
        for (int i = 0; i < taps; ++i)
        {
            const long long k = c + i - half;
            if (k >= 0 && k < (long long) x.size()) acc += h[(size_t) i] * x[(size_t) k];
        }
        y[o] = (float) acc;
    }
    return y;
}
} // namespace pitch

// Tono cada 10 ms (MIDI, 0 sin voz)
inline PitchCurve analyzePitch (const std::vector<float>& x, double sr)
{
    PitchCurve pc;
    const int d = juce::jmax (1, (int) std::floor (sr / 16000.0));
    const auto y = pitch::decimate (x, d);
    const double sd = sr / d;
    const int tmin = (int) std::floor (sd / 1000.0), tmax = (int) std::ceil (sd / 60.0);
    const int w = (int) std::round (0.03 * sd);
    const int frames = (int) std::floor ((double) x.size() / (0.01 * sr));
    pc.hop = 0.01;
    pc.midi.assign ((size_t) frames, 0.0f);
    double top = 0.0;
    std::vector<double> en ((size_t) frames, 0.0);
    for (int f = 0; f < frames; ++f)
    {
        const long long c = std::llround (f * 0.01 * sd);           // por tiempo: a 44,1 kHz la trama no es un número entero de muestras
        double e = 0.0;
        for (int j = 0; j < w; ++j) { const long long k = c + j - w / 2; if (k >= 0 && k < (long long) y.size()) e += (double) y[(size_t) k] * y[(size_t) k]; }
        en[(size_t) f] = e / w; top = juce::jmax (top, en[(size_t) f]);
    }
    std::vector<double> df ((size_t) tmax + 2);
    for (int f = 0; f < frames; ++f)
    {
        if (en[(size_t) f] < top * 1.0e-5 || en[(size_t) f] < 1.0e-8) continue;       // −50 dB bajo lo más alto: silencio
        const long long c = std::llround (f * 0.01 * sd) - w / 2;
        if (c < 0 || c + w + tmax >= (long long) y.size()) continue;
        const float* p = y.data() + c;
        double run = 0.0; df[0] = 1.0;
        for (int t = 1; t <= tmax; ++t)
        {
            double s = 0.0;
            for (int j = 0; j < w; ++j) { const double v = (double) p[j] - p[j + t]; s += v * v; }
            run += s;
            df[(size_t) t] = run > 0.0 ? s * t / run : 1.0;
        }
        int best = -1;
        for (int t = tmin; t < tmax; ++t)
            if (df[(size_t) t] < 0.15) { while (t + 1 < tmax && df[(size_t) t + 1] < df[(size_t) t]) ++t; best = t; break; }
        if (best < 0)
        {
            int m = tmin;
            for (int t = tmin; t < tmax; ++t) if (df[(size_t) t] < df[(size_t) m]) m = t;
            if (df[(size_t) m] < 0.3) best = m;
        }
        if (best <= tmin || best >= tmax - 1) continue;
        const double a = df[(size_t) best - 1], b = df[(size_t) best], cc = df[(size_t) best + 1];
        const double den = a - 2 * b + cc;
        const double tau = best + (std::abs (den) > 1.0e-12 ? 0.5 * (a - cc) / den : 0.0);
        pc.midi[(size_t) f] = (float) (69.0 + 12.0 * std::log2 (sd / tau / 440.0));
    }
    // Quita tramos sueltos de una trama y saltos de octava de una trama
    for (int f = 1; f + 1 < frames; ++f)
    {
        auto& m = pc.midi;
        if (m[(size_t) f] > 0 && m[(size_t) f - 1] <= 0 && m[(size_t) f + 1] <= 0) m[(size_t) f] = 0;
        else if (m[(size_t) f] > 0 && m[(size_t) f - 1] > 0 && m[(size_t) f + 1] > 0
                 && std::abs (m[(size_t) f - 1] - m[(size_t) f + 1]) < 1.0f && std::abs (m[(size_t) f] - m[(size_t) f - 1]) > 6.0f)
            m[(size_t) f] = 0.5f * (m[(size_t) f - 1] + m[(size_t) f + 1]);
    }
    return pc;
}

// Notas a partir de la curva
inline std::vector<PitchNote> segmentNotes (const PitchCurve& pc)
{
    std::vector<PitchNote> out;
    const auto& m = pc.midi;
    const int n = (int) m.size();
    auto median = [&] (int a, int b)
    {
        std::vector<float> v (m.begin() + a, m.begin() + b);
        std::nth_element (v.begin(), v.begin() + (long) v.size() / 2, v.end());
        return v[v.size() / 2];
    };
    auto flush = [&] (int a, int b)
    {
        if (b - a < 6) return;                                  // menos de 60 ms: no es una nota
        out.push_back ({ a * pc.hop, b * pc.hop, median (a, b), 0.0f, 0.0f });
    };
    int f = 0;
    while (f < n)
    {
        while (f < n && m[(size_t) f] <= 0) ++f;
        if (f >= n) break;
        int a = f;
        while (f < n && m[(size_t) f] > 0)
        {
            // ¿empieza otra nota? 3 tramas seguidas a más de 0,7 st del centro de esta
            if (f - a >= 6)
            {
                const float centre = median (a, f);
                bool jump = f + 3 <= n;
                for (int k = f; jump && k < f + 3; ++k) jump = m[(size_t) k] > 0 && std::abs (m[(size_t) k] - centre) > 0.7f;
                if (jump) { flush (a, f); a = f; }
            }
            ++f;
        }
        flush (a, f);
    }
    return out;
}

// TD-PSOLA con la curva `pc` y las notas editadas. `x`: canales de la toma.
inline void applyPitchEdits (const std::vector<std::vector<float>>& x, double sr, const PitchCurve& pc,
                             const std::vector<PitchNote>& notes, std::vector<std::vector<float>>& out)
{
    const long long len = x.empty() ? 0 : (long long) x[0].size();
    const int frames = (int) pc.midi.size();
    // Semitonos a mover en cada trama: el salto de la nota, suavizado 50 ms en los bordes, más el
    // enderezado (sin suavizar, para que siga al vibrato), que entra en rampa en los primeros y
    // últimos 30 ms de la nota
    std::vector<float> sh ((size_t) frames, 0.0f), fl ((size_t) frames, 0.0f), st ((size_t) frames, 0.0f);
    for (const auto& nt : notes)
    {
        if (std::abs (nt.shift) < 1.0e-4f && nt.flatten <= 0.0f) continue;
        const int a = juce::jmax (0, (int) std::floor (nt.start / pc.hop)), b = juce::jmin (frames, (int) std::ceil (nt.end / pc.hop));
        const float amt = juce::jlimit (0.0f, 1.0f, nt.flatten);
        for (int f = a; f < b; ++f)
        {
            const float m = pc.midi[(size_t) f];
            if (m <= 0) continue;
            sh[(size_t) f] = nt.shift;
            const float ramp = juce::jmin (1.0f, (float) (juce::jmin (f - a, b - 1 - f) + 1) / 3.0f);
            fl[(size_t) f] = amt * ramp * (nt.midi - m);
        }
    }
    for (int f = 0; f < frames; ++f)
    {
        if (pc.midi[(size_t) f] <= 0) continue;
        float acc = 0.0f; int c = 0;
        for (int k = juce::jmax (0, f - 2); k <= juce::jmin (frames - 1, f + 2); ++k) { acc += sh[(size_t) k]; ++c; }
        st[(size_t) f] = acc / (float) c + fl[(size_t) f];
    }
    const double hopS = pc.hop * sr;
    auto frameAt = [&] (double s) { return juce::jlimit (0, juce::jmax (0, frames - 1), (int) std::round (s / hopS)); };
    // Marcas de análisis: un periodo donde hay voz, 5 ms donde no
    const double unv = std::round (0.005 * sr);
    std::vector<double> mk;
    for (double t = 0.0; t < (double) len;)
    {
        mk.push_back (t);
        const float m = pc.midi[(size_t) frameAt (t)];
        t += m > 0 ? sr / (440.0 * std::pow (2.0, (m - 69.0) / 12.0)) : unv;
    }
    mk.push_back ((double) len);
    out.assign (x.size(), std::vector<float> ((size_t) len, 0.0f));
    std::vector<float> wsum ((size_t) len, 0.0f);
    size_t k = 0;
    for (double s = 0.0; s < (double) len;)
    {
        while (k + 1 < mk.size() && std::abs (mk[k + 1] - s) <= std::abs (mk[k] - s)) ++k;
        const size_t kk = juce::jmin (k, mk.size() - 2);
        const double a = mk[kk], T = juce::jmax (8.0, mk[kk + 1] - a);
        const int fr = frameAt (a);
        const double ratio = std::pow (2.0, st[(size_t) fr] / 12.0);
        const int L = (int) std::ceil (T);
        if (std::abs (st[(size_t) fr]) < 1.0e-6f) s = a;          // sin cambio aquí: vuelve a las marcas (lo no tocado sale igual)
        const long long ai = (long long) std::llround (a), si = (long long) std::llround (s);
        for (int i = -L; i < L; ++i)
        {
            const long long src = ai + i, dst = si + i;
            if (src < 0 || src >= len || dst < 0 || dst >= len) continue;
            const float w = 0.5f - 0.5f * (float) std::cos (juce::MathConstants<double>::pi * (i + L + 0.5) / L);
            wsum[(size_t) dst] += w;
            for (size_t c = 0; c < x.size(); ++c) out[c][(size_t) dst] += w * x[c][(size_t) src];
        }
        s += pc.midi[(size_t) fr] > 0 ? T / ratio : T;
    }
    for (long long i = 0; i < len; ++i)
        if (wsum[(size_t) i] > 1.0e-3f)
            for (auto& o : out) o[(size_t) i] /= wsum[(size_t) i];
}

} // namespace afo::fx

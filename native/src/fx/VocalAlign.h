// AllForOne — Vocal Align (AF-67): ajusta el tiempo de una toma (doblaje, coro) a una voz guía.
//
// Proceso sin conexión sobre el archivo entero (no es un efecto de inserción): la toma y la guía se
// ponen en la misma línea de tiempo, se describen cada 5 ms con 20 bandas de energía (dB,
// normalizadas por banda en cada archivo, así no importa que una esté más alta o con otra EQ) y su
// subida (ataques), y un DTW con banda (desplazamiento máximo) busca el camino más barato que casa
// cada instante de la guía con uno de la toma. Ese mapa, suavizado y escalado por la fuerza, mueve
// la toma con WSOLA (ventanas de 30 ms al 50 % que se colocan donde mejor encajan con la anterior):
// cambia el tiempo sin cambiar el tono. Con fuerza 0 (o si ya cuadra) la salida es la toma tal cual.
#pragma once

#include <juce_dsp/juce_dsp.h>

#include <array>
#include <cmath>
#include <limits>
#include <string>
#include <vector>

namespace afo::fx
{

struct AlignStats
{
    double meanShiftMs = 0.0, maxShiftMs = 0.0;   // lo que había que mover (en lo que suenan las dos)
    int activeFrames = 0, frames = 0;
};

namespace align
{
constexpr int bands = 20;
using Feat = std::array<float, bands + 1>;    // 20 bandas + subida

// Rasgos cada `hop` muestras (ventana de Hann de 2048 centrada) y energía de cada trama en dBFS
inline std::vector<Feat> features (const std::vector<float>& x, double sr, int hop, std::vector<float>& energyDb)
{
    constexpr int order = 11, n = 1 << order;
    juce::dsp::FFT fft (order);
    std::vector<float> win (n), buf (2 * n);
    for (int i = 0; i < n; ++i) win[(size_t) i] = 0.5f - 0.5f * std::cos (2.0f * juce::MathConstants<float>::pi * (float) i / (float) n);
    std::array<int, bands + 1> edge {};
    for (int b = 0; b <= bands; ++b)
        edge[(size_t) b] = juce::jlimit (1, n / 2, (int) std::round (80.0 * std::pow (100.0, (double) b / bands) * n / sr));
    for (int b = 1; b <= bands; ++b) edge[(size_t) b] = juce::jmax (edge[(size_t) b], edge[(size_t) b - 1] + 1);

    const int frames = (int) ((x.size() + (size_t) hop - 1) / (size_t) hop);
    std::vector<Feat> f ((size_t) frames);
    energyDb.assign ((size_t) frames, -120.0f);
    const double winPow = 0.375 * n;
    for (int t = 0; t < frames; ++t)
    {
        const long long c = (long long) t * hop - n / 2;
        double e = 0.0;
        for (int i = 0; i < n; ++i)
        {
            const long long k = c + i;
            const float v = k >= 0 && k < (long long) x.size() ? x[(size_t) k] : 0.0f;
            buf[(size_t) i] = v * win[(size_t) i];
            e += (double) v * v * win[(size_t) i] * win[(size_t) i];
        }
        std::fill (buf.begin() + n, buf.end(), 0.0f);
        energyDb[(size_t) t] = (float) (10.0 * std::log10 (e / winPow + 1.0e-12));
        fft.performFrequencyOnlyForwardTransform (buf.data());
        for (int b = 0; b < bands; ++b)
        {
            double s = 0.0;
            for (int k = edge[(size_t) b]; k < edge[(size_t) b + 1]; ++k) s += (double) buf[(size_t) k] * buf[(size_t) k];
            f[(size_t) t][(size_t) b] = (float) (10.0 * std::log10 (s / (double) (edge[(size_t) b + 1] - edge[(size_t) b]) + 1.0e-6));
        }
    }
    // Subida: lo que crece cada banda respecto a la trama anterior (marca los ataques de sílaba)
    for (int t = 0; t < frames; ++t)
    {
        float up = 0.0f;
        if (t > 0)
            for (int b = 0; b < bands; ++b) up += juce::jmax (0.0f, f[(size_t) t][(size_t) b] - f[(size_t) t - 1][(size_t) b]);
        f[(size_t) t][bands] = up / bands;
    }
    // Normaliza cada rasgo con media y desviación de lo que suena (la ganancia y la EQ no cuentan)
    const float top = frames ? *std::max_element (energyDb.begin(), energyDb.end()) : -120.0f;
    for (int b = 0; b <= bands; ++b)
    {
        double s = 0.0, s2 = 0.0; int cnt = 0;
        for (int t = 0; t < frames; ++t)
            if (energyDb[(size_t) t] > top - 45.0f) { const double v = f[(size_t) t][(size_t) b]; s += v; s2 += v * v; ++cnt; }
        if (cnt < 2) continue;
        const double m = s / cnt, sd = std::sqrt (juce::jmax (1.0e-6, s2 / cnt - m * m));
        for (int t = 0; t < frames; ++t)
            f[(size_t) t][(size_t) b] = (float) juce::jlimit (-4.0, 4.0, (f[(size_t) t][(size_t) b] - m) / sd);
    }
    return f;
}

// DTW con banda |i − j| ≤ w: para cada trama i de la guía, la trama de la toma que le toca
inline std::vector<double> warpPath (const std::vector<Feat>& g, const std::vector<Feat>& d, int w)
{
    const int n = (int) juce::jmin (g.size(), d.size()), width = 2 * w + 1;
    const float inf = std::numeric_limits<float>::infinity(), pen = 0.15f;
    auto dist = [&] (int i, int j)
    {
        float s = 0.0f;
        for (int b = 0; b < bands; ++b) s += std::abs (g[(size_t) i][(size_t) b] - d[(size_t) j][(size_t) b]);
        return s / bands + 0.5f * std::abs (g[(size_t) i][bands] - d[(size_t) j][bands]);
    };
    std::vector<float> D ((size_t) n * width, inf);
    std::vector<unsigned char> from ((size_t) n * width, 0);       // 0 diagonal, 1 de arriba (i−1), 2 de la izquierda (j−1)
    auto at = [&] (int i, int k) -> float& { return D[(size_t) i * width + (size_t) k]; };
    for (int i = 0; i < n; ++i)
        for (int k = 0; k < width; ++k)
        {
            const int j = i + k - w;
            if (j < 0 || j >= n) continue;
            const float c = dist (i, j);
            if (i == 0 && j == 0) { at (i, k) = c; continue; }
            float best = inf; unsigned char how = 0;
            if (i > 0 && j > 0 && at (i - 1, k) < best) { best = at (i - 1, k); how = 0; }
            if (i > 0 && k + 1 < width && at (i - 1, k + 1) + pen < best) { best = at (i - 1, k + 1) + pen; how = 1; }
            if (j > 0 && k > 0 && at (i, k - 1) + pen < best) { best = at (i, k - 1) + pen; how = 2; }
            if (best == inf) continue;
            at (i, k) = best + c; from[(size_t) i * width + (size_t) k] = how;
        }
    std::vector<double> sum ((size_t) n, 0.0), cnt ((size_t) n, 0.0);
    int i = n - 1, k = w;
    while (i >= 0 && k >= 0 && k < width)
    {
        const int j = i + k - w;
        sum[(size_t) i] += j; cnt[(size_t) i] += 1.0;
        if (i == 0 && j == 0) break;
        const auto how = from[(size_t) i * width + (size_t) k];
        if (how == 0) --i; else if (how == 1) { --i; ++k; } else --k;
    }
    std::vector<double> map ((size_t) n);
    for (int t = 0; t < n; ++t) map[(size_t) t] = cnt[(size_t) t] > 0 ? sum[(size_t) t] / cnt[(size_t) t] : t;
    return map;
}

// WSOLA: out[m] ≈ x[src(m)] sin cambiar el tono. `src` da la posición de origen (muestras) del centro
// de cada ventana de salida. Ventana de Hann periódica al 50 %: suma 1, así que sin desplazamiento la
// salida es la entrada exacta.
template <typename Src>
inline void wsola (const std::vector<std::vector<float>>& x, const std::vector<float>& mono, Src src,
                   std::vector<std::vector<float>>& out, double sr)
{
    const long long len = (long long) mono.size();
    const int nw = 2 * (int) std::round (0.015 * sr), hs = nw / 2;
    const int tol = 4 * (int) std::ceil (0.008 * sr / 4.0);
    std::vector<float> win ((size_t) nw);
    for (int i = 0; i < nw; ++i) win[(size_t) i] = 0.5f - 0.5f * std::cos (2.0f * juce::MathConstants<float>::pi * (float) i / (float) nw);
    auto smp = [&] (long long k) { return k >= 0 && k < len ? mono[(size_t) k] : 0.0f; };
    auto ncc = [&] (long long a, long long b, int step)
    {
        double ab = 0.0, aa = 0.0, bb = 0.0;
        for (int i = 0; i < nw; i += step) { const float u = smp (a + i), v = smp (b + i); ab += u * v; aa += u * u; bb += v * v; }
        return aa > 1.0e-12 && bb > 1.0e-12 ? ab / std::sqrt (aa * bb) : (a == b ? 1.0 : 0.0);
    };
    for (auto& o : out) o.assign ((size_t) len, 0.0f);
    long long prev = 0;
    for (long long k = -1; k * hs < len; ++k)
    {
        const long long o = k * hs;
        const long long want = (long long) std::llround (src ((double) (o + hs))) - hs;
        long long pick = want;
        if (k >= 0)
        {
            const long long natural = prev + hs;
            long long best = 0; double bv = ncc (want, natural, 4);
            for (int dlt = -tol; dlt <= tol; dlt += 4)
                if (dlt != 0) { const double v = ncc (want + dlt, natural, 4); if (v > bv) { bv = v; best = dlt; } }
            long long fine = best; double fv = ncc (want + best, natural, 1);
            for (int dlt = -3; dlt <= 3; ++dlt)
                if (dlt != 0) { const double v = ncc (want + best + dlt, natural, 1); if (v > fv) { fv = v; fine = best + dlt; } }
            pick = want + fine;
        }
        for (size_t c = 0; c < x.size(); ++c)
            for (int i = 0; i < nw; ++i)
            {
                const long long m = o + i, s = pick + i;
                if (m >= 0 && m < len && s >= 0 && s < len) out[c][(size_t) m] += x[c][(size_t) s] * win[(size_t) i];
            }
        prev = pick;
    }
}
} // namespace align

// Alinea la toma `dub` (canales, sr) con `guide` (mono, ya en el tiempo de la toma: misma longitud).
// strength 0–1, maxShiftMs: lo más que se puede mover una sílaba.
inline AlignStats alignTake (const std::vector<float>& guide, const std::vector<std::vector<float>>& dub, double sr,
                             float strength, float maxShiftMs, std::vector<std::vector<float>>& out)
{
    AlignStats st;
    const size_t len = dub.empty() ? 0 : dub[0].size();
    std::vector<float> mono (len, 0.0f);
    for (auto& ch : dub)
        for (size_t i = 0; i < len; ++i) mono[i] += ch[i] / (float) dub.size();
    const int hop = juce::jmax (16, (int) std::round (0.005 * sr));
    std::vector<float> eg, ed;
    const auto fg = align::features (guide, sr, hop, eg), fd = align::features (mono, sr, hop, ed);
    const int w = juce::jmax (1, (int) std::round (maxShiftMs * 0.001 * sr / hop));
    auto map = align::warpPath (fg, fd, w);
    const int n = (int) map.size();
    st.frames = n;
    // Suavizado (±30 ms) y siempre hacia delante
    {
        const int r = juce::jmax (1, (int) std::round (0.03 * sr / hop));
        std::vector<double> sm ((size_t) n);
        double acc = 0.0; int cnt = 0;
        for (int t = 0; t < juce::jmin (n, r); ++t) { acc += map[(size_t) t]; ++cnt; }
        for (int t = 0; t < n; ++t)
        {
            if (t + r < n) { acc += map[(size_t) (t + r)]; ++cnt; }
            if (t - r - 1 >= 0) { acc -= map[(size_t) (t - r - 1)]; --cnt; }
            sm[(size_t) t] = acc / cnt;
        }
        for (int t = 1; t < n; ++t) sm[(size_t) t] = juce::jmax (sm[(size_t) t], sm[(size_t) t - 1]);
        map = sm;
    }
    const float topG = eg.empty() ? -120.0f : *std::max_element (eg.begin(), eg.end());
    const float topD = ed.empty() ? -120.0f : *std::max_element (ed.begin(), ed.end());
    double sum = 0.0;
    for (int t = 0; t < n; ++t)
    {
        const double dev = (map[(size_t) t] - t) * hop / sr * 1000.0;
        if (eg[(size_t) t] > topG - 40.0f && ed[(size_t) t] > topD - 40.0f)
        {
            sum += std::abs (dev); ++st.activeFrames;
            st.maxShiftMs = juce::jmax (st.maxShiftMs, std::abs (dev));
        }
        map[(size_t) t] = t + strength * (map[(size_t) t] - t);
    }
    st.meanShiftMs = st.activeFrames ? sum / st.activeFrames : 0.0;
    if (strength <= 0.0f) { out = dub; return st; }
    auto src = [&] (double m)
    {
        const double f = m / hop;
        if (f <= 0.0) return m;
        const int i = (int) f;
        if (i >= n - 1) return m + (map[(size_t) n - 1] - (n - 1)) * hop;
        const double a = f - i, s = map[(size_t) i] + a * (map[(size_t) i + 1] - map[(size_t) i]);
        return s * hop;
    };
    out.assign (dub.size(), {});
    align::wsola (dub, mono, src, out, sr);
    return st;
}

} // namespace afo::fx

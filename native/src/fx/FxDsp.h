// AllForOne — motores DSP compartidos por la biblioteca nativa de efectos.
//
// Como pide la especificación (docs/BIBLIOTECA_NATIVA.md): una plataforma de filtros alimenta EQ,
// channel strip y delays; un detector de dinámica alimenta compresor, gate y channel strip; una
// red de retardos alimenta la reverb. Todo es tiempo real: sin asignaciones ni bloqueos en process().
#pragma once

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <complex>
#include <vector>

namespace afo::fx
{

constexpr double pi = 3.14159265358979323846;

inline float dbToGain (float db) { return db <= -100.0f ? 0.0f : std::pow (10.0f, db / 20.0f); }
inline float gainToDb (float g)  { return g <= 1.0e-5f ? -100.0f : 20.0f * std::log10 (g); }
// Coeficiente de un filtro de un polo que recorre el 63 % en `ms`
inline float onePole (float ms, double sr) { return ms <= 0.0f ? 1.0f : 1.0f - (float) std::exp (-1.0 / (ms * 0.001 * sr)); }

// onePole() recalculado solo cuando cambia el tiempo (evita una exponencial por muestra)
struct Coef
{
    float ms = -1.0f, c = 1.0f;
    float get (float t, double sr) noexcept { if (t != ms) { ms = t; c = onePole (t, sr); } return c; }
};

//==============================================================================
// Biquad del Audio EQ Cookbook (RBJ), coeficientes en double, forma directa transpuesta II
struct Biquad
{
    enum class Type { lowpass, highpass, bell, lowShelf, highShelf, bandpass };
    double b0 = 1, b1 = 0, b2 = 0, a1 = 0, a2 = 0;
    std::array<double, 2> z1 {}, z2 {};

    void set (Type t, double freq, double q, double gainDb, double sr)
    {
        freq = std::clamp (freq, 5.0, sr * 0.49);
        q = std::max (0.025, q);
        const double A = std::pow (10.0, gainDb / 40.0), w = 2 * pi * freq / sr;
        const double c = std::cos (w), s = std::sin (w), alpha = s / (2 * q);
        double n0, n1, n2, d0, d1, d2;
        switch (t)
        {
            case Type::lowpass:  n0 = (1 - c) / 2; n1 = 1 - c; n2 = n0; d0 = 1 + alpha; d1 = -2 * c; d2 = 1 - alpha; break;
            case Type::highpass: n0 = (1 + c) / 2; n1 = -(1 + c); n2 = n0; d0 = 1 + alpha; d1 = -2 * c; d2 = 1 - alpha; break;
            case Type::bandpass: n0 = alpha; n1 = 0; n2 = -alpha; d0 = 1 + alpha; d1 = -2 * c; d2 = 1 - alpha; break;
            case Type::bell:
                n0 = 1 + alpha * A; n1 = -2 * c; n2 = 1 - alpha * A; d0 = 1 + alpha / A; d1 = -2 * c; d2 = 1 - alpha / A; break;
            case Type::lowShelf:
            {
                const double sq = 2 * std::sqrt (A) * alpha;
                n0 = A * ((A + 1) - (A - 1) * c + sq); n1 = 2 * A * ((A - 1) - (A + 1) * c); n2 = A * ((A + 1) - (A - 1) * c - sq);
                d0 = (A + 1) + (A - 1) * c + sq; d1 = -2 * ((A - 1) + (A + 1) * c); d2 = (A + 1) + (A - 1) * c - sq; break;
            }
            default: // highShelf
            {
                const double sq = 2 * std::sqrt (A) * alpha;
                n0 = A * ((A + 1) + (A - 1) * c + sq); n1 = -2 * A * ((A - 1) + (A + 1) * c); n2 = A * ((A + 1) + (A - 1) * c - sq);
                d0 = (A + 1) - (A - 1) * c + sq; d1 = 2 * ((A - 1) - (A + 1) * c); d2 = (A + 1) - (A - 1) * c - sq; break;
            }
        }
        b0 = n0 / d0; b1 = n1 / d0; b2 = n2 / d0; a1 = d1 / d0; a2 = d2 / d0;
    }

    void reset() { z1 = {}; z2 = {}; }

    float process (float x, int ch = 0) noexcept
    {
        const double y = b0 * x + z1[(size_t) ch];
        z1[(size_t) ch] = b1 * x - a1 * y + z2[(size_t) ch];
        z2[(size_t) ch] = b2 * x - a2 * y;
        return (float) y;
    }

    // |H| en dB a la frecuencia dada (para dibujar la curva real del filtro)
    double magnitudeDb (double freq, double sr) const
    {
        const auto z = std::polar (1.0, -2 * pi * freq / sr), z2c = z * z;
        const auto h = (b0 + b1 * z + b2 * z2c) / (1.0 + a1 * z + a2 * z2c);
        return 20.0 * std::log10 (std::max (1.0e-9, std::abs (h)));
    }
};

//==============================================================================
// Línea de retardo con lectura fraccional (interpolación lineal)
struct DelayLine
{
    std::vector<float> buf;
    int w = 0;

    void prepare (int maxSamples) { buf.assign ((size_t) std::max (4, maxSamples + 2), 0.0f); w = 0; }
    void clear() { std::fill (buf.begin(), buf.end(), 0.0f); }
    void push (float x) noexcept { buf[(size_t) w] = x; if (++w >= (int) buf.size()) w = 0; }
    // read(1) = la última muestra escrita; leer antes de escribir da un retardo de `d` muestras
    float read (float d) const noexcept
    {
        const int n = (int) buf.size();
        d = std::clamp (d, 1.0f, (float) (n - 2));
        const int i = (int) d;
        const float f = d - (float) i;
        int a = w - i, b = w - i - 1;
        if (a < 0) a += n;
        if (b < 0) b += n;
        return buf[(size_t) a] + f * (buf[(size_t) b] - buf[(size_t) a]);
    }
    // Interpolación de Lagrange de 3.er orden: retardo fraccional casi plano hasta los agudos
    float readLagrange (float d) const noexcept
    {
        const int n = (int) buf.size();
        d = std::clamp (d, 2.0f, (float) (n - 3));
        const int i = (int) d;
        const float f = d - (float) i;
        auto at = [&] (int k) { int j = w - k; if (j < 0) j += n; return buf[(size_t) j]; };
        const float x0 = at (i - 1), x1 = at (i), x2 = at (i + 1), x3 = at (i + 2);
        return -f * (f - 1) * (f - 2) / 6 * x0 + (f + 1) * (f - 1) * (f - 2) / 2 * x1
               - (f + 1) * f * (f - 2) / 2 * x2 + (f + 1) * f * (f - 1) / 6 * x3;
    }
};

//==============================================================================
// Curva de compresión con rodilla suave (Giannoulis, Massberg y Reiss, 2012). Devuelve la ganancia en dB (≤ 0).
inline float compressorGainDb (float levelDb, float thresholdDb, float ratio, float kneeDb) noexcept
{
    const float over = levelDb - thresholdDb;
    float out;
    if (2.0f * over < -kneeDb)          out = levelDb;
    else if (2.0f * std::abs (over) <= kneeDb && kneeDb > 0.0f)
    {
        const float k = over + kneeDb / 2.0f;
        out = levelDb + (1.0f / ratio - 1.0f) * k * k / (2.0f * kneeDb);
    }
    else                                 out = thresholdDb + over / ratio;
    return std::min (0.0f, out - levelDb);
}

// Compresor estéreo enlazado: detector Peak o RMS, suavizado en dB con ataque y liberación separados
struct Compressor
{
    double sr = 48000;
    float rms = 0.0f, grDb = 0.0f;
    Coef att, rel, rmsCoef;

    void prepare (double sampleRate) { sr = sampleRate; att = rel = rmsCoef = {}; reset(); }
    void reset() { rms = 0.0f; grDb = 0.0f; }

    // Devuelve la ganancia lineal a aplicar a esta muestra
    float next (float l, float r, float thr, float ratio, float knee, float attackMs, float releaseMs, bool rmsMode) noexcept
    {
        float level = std::max (std::abs (l), std::abs (r));
        if (rmsMode)
        {
            rms += rmsCoef.get (10.0f, sr) * (0.5f * (l * l + r * r) - rms);
            level = std::sqrt (std::max (0.0f, rms)) * 1.41421356f;     // una senoidal da el mismo nivel en Peak y RMS
        }
        const float target = compressorGainDb (gainToDb (level), thr, std::max (1.0f, ratio), knee);
        const float coef = target < grDb ? att.get (attackMs, sr) : rel.get (releaseMs, sr);
        grDb += coef * (target - grDb);
        return dbToGain (grDb);
    }
};

// Puerta de ruido: histéresis, mantenimiento, ataque y cierre; `range` es la atenuación al cerrar
struct Gate
{
    double sr = 48000;
    float env = 0.0f, gain = 1.0f;
    int holdLeft = 0;
    bool open = true;
    Coef fall, att, rel;

    void prepare (double sampleRate) { sr = sampleRate; fall = att = rel = {}; reset(); }
    void reset() { env = 0.0f; gain = 1.0f; holdLeft = 0; open = true; }

    float next (float l, float r, float thrDb, float rangeDb, float attackMs, float holdMs, float releaseMs, float hystDb) noexcept
    {
        const float x = std::max (std::abs (l), std::abs (r));
        env = x > env ? x : env + fall.get (5.0f, sr) * (x - env);       // detector de pico con caída de 5 ms
        const float lvl = gainToDb (env);
        if (lvl >= thrDb)                         { open = true; holdLeft = (int) (holdMs * 0.001 * sr); }
        else if (lvl < thrDb - hystDb)
        {
            if (holdLeft > 0) --holdLeft;
            else open = false;
        }
        const float target = open ? 1.0f : dbToGain (rangeDb);
        gain += (target > gain ? att.get (attackMs, sr) : rel.get (releaseMs, sr)) * (target - gain);
        return gain;
    }
};

//==============================================================================
// Reverb de red de retardos realimentada (FDN) de 8 líneas con matriz de Householder (sin pérdidas):
// el tiempo de caída RT60 se fija exactamente con la ganancia de cada línea, g = 10^(−3·L / (RT60·fs)).
struct Fdn
{
    static constexpr int N = 8;
    static constexpr std::array<float, N> baseMs { 29.7f, 37.1f, 41.1f, 43.7f, 53.3f, 59.9f, 67.7f, 73.1f };
    static constexpr std::array<float, 4> diffMs { 4.77f, 3.59f, 12.73f, 9.30f };
    double sr = 48000;
    std::array<DelayLine, N> lines;
    std::array<float, N> len {}, g {}, lp {};
    std::array<DelayLine, 4> diff;
    std::array<float, 4> diffLen {};
    float damp = 0.5f, diffGain = 0.6f;

    void prepare (double sampleRate)
    {
        sr = sampleRate;
        for (auto& l : lines) l.prepare ((int) (0.2 * sr));          // tamaño máximo ×2,6
        for (auto& d : diff)  d.prepare ((int) (0.04 * sr));
        reset();
    }
    void reset() { for (auto& l : lines) l.clear(); for (auto& d : diff) d.clear(); lp = {}; }

    // size 0..1, decay en s, damping: frecuencia de corte del amortiguamiento en Hz, diffusion 0..1
    void set (float size, float decay, float dampHz, float diffusion)
    {
        const float scale = 0.35f + 2.2f * size;
        for (int i = 0; i < N; ++i)
        {
            len[(size_t) i] = baseMs[(size_t) i] * scale * 0.001f * (float) sr;
            g[(size_t) i] = std::pow (10.0f, -3.0f * len[(size_t) i] / (std::max (0.1f, decay) * (float) sr));
        }
        for (int i = 0; i < 4; ++i)
            diffLen[(size_t) i] = diffMs[(size_t) i] * (0.5f + size) * 0.001f * (float) sr;
        damp = 1.0f - (float) std::exp (-2 * pi * std::clamp (dampHz, 200.0f, 20000.0f) / sr);
        diffGain = 0.45f + 0.3f * std::clamp (diffusion, 0.0f, 1.0f);
    }

    // Entrada mono → salida estéreo decorrelada
    void process (float in, float& outL, float& outR) noexcept
    {
        for (int i = 0; i < 4; ++i)                                     // difusión de entrada (pasatodos)
        {
            auto& d = diff[(size_t) i];
            const float delayed = d.read (diffLen[(size_t) i]);
            const float v = in + diffGain * delayed;
            d.push (v);
            in = delayed - diffGain * v;
        }
        std::array<float, N> y {};
        float sum = 0.0f;
        for (int i = 0; i < N; ++i)
        {
            float v = lines[(size_t) i].read (len[(size_t) i]) * g[(size_t) i];
            lp[(size_t) i] += damp * (v - lp[(size_t) i]);               // pérdida de agudos dentro del lazo
            y[(size_t) i] = lp[(size_t) i];
            sum += y[(size_t) i];
        }
        const float h = sum * (2.0f / N);                               // Householder: y − (2/N)·Σy
        outL = outR = 0.0f;
        for (int i = 0; i < N; ++i)
        {
            lines[(size_t) i].push (y[(size_t) i] - h + in);
            outL += (i & 1) ? -y[(size_t) i] : y[(size_t) i];
            outR += (i & 2) ? -y[(size_t) i] : y[(size_t) i];
        }
        outL *= 0.35f; outR *= 0.35f;
    }
};

//==============================================================================
// Copia sin bloqueo de la señal de salida para el analizador (un escritor: audio; un lector: mensajes)
struct ScopeFifo
{
    static constexpr int size = 8192;   // potencia de 2
    std::array<float, size> data {};
    std::atomic<int> write { 0 };

    void push (const float* l, const float* r, int n) noexcept
    {
        int w = write.load (std::memory_order_relaxed);
        for (int i = 0; i < n; ++i)
        {
            data[(size_t) w] = r != nullptr ? 0.5f * (l[i] + r[i]) : l[i];
            w = (w + 1) & (size - 1);
        }
        write.store (w, std::memory_order_release);
    }

    // Las últimas `n` muestras (n ≤ size), de la más antigua a la más nueva
    void latest (float* out, int n) const noexcept
    {
        int w = write.load (std::memory_order_acquire);
        for (int i = 0; i < n; ++i)
            out[i] = data[(size_t) ((w - n + i) & (size - 1))];
    }
};

} // namespace afo::fx

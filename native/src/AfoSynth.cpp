#include "AfoSynth.h"

#include <algorithm>
#include <cmath>

namespace afo::synth
{

namespace
{
    constexpr double pi = 3.14159265358979323846;
    enum Wave { sine, triangle, sawtooth, square };
    constexpr int presetWave[8] = { triangle, sawtooth, square, sawtooth, sine, sawtooth, sine, triangle };

    float osc (int wave, double phase) noexcept
    {
        const double f = phase - std::floor (phase);
        switch (wave)
        {
            case sine:     return (float) std::sin (2 * pi * phase);
            case square:   return f < 0.5 ? 1.0f : -1.0f;
            case sawtooth: return (float) (2 * f - 1);
            default:       return (float) (1 - 4 * std::abs (f - 0.5));
        }
    }

    // exponentialRampToValueAtTime(0.001, t0 + decay) desde g0
    double envelope (double g0, double decay, double seconds) noexcept
    {
        return g0 * std::pow (0.001 / std::max (g0, 1e-6), std::min (1.0, seconds / decay));
    }

    double noteHz (int midiNote) { return 440.0 * std::pow (2.0, (midiNote - 69) / 12.0); }
}

void AtomicParams::store (const Params& p)
{
    mode = p.mode; wave = p.wave; vel = p.vel; bri = p.bri; sus = p.sus; vol = p.vol; tun = p.tun; rev = p.rev;
}

Params AtomicParams::load() const
{
    Params p;
    p.mode = mode; p.wave = wave; p.vel = vel; p.bri = bri; p.sus = sus; p.vol = vol; p.tun = tun; p.rev = rev;
    return p;
}

void Biquad::set (Type type, double freq, double sampleRate)
{
    freq = std::clamp (freq, 10.0, sampleRate / 2 - 100);
    const double w0 = 2 * pi * freq / sampleRate, c = std::cos (w0);
    // Web Audio: Q = 1 por defecto; en lowpass/highpass va en dB, en bandpass es lineal
    const double q = type == Type::bandpass ? 1.0 : std::pow (10.0, 1.0 / 20.0);
    const double alpha = std::sin (w0) / (2 * q), a0 = 1 + alpha;
    double n0, n1, n2;
    if (type == Type::lowpass)       { n0 = (1 - c) / 2; n1 = 1 - c;    n2 = (1 - c) / 2; }
    else if (type == Type::highpass) { n0 = (1 + c) / 2; n1 = -(1 + c); n2 = (1 + c) / 2; }
    else                             { n0 = alpha;       n1 = 0;        n2 = -alpha; }
    b0 = n0 / a0; b1 = n1 / a0; b2 = n2 / a0; a1 = -2 * c / a0; a2 = (1 - alpha) / a0;
    z1 = z2 = 0;
}

float Biquad::process (float x) noexcept
{
    const double y = b0 * x + z1;
    z1 = b1 * x - a1 * y + z2;
    z2 = b2 * x - a2 * y;
    return (float) y;
}

double noteSeconds (const Params& p) { return p.sus ? 1.4 : 0.3; }

void Voice::startNote (const Params& p, int midiNote, double seconds, double sampleRate, int delaySamples)
{
    *this = Voice();
    active = true; delay = std::max (0, delaySamples); sr = sampleRate; mode = 0;
    wave = presetWave[std::clamp (p.wave, 0, 7)];
    freq = noteHz (midiNote);
    decay = seconds;
    length = (int64_t) (seconds * sr);
    g0 = std::max (0.05, p.vel / 100.0) * 0.25;
    filter.set (Biquad::Type::lowpass, 400 + p.bri * 60.0, sr);
    useFilter = true;
}

void Voice::startDrum (const Params& p, int drumLane, double sampleRate, int delaySamples)
{
    *this = Voice();
    active = true; delay = std::max (0, delaySamples); sr = sampleRate; mode = 1;
    lane = std::clamp (drumLane, 0, 7);
    noise = 0x9E3779B9u * (uint32_t) (lane + 1) + (uint32_t) delaySamples;
    const double v = p.vol / 100.0, k = std::pow (2.0, (p.tun - 50.0) / 50.0);
    if (lane == 0 || lane == 5)                      // bombo / tom: seno con barrido
    {
        f0 = (lane ? 170 : 150) * k; f1 = (lane ? 90 : 45) * k;
        g0 = v; decay = lane ? 0.3 : 0.45; length = (int64_t) (0.5 * sr);
    }
    else if (lane == 7)                              // cencerro: dos cuadradas
    {
        f0 = 560 * k; f1 = 845 * k;
        g0 = v * 0.3; decay = 0.2; length = (int64_t) (0.25 * sr);
    }
    else                                             // caja, hi-hats, palmas, platillo: ruido filtrado
    {
        static constexpr double de[] = { 0, 0.18, 0.05, 0.3, 0.12, 0, 0.9 };
        static constexpr double fq[] = { 0, 1200, 7000, 7000, 1500, 0, 5000 };
        g0 = v; decay = de[lane]; length = (int64_t) ((de[lane] + 0.05) * sr);
        filter.set (lane == 4 ? Biquad::Type::bandpass : Biquad::Type::highpass, fq[lane] * k, sr);
        useFilter = true;
    }
}

float Voice::next() noexcept
{
    if (! active) return 0.0f;
    if (delay > 0) { --delay; return 0.0f; }
    if (t >= length) { active = false; return 0.0f; }
    const double sec = (double) t / sr;
    float x;
    if (mode == 0)
    {
        x = osc (wave, phase);
        phase += freq / sr;
    }
    else if (lane == 0 || lane == 5)
    {
        x = osc (sine, phase);
        phase += f0 * std::pow (f1 / f0, std::min (1.0, sec / sweep)) / sr;
    }
    else if (lane == 7)
    {
        x = osc (square, phase) + osc (square, phase2);
        phase += f0 / sr; phase2 += f1 / sr;
    }
    else
    {
        noise = noise * 1664525u + 1013904223u;
        x = (float) ((noise >> 8) * (2.0 / 16777216.0) - 1.0);
    }
    if (useFilter) x = filter.process (x);
    ++t;
    return x * (float) envelope (g0, decay, sec);
}

int hitLengthSamples (const Params& p, int midiNote, double seconds, double sampleRate)
{
    Voice v;
    if (p.mode == 0) v.startNote (p, midiNote, seconds, sampleRate, 0);
    else v.startDrum (p, midiNote - firstDrumNote, sampleRate, 0);
    return (int) v.length;
}

void renderHit (const Params& p, int midiNote, double seconds, double sampleRate, float* out, int numSamples)
{
    Voice v;
    if (p.mode == 0) v.startNote (p, midiNote, seconds, sampleRate, 0);
    else v.startDrum (p, midiNote - firstDrumNote, sampleRate, 0);
    for (int i = 0; i < numSamples; ++i)
        out[i] = v.next();
}

} // namespace afo::synth

#include "AfoSynth.h"

#include <algorithm>
#include <cmath>

namespace afo::synth
{

namespace
{
    constexpr double pi = 3.14159265358979323846;
    enum Wave { sine, triangle, sawtooth, square };
    constexpr int presetWave[numPresets] = { triangle, sawtooth, square, sawtooth, sine, sawtooth, sine, triangle, sine };

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
    glide = p.glide; drive = p.drive; punch = p.punch;
}

Params AtomicParams::load() const
{
    Params p;
    p.mode = mode; p.wave = wave; p.vel = vel; p.bri = bri; p.sus = sus; p.vol = vol; p.tun = tun; p.rev = rev;
    p.glide = glide; p.drive = drive; p.punch = punch;
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
    wave = presetWave[std::clamp (p.wave, 0, numPresets - 1)];
    freq = noteHz (midiNote);
    note = midiNote;
    if (p.wave == bass808)
    {
        is808 = true;
        drive = std::clamp (p.drive, 0.0f, 100.0f) / 100.0;
        punchSemis = std::clamp (p.punch, 0.0f, 100.0f) / 100.0 * 24.0;
    }
    decay = seconds;
    length = (int64_t) (seconds * sr);
    g0 = std::max (0.05, p.vel / 100.0) * 0.25;
    filter.set (Biquad::Type::lowpass, 400 + p.bri * 60.0, sr);
    useFilter = true;
}

void Voice::startHeldNote (const Params& p, int midiNote, float velocity, double sampleRate, int delaySamples)
{
    startNote (p, midiNote, 60.0, sampleRate, delaySamples);       // tope de seguridad: un minuto
    // Sostén y release por preset: piano, bajo, batería (no se usa), guitarra, pad, cuerdas, coro, campanas, 808
    static constexpr double sus[numPresets] = { 0.25, 0.6, 0.3, 0.35, 0.9, 0.85, 0.9, 0.08, 0.55 };
    static constexpr double rel[numPresets] = { 0.15, 0.08, 0.1, 0.12, 0.45, 0.35, 0.4, 0.6, 0.09 };
    static constexpr double att[numPresets] = { 0.004, 0.004, 0.004, 0.004, 0.06, 0.04, 0.05, 0.002, 0.002 };
    const int k = std::clamp (p.wave, 0, numPresets - 1);
    gated = true; note = midiNote;
    sustain = sus[k]; releaseSec = p.sus ? rel[k] * 3 : rel[k]; attack = att[k];
    g0 *= std::clamp (velocity / 100.0, 0.05, 1.27);
}

void Voice::noteOff (int atSample) noexcept
{
    if (offAt >= 0 || released) return;
    offAt = delay > 0 ? std::max (1, atSample - delay) : t + std::max (0, atSample);
}

double Voice::currentHz() const noexcept
{
    if (glideFrom > 0 && glideT < glideSamples)
        return glideFrom * std::pow (freq / glideFrom, glideT / glideSamples);
    return freq;
}

void Voice::glideTo (const Params& p, int midiNote, int atSample) noexcept
{
    pendingNote = midiNote;
    pendingWait = delay > 0 ? std::max (0, atSample - delay) : std::max (0, atSample);
    note = midiNote;
    glideSamples = std::clamp (p.glide, 0.0f, 100.0f) / 100.0 * 0.3 * sr;
}

void Voice::choke() noexcept
{
    if (! active) return;
    if (delay > 0) { active = false; return; }        // aún no sonaba
    if (released && relSec >= 0 && releaseSec <= 0.005) return;
    gated = true; released = true; relLevel = lastEnv; relSec = (double) t / sr; releaseSec = 0.005;
}

void Voice::startDrum (const Params& p, int drumLane, double sampleRate, int delaySamples, const Sample* s)
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
    if (s != nullptr && s->data.size() > 1 && s->sampleRate > 0)    // sampler: el golpe grabado, tal cual
    {
        sample = s; useFilter = false; g0 = v;
        sstep = s->sampleRate / sr * k;
        length = (int64_t) ((double) (s->data.size() - 1) / sstep);
    }
}

float Voice::next() noexcept
{
    if (! active) return 0.0f;
    if (delay > 0) { --delay; return 0.0f; }
    if (t >= length) { active = false; return 0.0f; }
    if (sample != nullptr)
    {
        const auto i = (size_t) spos;
        const float fr = (float) (spos - (double) i), a = sample->data[i], b = sample->data[i + 1];
        spos += sstep;
        ++t;
        return (float) g0 * (a + (b - a) * fr);
    }
    const double sec = (double) t / sr;
    float x;
    if (mode == 0 && is808)
    {
        if (pendingNote >= 0 && pendingWait-- <= 0)
        {
            glideFrom = currentHz(); freq = noteHz (pendingNote); glideT = 0; pendingNote = -1;
            if (glideSamples < 1) glideFrom = 0;
        }
        double f = currentHz();
        if (glideFrom > 0 && glideT < glideSamples) glideT += 1;
        if (punchSemis > 0) f *= std::pow (2.0, punchSemis / 12.0 * std::exp (-sec / 0.04));
        x = osc (sine, phase);
        phase += f / sr;
        if (drive > 0)
        {
            const double k = 1.0 + drive * 9.0;
            x = (float) (std::tanh (k * x) / std::tanh (k));
        }
    }
    else if (mode == 0)
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
    if (gated)
    {
        if (! released && offAt >= 0 && t >= offAt) { released = true; relLevel = lastEnv; relSec = sec; }
        double e;
        if (released)
        {
            const double r = (sec - relSec) / releaseSec;
            if (r >= 1.0) { active = false; return 0.0f; }
            e = relLevel * std::pow (0.001, r);
        }
        else
            e = lastEnv = g0 * std::min (1.0, sec / attack) * (sustain + (1 - sustain) * std::exp (-sec / 0.6));
        return x * (float) e;
    }
    lastEnv = envelope (g0, decay, sec);
    return x * (float) lastEnv;
}

int hitLengthSamples (const Params& p, int midiNote, double seconds, double sampleRate, const Sample* s)
{
    Voice v;
    if (p.mode == 0) v.startNote (p, midiNote, seconds, sampleRate, 0);
    else v.startDrum (p, midiNote - firstDrumNote, sampleRate, 0, s);
    return (int) v.length;
}

void renderHit (const Params& p, int midiNote, double seconds, double sampleRate, float* out, int numSamples,
                const Sample* s)
{
    Voice v;
    if (p.mode == 0) v.startNote (p, midiNote, seconds, sampleRate, 0);
    else v.startDrum (p, midiNote - firstDrumNote, sampleRate, 0, s);
    for (int i = 0; i < numSamples; ++i)
        out[i] = v.next();
}

} // namespace afo::synth

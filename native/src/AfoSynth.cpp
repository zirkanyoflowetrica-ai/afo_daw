#include "AfoSynth.h"

#include <algorithm>
#include <cmath>

namespace afo::synth
{

namespace
{
    constexpr double pi = 3.14159265358979323846;
    enum Wave { sine, triangle, sawtooth, square };
    constexpr int presetWave[numPresets] = { triangle, sawtooth, square, sawtooth, sine, sawtooth, sine, triangle, sine, sawtooth, sine, sine };

    // Diente de sierra con PolyBLEP (sin el aliasing de la sierra ingenua en las notas agudas)
    double blepSaw (double phase, double dt) noexcept
    {
        const double t = phase - std::floor (phase);
        double y = 2 * t - 1;
        if (t < dt)            { const double u = t / dt;       y -= u + u - u * u - 1; }
        else if (t > 1 - dt)   { const double u = (t - 1) / dt; y -= u * u + u + u + 1; }
        return y;
    }

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

    // ---- Tablas de onda: [tabla][nivel][onda][wtSize + 1]; el nivel L tiene 256 >> L armónicos ----
    constexpr int wtSize = 2048, wtFrames = 8, wtLevels = 9, wtMaxHarm = 256, wtStride = wtSize + 1;

    // Coeficientes (seno, coseno) del armónico h de la onda `frame` de la tabla `tab`
    void wtSpectrum (int tab, int frame, int h, double& s, double& c)
    {
        s = c = 0;
        const auto blend = [frame] (int keys, int& k0, double& fr)
        {
            const double x = frame * (keys - 1) / (double) (wtFrames - 1);
            k0 = std::min ((int) x, keys - 2); fr = x - k0;
        };
        const bool odd = (h & 1) != 0;
        if (tab == 0)                           // Básica: seno → triángulo → sierra → cuadrada
        {
            const double key[4] = { h == 1 ? 1.0 : 0.0,
                                    odd ? 8 / (pi * pi * h * h) * (((h - 1) / 2) % 2 ? -1 : 1) : 0.0,
                                    2 / (pi * h) * (odd ? 1 : -1),
                                    odd ? 4 / (pi * h) : 0.0 };
            int k; double fr; blend (4, k, fr);
            s = key[k] + (key[k + 1] - key[k]) * fr;
        }
        else if (tab == 1)                      // Vocal: formantes de u, o, a, e, i sobre un do3
        {
            static constexpr double F[5][3] = { { 325, 700, 2530 }, { 450, 800, 2830 }, { 800, 1150, 2900 },
                                                { 400, 2100, 2800 }, { 290, 2300, 3000 } };
            static constexpr double g[3] = { 1.0, 0.7, 0.3 }, bw[3] = { 80, 110, 160 };
            const double f = 130.81 * h;
            const auto amp = [&] (int v)
            {
                double a = 0.02 / h;
                for (int i = 0; i < 3; ++i) { const double d = (f - F[v][i]) / bw[i]; a += g[i] * std::exp (-0.5 * d * d); }
                return a;
            };
            int k; double fr; blend (5, k, fr);
            s = amp (k) + (amp (k + 1) - amp (k)) * fr;
        }
        else if (tab == 2)                      // Metálica: peines de armónicos que se abren hacia los agudos
        {
            const double a = std::pow (h, -0.7) * (0.5 + 0.5 * std::cos (2 * pi * h * (0.13 + 0.06 * frame)))
                             * std::exp (-h / (3.0 + 2.0 * frame * frame)) * (odd ? 1.0 : 0.6);
            s = ((h * 2654435761u) >> 31) ? -a : a;      // signo fijo por armónico: onda menos picuda
        }
        else                                    // Digital: pulso que se estrecha (50 % → 5 %)
        {
            const double d = 0.5 - 0.45 * frame / (wtFrames - 1.0);
            c = 4 / (pi * h) * std::sin (pi * h * d);
        }
    }

    struct WaveTables
    {
        std::vector<float> data;
        WaveTables() : data ((size_t) wtTables * wtLevels * wtFrames * wtStride)
        {
            std::vector<double> sn (wtSize), x (wtSize);
            for (int n = 0; n < wtSize; ++n) sn[(size_t) n] = std::sin (2 * pi * n / wtSize);
            std::vector<double> s (wtMaxHarm + 1), c (wtMaxHarm + 1);
            for (int tab = 0; tab < wtTables; ++tab)
                for (int fr = 0; fr < wtFrames; ++fr)
                {
                    for (int h = 1; h <= wtMaxHarm; ++h) wtSpectrum (tab, fr, h, s[(size_t) h], c[(size_t) h]);
                    double norm = 1;
                    for (int L = 0; L < wtLevels; ++L)
                    {
                        std::fill (x.begin(), x.end(), 0.0);
                        for (int h = 1; h <= (wtMaxHarm >> L); ++h)
                        {
                            const double a = s[(size_t) h], b = c[(size_t) h];
                            if (a == 0 && b == 0) continue;
                            for (int n = 0; n < wtSize; ++n)
                            {
                                const int i = (h * n) & (wtSize - 1);
                                x[(size_t) n] += a * sn[(size_t) i] + b * sn[(size_t) ((i + wtSize / 4) & (wtSize - 1))];
                            }
                        }
                        if (L == 0)
                        {
                            double pk = 0;
                            for (double v : x) pk = std::max (pk, std::abs (v));
                            norm = pk > 0 ? 1 / pk : 1;
                        }
                        float* out = data.data() + ((size_t) (tab * wtLevels + L) * wtFrames + (size_t) fr) * wtStride;
                        for (int n = 0; n < wtSize; ++n) out[n] = (float) (x[(size_t) n] * norm);
                        out[wtSize] = out[0];
                    }
                }
        }
    };

    const WaveTables& waveTables()
    {
        static const WaveTables w;              // se construye una vez (inicio seguro entre hilos)
        return w;
    }
}

void warmUp() { (void) waveTables(); }

void AtomicParams::store (const Params& p)
{
    mode = p.mode; wave = p.wave; vel = p.vel; bri = p.bri; sus = p.sus; vol = p.vol; tun = p.tun; rev = p.rev;
    glide = p.glide; drive = p.drive; punch = p.punch;
    arp = p.arp; arpRate = p.arpRate; arpOct = p.arpOct; arpGate = p.arpGate;
    for (size_t i = 0; i < 8; ++i) { dTun[i] = p.dTun[i]; dDec[i] = p.dDec[i]; dTone[i] = p.dTone[i]; dLvl[i] = p.dLvl[i];
                                     dPan[i] = p.dPan[i]; dChoke[i] = p.dChoke[i]; }
    anDet = p.anDet; anCut = p.anCut; anRes = p.anRes; anEnv = p.anEnv; anAtk = p.anAtk; anRel = p.anRel;
    wtTab = p.wtTab; wtPos = p.wtPos; wtEnv = p.wtEnv; wtLfo = p.wtLfo; wtAtk = p.wtAtk; wtRel = p.wtRel;
    smRoot = p.smRoot; smStart = p.smStart; smLoop = p.smLoop; smLoopAt = p.smLoopAt; smAtk = p.smAtk; smRel = p.smRel;
}

Params AtomicParams::load() const
{
    Params p;
    p.mode = mode; p.wave = wave; p.vel = vel; p.bri = bri; p.sus = sus; p.vol = vol; p.tun = tun; p.rev = rev;
    p.glide = glide; p.drive = drive; p.punch = punch;
    p.arp = arp; p.arpRate = arpRate; p.arpOct = arpOct; p.arpGate = arpGate;
    for (size_t i = 0; i < 8; ++i) { p.dTun[i] = dTun[i]; p.dDec[i] = dDec[i]; p.dTone[i] = dTone[i]; p.dLvl[i] = dLvl[i];
                                     p.dPan[i] = dPan[i]; p.dChoke[i] = dChoke[i]; }
    p.anDet = anDet; p.anCut = anCut; p.anRes = anRes; p.anEnv = anEnv; p.anAtk = anAtk; p.anRel = anRel;
    p.wtTab = wtTab; p.wtPos = wtPos; p.wtEnv = wtEnv; p.wtLfo = wtLfo; p.wtAtk = wtAtk; p.wtRel = wtRel;
    p.smRoot = smRoot; p.smStart = smStart; p.smLoop = smLoop; p.smLoopAt = smLoopAt; p.smAtk = smAtk; p.smRel = smRel;
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

void Voice::startNote (const Params& p, int midiNote, double seconds, double sampleRate, int delaySamples, const Sample* s)
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
    if (p.wave == analog)
    {
        isAnalog = true; useFilter = false;
        const auto pc = [] (float v) { return std::clamp ((double) v, 0.0, 100.0) / 100.0; };
        detune = std::pow (2.0, pc (p.anDet) * 25.0 / 1200.0);
        cutBase = 40.0 * std::pow (2.0, pc (p.anCut) * 9.0) * std::sqrt (freq / 261.63);
        envOct = pc (p.anEnv) * 5.0;
        res = pc (p.anRes) * 0.97;
        attack = 0.001 * std::pow (2.0, pc (p.anAtk) * 11.0);
        releaseSec = 0.01 * std::pow (2.0, pc (p.anRel) * 8.2);
        sustain = 0.7;
        gated = true;                                   // nota de la rejilla: suena `seconds` y libera
        offAt = std::max ((int64_t) 1, (int64_t) (seconds * sr));
        length = offAt + (int64_t) ((releaseSec + 0.05) * sr);
    }
    if (p.wave == wavetable)
    {
        isWave = true; useFilter = false;
        const auto pc = [] (float v) { return std::clamp ((double) v, 0.0, 100.0) / 100.0; };
        int level = 0;                                  // el más rico cuyo armónico más alto queda bajo 0,45·sr
        while (level < wtLevels - 1 && (wtMaxHarm >> level) * freq > 0.45 * sr) ++level;
        wtData = waveTables().data.data() + (size_t) (std::clamp (p.wtTab, 0, wtTables - 1) * wtLevels + level) * wtFrames * wtStride;
        wtPos = pc (p.wtPos); wtSweep = pc (p.wtEnv); wtLfo = pc (p.wtLfo) * 0.35;
        attack = 0.001 * std::pow (2.0, pc (p.wtAtk) * 11.0);
        releaseSec = 0.01 * std::pow (2.0, pc (p.wtRel) * 8.2);
        sustain = 0.7;
        gated = true;
        offAt = std::max ((int64_t) 1, (int64_t) (seconds * sr));
        length = offAt + (int64_t) ((releaseSec + 0.05) * sr);
    }
    if (p.wave == sampler)
    {
        isSampler = true; useFilter = false;
        if (s == nullptr || s->data.size() < 2 || s->sampleRate <= 0) { active = false; length = 0; return; }   // sin sonido cargado: no suena
        const auto pc = [] (float v) { return std::clamp ((double) v, 0.0, 100.0) / 100.0; };
        const double last = (double) (s->data.size() - 1);
        sample = s;
        sstep = s->sampleRate / sr * std::pow (2.0, (midiNote - std::clamp (p.smRoot, 0, 127)) / 12.0);
        spos = std::floor (pc (p.smStart) * last * 0.99);
        smLoop = p.smLoop;
        loopEnd = last;
        loopStart = std::max (spos, std::floor (pc (p.smLoopAt) * last * 0.99));
        xfade = std::min (0.01 * s->sampleRate, (loopEnd - loopStart) / 2);
        if (loopEnd - loopStart < 64) smLoop = false;       // bucle demasiado corto: sin bucle
        g0 = std::max (0.05, p.vel / 100.0) * 0.5;
        attack = 0.001 * std::pow (2.0, pc (p.smAtk) * 11.0);
        releaseSec = 0.01 * std::pow (2.0, pc (p.smRel) * 8.2);
        sustain = 1.0;                                      // el sonido conserva su propia forma
        gated = true;
        offAt = std::max ((int64_t) 1, (int64_t) (seconds * sr));
        length = offAt + (int64_t) ((releaseSec + 0.05) * sr);
    }
}

void Voice::startHeldNote (const Params& p, int midiNote, float velocity, double sampleRate, int delaySamples, const Sample* s)
{
    startNote (p, midiNote, 60.0, sampleRate, delaySamples, s);
    if (! active) return;       // tope de seguridad: un minuto
    // Sostén y release por preset: piano, bajo, batería (no se usa), guitarra, pad, cuerdas, coro, campanas, 808
    static constexpr double sus[numPresets] = { 0.25, 0.6, 0.3, 0.35, 0.9, 0.85, 0.9, 0.08, 0.55, 0.7, 0.7, 1.0 };
    static constexpr double rel[numPresets] = { 0.15, 0.08, 0.1, 0.12, 0.45, 0.35, 0.4, 0.6, 0.09, 0.3, 0.3, 0.3 };
    static constexpr double att[numPresets] = { 0.004, 0.004, 0.004, 0.004, 0.06, 0.04, 0.05, 0.002, 0.002, 0.005, 0.005, 0.002 };
    const int k = std::clamp (p.wave, 0, numPresets - 1);
    gated = true; note = midiNote;
    if (isAnalog || isWave || isSampler) offAt = -1;                           // ataque y liberación ya vienen de sus perillas
    else { sustain = sus[k]; releaseSec = p.sus ? rel[k] * 3 : rel[k]; attack = att[k]; }
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

void Voice::chokeAt (int atSample) noexcept
{
    if (! active) return;
    const int w = atSample - delay;                    // muestras de esta voz hasta el golpe que corta
    if (w < 0) return;                                 // esta voz empieza después: no se corta
    chokeWait = w;
}

void Voice::startDrum (const Params& p, int drumLane, double sampleRate, int delaySamples, const Sample* s)
{
    *this = Voice();
    active = true; delay = std::max (0, delaySamples); sr = sampleRate; mode = 1;
    lane = std::clamp (drumLane, 0, 7);
    {
        const double pan = std::clamp (p.dPan[(size_t) lane], 0.0f, 100.0f) / 100.0;
        panL = (float) std::min (1.0, 2.0 * (1.0 - pan)); panR = (float) std::min (1.0, 2.0 * pan);
    }
    noise = 0x9E3779B9u * (uint32_t) (lane + 1) + (uint32_t) delaySamples;
    const auto L = (size_t) lane;
    const double lvl = std::clamp (p.dLvl[L], 0.0f, 100.0f) / 50.0;
    const double v = p.vol / 100.0 * lvl * lvl;
    const double k = std::pow (2.0, (p.tun - 50.0) / 50.0) * std::pow (2.0, (std::clamp (p.dTun[L], 0.0f, 100.0f) - 50.0) / 50.0);
    const double dk = std::pow (2.0, (std::clamp (p.dDec[L], 0.0f, 100.0f) - 50.0) / 25.0);     // caída ×¼ … ×4
    const double tone = (std::clamp (p.dTone[L], 0.0f, 100.0f) - 50.0) / 50.0;                  // −1 … +1
    if (lane == 0 || lane == 5)                      // bombo / tom: seno con barrido (tono = golpe de afinación)
    {
        f0 = (lane ? 170 : 150) * k * std::pow (2.0, 1.5 * tone); f1 = (lane ? 90 : 45) * k;
        g0 = v; decay = (lane ? 0.3 : 0.45) * dk; length = (int64_t) (std::max (0.5, decay + 0.05) * sr);
    }
    else if (lane == 7)                              // cencerro: dos cuadradas (tono = intervalo entre ellas)
    {
        f0 = 560 * k; f1 = 845 * k * std::pow (2.0, 0.5 * tone);
        g0 = v * 0.3; decay = 0.2 * dk; length = (int64_t) ((0.05 + decay) * sr);
    }
    else                                             // caja, hi-hats, palmas, platillo: ruido filtrado (tono = filtro)
    {
        static constexpr double de[] = { 0, 0.18, 0.05, 0.3, 0.12, 0, 0.9 };
        static constexpr double fq[] = { 0, 1200, 7000, 7000, 1500, 0, 5000 };
        g0 = v; decay = de[lane] * dk; length = (int64_t) ((decay + 0.05) * sr);
        filter.set (lane == 4 ? Biquad::Type::bandpass : Biquad::Type::highpass, fq[lane] * k * std::pow (2.0, 2.0 * tone), sr);
        useFilter = true;
    }
    if (s != nullptr && s->data.size() > 1 && s->sampleRate > 0)    // sampler: el golpe grabado, tal cual
    {
        sample = s; useFilter = false; g0 = v;
        sstep = s->sampleRate / sr * k;
        length = (int64_t) ((double) (s->data.size() - 1) / sstep);
        if (dk < 1.0) length = (int64_t) ((double) length * dk);               // caída: acorta el golpe
    }
}

float Voice::next() noexcept
{
    if (! active) return 0.0f;
    if (delay > 0) { --delay; return 0.0f; }
    if (chokeWait >= 0 && chokeWait-- == 0) choke();
    if (t >= length) { active = false; return 0.0f; }
    if (sample != nullptr && ! isSampler)
    {
        const auto i = (size_t) spos;
        const float fr = (float) (spos - (double) i), a = sample->data[i], b = sample->data[i + 1];
        spos += sstep;
        ++t;
        float y = (float) g0 * (a + (b - a) * fr);
        if (released)                                   // cortado por su grupo: fundido de 5 ms
        {
            const double r = ((double) t / sr - relSec) / releaseSec;
            if (r >= 1.0) { active = false; return 0.0f; }
            y *= (float) std::pow (0.001, r);
        }
        return y;
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
    else if (mode == 0 && isAnalog)
    {
        const double d1 = freq * detune / sr, d2 = freq / detune / sr;
        double y = 0.5 * (blepSaw (phase, d1) + blepSaw (phase2, d2));
        phase += d1; phase2 += d2;
        if (filtWait-- <= 0)                            // coeficientes cada 16 muestras
        {
            filtWait = 15;
            const double fc = std::min (cutBase * std::pow (2.0, envOct * std::exp (-sec / 0.3)), 0.45 * sr);
            const double g = std::tan (pi * fc / sr), k = 2.0 - 2.0 * res;
            fa1 = 1.0 / (1.0 + g * (g + k)); fa2 = g * fa1; fa3 = g * fa2;
        }
        const double v3 = y - ic2, v1 = fa1 * ic1 + fa2 * v3, v2 = ic2 + fa2 * ic1 + fa3 * v3;
        ic1 = 2 * v1 - ic1; ic2 = 2 * v2 - ic2;
        x = (float) v2;
    }
    else if (mode == 0 && isWave)
    {
        if (filtWait-- <= 0)                            // posición en la tabla cada 16 muestras
        {
            filtWait = 15;
            double pos = wtPos + wtSweep * (1.0 - wtPos) * std::exp (-sec / 0.4);
            if (wtLfo > 0) pos += wtLfo * std::sin (2 * pi * sec);
            wtCur = std::clamp (pos, 0.0, 1.0) * (wtFrames - 1);
        }
        const int f = std::min ((int) wtCur, wtFrames - 2);
        const double ff = wtCur - f, ph = (phase - std::floor (phase)) * wtSize, r = ph - std::floor (ph);
        const auto i = (size_t) ph;
        const float* a = wtData + (size_t) f * wtStride;
        const float* b = a + wtStride;
        const double xa = a[i] + (a[i + 1] - a[i]) * r, xb = b[i] + (b[i + 1] - b[i]) * r;
        x = (float) (xa + (xb - xa) * ff);
        phase += freq / sr;
    }
    else if (mode == 0 && isSampler)
    {
        const auto& d = sample->data;
        const auto read = [&d] (double pos) noexcept
        {
            const auto i = (size_t) pos;
            const float fr = (float) (pos - (double) i);
            return i + 1 < d.size() ? d[i] + (d[i + 1] - d[i]) * fr : d.back();
        };
        if (smLoop && ! released)
        {
            while (spos >= loopEnd) spos -= loopEnd - loopStart;
            x = read (spos);
            if (spos > loopEnd - xfade)                    // fundido con el principio del bucle
            {
                const double w = (spos - (loopEnd - xfade)) / xfade;
                x = (float) (x * (1.0 - w) + read (spos - (loopEnd - loopStart)) * w);
            }
        }
        else
        {
            if (spos >= loopEnd) { active = false; return 0.0f; }   // fin del sonido
            x = read (spos);
        }
        spos += sstep;
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
    if (p.mode == 0) v.startNote (p, midiNote, seconds, sampleRate, 0, s);
    else v.startDrum (p, midiNote - firstDrumNote, sampleRate, 0, s);
    return (int) v.length;
}

void renderHit (const Params& p, int midiNote, double seconds, double sampleRate, float* out, int numSamples,
                const Sample* s)
{
    Voice v;
    if (p.mode == 0) v.startNote (p, midiNote, seconds, sampleRate, 0, s);
    else v.startDrum (p, midiNote - firstDrumNote, sampleRate, 0, s);
    for (int i = 0; i < numSamples; ++i)
        out[i] = v.next();
}

} // namespace afo::synth

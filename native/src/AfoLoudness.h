// AllForOne — medidor de sonoridad (ITU-R BS.1770 / EBU R128) y plugin de medida para pistas y master.
//
// Ponderación K (estante +4 dB a 1,68 kHz + paso alto a 38 Hz), bloques de 100 ms:
//   momentánea = últimos 400 ms, corto plazo = últimos 3 s,
//   integrada = media de bloques de 400 ms (solapados 75 %) con puerta absoluta −70 LUFS y relativa −10 LU.
// La integrada se guarda en un histograma de 0,1 LU: el hilo de audio no reserva memoria.
// RMS: media de L y R con constante de 300 ms (una senoidal de pico 0 dBFS da −3 dB RMS).
#pragma once

#include "fx/FxDsp.h"

#include <tracktion_engine/tracktion_engine.h>

namespace afo
{
namespace te = tracktion;

struct LoudnessMeter
{
    static constexpr float floorDb = -70.0f, topDb = 5.0f, step = 0.1f;
    static constexpr int bins = (int) ((topDb - floorDb) / step) + 1;

    void prepare (double sampleRate)
    {
        sr = sampleRate;
        // Coeficientes exactos de BS.1770 para cualquier frecuencia de muestreo (derivación de B. De Man):
        // a 48 kHz dan los de la norma
        fx::Biquad shelf, hp;
        {
            const double f0 = 1681.974450955533, g = 3.999843853973347, q = 0.7071752369554196;
            const double K = std::tan (fx::pi * f0 / sr), vh = std::pow (10.0, g / 20.0), vb = std::pow (vh, 0.4996667741545416);
            const double a0 = 1.0 + K / q + K * K;
            shelf.b0 = (vh + vb * K / q + K * K) / a0; shelf.b1 = 2.0 * (K * K - vh) / a0; shelf.b2 = (vh - vb * K / q + K * K) / a0;
            shelf.a1 = 2.0 * (K * K - 1.0) / a0;       shelf.a2 = (1.0 - K / q + K * K) / a0;
        }
        {
            const double f0 = 38.13547087602444, q = 0.5003270373238773;
            const double K = std::tan (fx::pi * f0 / sr), a0 = 1.0 + K / q + K * K;
            hp.b0 = 1.0; hp.b1 = -2.0; hp.b2 = 1.0;
            hp.a1 = 2.0 * (K * K - 1.0) / a0; hp.a2 = (1.0 - K / q + K * K) / a0;
        }
        for (auto& f : k) { f[0] = shelf; f[1] = hp; }
        blockLen = juce::jmax (1, (int) std::round (sr * 0.1));
        rmsCoef = 1.0 - std::exp (-1.0 / (0.3 * sr));
    }

    // Solo desde el hilo de mensajes con el audio parado o antes de medir: vacía la integrada
    void resetIntegrated()
    {
        for (auto& c : hist) c.store (0, std::memory_order_relaxed);
        for (auto& b : ring) b = 0.0;
        filled = 0; acc = 0.0; accN = 0;
        maxPeak.store (0.0f);
    }

    void process (const float* l, const float* r, int n) noexcept
    {
        float pk = 0.0f;
        for (int i = 0; i < n; ++i)
        {
            const float a = l[i], b = r != nullptr ? r[i] : a;
            pk = std::max (pk, std::max (std::abs (a), std::abs (b)));
            rms += rmsCoef * (0.5 * ((double) a * a + (double) b * b) - rms);
            const double ka = k[0][1].process (k[0][0].process (a)), kb = k[1][1].process (k[1][0].process (b));
            acc += ka * ka + (r != nullptr ? kb * kb : 0.0);   // mono: un solo canal (G = 1)
            if (++accN >= blockLen)
                closeBlock();
        }
        peak.store (std::max (peak.load (std::memory_order_relaxed), pk), std::memory_order_relaxed);
        maxPeak.store (std::max (maxPeak.load (std::memory_order_relaxed), pk), std::memory_order_relaxed);
        rmsDb.store ((float) (10.0 * std::log10 (rms + 1e-12)), std::memory_order_relaxed);
    }

    float readPeakDb() { return fx::gainToDb (peak.exchange (0.0f)); }     // desde la última lectura
    float maxPeakDb() const { return fx::gainToDb (maxPeak.load()); }     // desde el último reinicio
    float momentary() const { return momentaryLufs.load (std::memory_order_relaxed); }
    float shortTerm() const { return shortLufs.load (std::memory_order_relaxed); }
    float rmsValue() const { return rmsDb.load (std::memory_order_relaxed); }

    // Integrada con las dos puertas (hilo de mensajes)
    float integrated() const
    {
        double e = 0.0; uint64_t c = 0;
        std::array<uint32_t, (size_t) bins> h {};
        for (int i = 0; i < bins; ++i) { h[(size_t) i] = hist[(size_t) i].load (std::memory_order_relaxed); c += h[(size_t) i]; e += h[(size_t) i] * toEnergy (i); }
        if (c == 0) return -100.0f;
        const float gate = toLufs (e / (double) c) - 10.0f;
        e = 0.0; c = 0;
        for (int i = 0; i < bins; ++i)
            if (binLufs (i) >= gate) { c += h[(size_t) i]; e += h[(size_t) i] * toEnergy (i); }
        return c == 0 ? -100.0f : toLufs (e / (double) c);
    }

private:
    static float toLufs (double ms) { return (float) (-0.691 + 10.0 * std::log10 (ms + 1e-20)); }
    static float binLufs (int i) { return floorDb + i * step; }
    static double toEnergy (int i) { return std::pow (10.0, (binLufs (i) + 0.691) / 10.0); }

    void closeBlock() noexcept
    {
        ring[(size_t) head] = acc / accN;
        head = (head + 1) % 30;
        filled = std::min (filled + 1, 30);
        acc = 0.0; accN = 0;
        auto mean = [this] (int count)
        {
            double s = 0.0;
            for (int j = 1; j <= count; ++j) s += ring[(size_t) ((head - j + 30) % 30)];
            return s / count;
        };
        if (filled >= 4)
        {
            const float m = toLufs (mean (4));
            momentaryLufs.store (m, std::memory_order_relaxed);
            if (m >= floorDb)
            {
                const int b = std::clamp ((int) std::round ((m - floorDb) / step), 0, bins - 1);
                hist[(size_t) b].fetch_add (1, std::memory_order_relaxed);
            }
        }
        shortLufs.store (filled >= 30 ? toLufs (mean (30)) : -100.0f, std::memory_order_relaxed);
    }

    double sr = 48000.0, rmsCoef = 0.0, rms = 0.0, acc = 0.0;
    int blockLen = 4800, accN = 0, head = 0, filled = 0;
    std::array<std::array<fx::Biquad, 2>, 2> k;   // [canal][etapa]
    std::array<double, 30> ring {};
    std::array<std::atomic<uint32_t>, (size_t) bins> hist {};
    std::atomic<float> peak { 0.0f }, maxPeak { 0.0f }, rmsDb { -100.0f }, momentaryLufs { -100.0f }, shortLufs { -100.0f };
};

//==============================================================================
// Plugin invisible al final de cada pista (después del fader) y del master: solo mide
class AfoMeterPlugin : public te::Plugin
{
public:
    AfoMeterPlugin (te::PluginCreationInfo info) : te::Plugin (info) {}
    ~AfoMeterPlugin() override { notifyListenersOfDeletion(); }

    static const char* getPluginName() { return "AllForOne Meter"; }
    static constexpr const char* xmlTypeName = "afoMeter";
    juce::String getName() const override              { return getPluginName(); }
    juce::String getPluginType() override              { return xmlTypeName; }
    juce::String getShortName (int) override           { return "AFO Meter"; }
    juce::String getSelectableDescription() override   { return getName(); }
    int getNumOutputChannelsGivenInputs (int n) override { return juce::jmax (2, n); }
    bool takesAudioInput() override                    { return true; }
    bool canBeAddedToClip() override                   { return false; }
    bool canBeAddedToRack() override                   { return false; }

    // No se vacía al reinicializar (Tracktion reinicia plugins al renderizar o cambiar el grafo)
    void initialise (const te::PluginInitialisationInfo& i) override { meter.prepare (i.sampleRate); }
    void deinitialise() override {}

    void applyToBuffer (const te::PluginRenderContext& fc) override
    {
        if (fc.destBuffer == nullptr || fc.bufferNumSamples == 0 || fc.destBuffer->getNumChannels() == 0)
            return;
        auto& b = *fc.destBuffer;
        meter.process (b.getReadPointer (0, fc.bufferStartSample),
                       b.getNumChannels() > 1 ? b.getReadPointer (1, fc.bufferStartSample) : nullptr, fc.bufferNumSamples);
    }

    LoudnessMeter meter;
};

} // namespace afo

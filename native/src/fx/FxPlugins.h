// AllForOne — biblioteca nativa de efectos (Hito 1 de docs/BIBLIOTECA_NATIVA.md).
//
// Cada efecto es un plugin de Tracktion con parámetros automatizables (ParameterWithStateValue: se
// guardan en el Edit y admiten automatización). FxBase reparte el bloque en tramos de 32 muestras,
// suaviza los parámetros (sin chasquidos), mide entrada/salida y copia la salida al analizador.
// Solo lo incluye AfoEngine.cpp.
#pragma once

#include "FxDsp.h"

#include <memory>
#include <vector>

namespace afo::fx
{
namespace te = tracktion;

//==============================================================================
struct ParamDesc
{
    const char* id;
    const char* name;
    float min, max, def;
    const char* unit;
    float centre = 0.0f;              // valor en el centro de la perilla (0 = lineal)
    const char* choices = nullptr;    // opciones separadas por «|» (parámetro discreto 0..n−1)
    const char* help = "";            // qué cambia (tooltip)
};

struct FxDesc
{
    const char* key;                  // identificador estable para la interfaz y los presets
    const char* af;                   // ID de la especificación (AF-01..AF-96)
    const char* name;
    const char* family;
    const char* summary;
    std::vector<ParamDesc> params;
    const char* meters;               // nombres de las medidas propias, separados por «|»
};

//==============================================================================
class FxBase : public te::Plugin
{
public:
    FxBase (te::PluginCreationInfo info, const FxDesc& d) : te::Plugin (info), desc (d)
    {
        for (auto& p : desc.params)
        {
            juce::NormalisableRange<float> range (p.min, p.max, p.choices != nullptr ? 1.0f : 0.0f);
            if (p.centre > p.min && p.centre < p.max)
                range.setSkewForCentre (p.centre);
            params.emplace_back (*this, p.id, juce::Identifier (p.id), juce::String::fromUTF8 (p.name), p.def, range);
        }
        smooth.resize (params.size());
        for (size_t i = 0; i < params.size(); ++i)
            smooth[i] = params[i].getCurrentValue();
    }

    ~FxBase() override
    {
        notifyListenersOfDeletion();
        for (auto& p : params) p.reset();
    }

    juce::String getName() const override              { return juce::String::fromUTF8 (desc.name); }
    juce::String getShortName (int) override           { return getName(); }
    juce::String getSelectableDescription() override   { return getName(); }
    int getNumOutputChannelsGivenInputs (int n) override { return juce::jmax (2, n); }
    bool takesAudioInput() override                    { return true; }

    void restorePluginStateFromValueTree (const juce::ValueTree& v) override
    {
        for (auto& p : params) p.setFromValueTree (v);
    }

    void initialise (const te::PluginInitialisationInfo& info) override
    {
        sampleRate = info.sampleRate;
        for (size_t i = 0; i < params.size(); ++i)
            smooth[i] = params[i].getCurrentValue();
        smoothCoef = 1.0f - (float) std::exp (-(double) chunk / (0.03 * sampleRate));
        prepareFx (sampleRate);
    }
    void deinitialise() override {}
    void reset() override { resetFx(); }

    void applyToBuffer (const te::PluginRenderContext& fc) override
    {
        if (fc.destBuffer == nullptr || fc.bufferNumSamples == 0)
            return;
        const juce::ScopedNoDenormals noDenormals;     // colas de filtros y reverbs: sin números subnormales
        auto& buf = *fc.destBuffer;
        const int n = fc.bufferNumSamples, start = fc.bufferStartSample;
        const int chans = buf.getNumChannels();
        if (chans == 0)
            return;
        float* l = buf.getWritePointer (0, start);
        float* r = chans > 1 ? buf.getWritePointer (1, start) : nullptr;

        inPeak.store (juce::jmax (inPeak.load(), peakOf (l, r, n)));
        for (int off = 0; off < n; off += chunk)
        {
            const int m = juce::jmin (chunk, n - off);
            for (size_t i = 0; i < params.size(); ++i)
            {
                const float target = params[i].getCurrentValue();
                smooth[i] = desc.params[i].choices != nullptr ? target : smooth[i] + smoothCoef * (target - smooth[i]);
            }
            if (r != nullptr)
                processFx (l + off, r + off, m);
            else
            {
                std::array<float, chunk> right {};
                std::copy (l + off, l + off + m, right.begin());
                processFx (l + off, right.data(), m);
                for (int i = 0; i < m; ++i) l[off + i] = 0.5f * (l[off + i] + right[(size_t) i]);
            }
        }
        outPeak.store (juce::jmax (outPeak.load(), peakOf (l, r, n)));
        if (! ownsScope)
            scope.push (l, r, n);
    }

    // Medidas para la interfaz (hilo de mensajes): pico de entrada y salida en dBFS + las propias
    std::vector<float> readMeters()
    {
        std::vector<float> m { gainToDb (inPeak.exchange (0.0f)), gainToDb (outPeak.exchange (0.0f)) };
        for (auto v : extraMeters()) m.push_back (v);
        return m;
    }

    // Espectro de la salida en `bands` bandas logarítmicas de 20 Hz a 20 kHz (dBFS de una senoidal)
    std::vector<float> spectrum (int bands, float slopeDbPerOct = 0.0f, float averaging = 0.0f)
    {
        constexpr int order = 12, size = 1 << order;
        if (fft == nullptr) { fft = std::make_unique<juce::dsp::FFT> (order); fftData.assign (2 * size, 0.0f); }
        scope.latest (fftData.data(), size);
        std::fill (fftData.begin() + size, fftData.end(), 0.0f);
        for (int i = 0; i < size; ++i)
            fftData[(size_t) i] *= 0.5f - 0.5f * (float) std::cos (2 * pi * i / (size - 1));
        fft->performFrequencyOnlyForwardTransform (fftData.data());
        bands = juce::jlimit (8, 256, bands);
        if ((int) avg.size() != bands) avg.assign ((size_t) bands, -120.0f);
        std::vector<float> out ((size_t) bands);
        const double binHz = sampleRate / size;
        for (int b = 0; b < bands; ++b)
        {
            const double f0 = 20.0 * std::pow (1000.0, (double) b / bands), f1 = 20.0 * std::pow (1000.0, (double) (b + 1) / bands);
            int k0 = (int) std::floor (f0 / binHz), k1 = (int) std::ceil (f1 / binHz);
            k0 = juce::jlimit (1, size / 2 - 1, k0); k1 = juce::jlimit (k0 + 1, size / 2, k1);
            float mag = 0.0f;
            for (int k = k0; k < k1; ++k) mag = juce::jmax (mag, fftData[(size_t) k]);
            float db = gainToDb (mag * 4.0f / size) + slopeDbPerOct * (float) std::log2 (std::sqrt (f0 * f1) / 1000.0);
            db = juce::jmax (-120.0f, db);
            avg[(size_t) b] = averaging * avg[(size_t) b] + (1.0f - averaging) * db;
            out[(size_t) b] = avg[(size_t) b];
        }
        return out;
    }

    float value (const juce::String& id) const
    {
        for (size_t i = 0; i < params.size(); ++i)
            if (id == desc.params[i].id) return params[i].getCurrentValue();
        return 0.0f;
    }
    // Parámetro de Tracktion (automatizable) por su id, o nullptr
    te::AutomatableParameter* parameter (const juce::String& id)
    {
        for (size_t i = 0; i < params.size(); ++i)
            if (id == desc.params[i].id) return params[i].parameter.get();
        return nullptr;
    }
    // Valor fijo guardado en el estado del plugin (el que manda cuando no hay automatización)
    float storedValue (const juce::String& id)
    {
        for (size_t i = 0; i < params.size(); ++i)
            if (id == desc.params[i].id) return params[i].getCachedValue().get();
        return 0.0f;
    }
    bool setValue (const juce::String& id, float v)
    {
        for (size_t i = 0; i < params.size(); ++i)
            if (id == desc.params[i].id)
            {
                params[i].setParameter (juce::jlimit (desc.params[i].min, desc.params[i].max, v), juce::sendNotification);
                return true;
            }
        return false;
    }

    const FxDesc& desc;
    std::atomic<float> bpm { 120.0f };          // tempo del proyecto (lo actualiza el motor)

protected:
    virtual void prepareFx (double) {}
    virtual void resetFx() {}
    virtual void processFx (float* l, float* r, int n) = 0;
    virtual std::vector<float> extraMeters() { return {}; }

    float p (int i) const      { return smooth[(size_t) i]; }                       // suavizado
    int choice (int i) const   { return juce::roundToInt (smooth[(size_t) i]); }
    float target (int i) const { return params[(size_t) i].getCurrentValue(); }    // sin suavizar (hilo de mensajes)

    static float peakOf (const float* l, const float* r, int n)
    {
        float m = 0.0f;
        for (int i = 0; i < n; ++i) m = juce::jmax (m, std::abs (l[i]), r != nullptr ? std::abs (r[i]) : 0.0f);
        return m;
    }

    static constexpr int chunk = 32;
    double sampleRate = 48000.0;
    ScopeFifo scope;
    bool ownsScope = false;

private:
    std::vector<te::ParameterWithStateValue> params;
    std::vector<float> smooth;
    float smoothCoef = 0.1f;
    std::atomic<float> inPeak { 0.0f }, outPeak { 0.0f };
    std::unique_ptr<juce::dsp::FFT> fft;
    std::vector<float> fftData, avg;
};

#define AFO_FX_TYPE(xml, descFn) \
    static constexpr const char* xmlTypeName = xml; \
    static const char* getPluginName() { return descFn().name; } \
    juce::String getPluginType() override { return xmlTypeName; }

//==============================================================================
// Descripciones (nombres y unidades en español, como el resto de la interfaz)
inline const FxDesc& gainDesc()
{
    static const FxDesc d { "gain", "AF-01", "AFO Gain", "Utilidades y señal",
        "Etapa transparente de nivel: ganancia, panorama, polaridad y mono.",
        { { "input", "Entrada", -36, 36, 0, "dB", 0, nullptr, "Sube o baja lo que entra (gain staging)" },
          { "pan", "Pan", -100, 100, 0, "%", 0, nullptr, "Equilibrio izquierda/derecha (atenúa el lado contrario)" },
          { "polarity", "Polaridad", 0, 1, 0, "", 0, "Normal|Invertida", "Invierte 180° para comprobar cancelaciones" },
          { "mono", "Mono", 0, 1, 0, "", 0, "Estéreo|Mono", "Suma L+R para comprobar la compatibilidad mono" },
          { "output", "Salida", -36, 36, 0, "dB", 0, nullptr, "Nivel final" } },
        "" };
    return d;
}

inline const FxDesc& eqDesc()
{
    static const FxDesc d { "eq", "AF-07", "AFO Parametric EQ", "Ecualización y resonancias",
        "Ecualizador de 6 bandas: paso alto, grave, dos medios, agudo y paso bajo.",
        { { "hpf", "Paso alto", 20, 1000, 20, "Hz", 120, nullptr, "Corta graves por debajo (20 Hz = apagado)" },
          { "hpfSlope", "Pendiente", 0, 1, 0, "", 0, "12 dB/oct|24 dB/oct", "Pendiente del paso alto" },
          { "lowFreq", "Grave Hz", 30, 500, 100, "Hz", 120, nullptr, "Frecuencia del estante de graves" },
          { "lowGain", "Grave", -18, 18, 0, "dB", 0, nullptr, "Suma o resta graves" },
          { "mid1Freq", "Medio 1 Hz", 40, 16000, 400, "Hz", 1000, nullptr, "Centro de la primera campana" },
          { "mid1Gain", "Medio 1", -18, 18, 0, "dB", 0, nullptr, "Ganancia de la primera campana" },
          { "mid1Q", "Q 1", 0.1f, 10, 1, "", 1, nullptr, "Anchura (alto = estrecho)" },
          { "mid2Freq", "Medio 2 Hz", 40, 16000, 2500, "Hz", 1000, nullptr, "Centro de la segunda campana" },
          { "mid2Gain", "Medio 2", -18, 18, 0, "dB", 0, nullptr, "Ganancia de la segunda campana" },
          { "mid2Q", "Q 2", 0.1f, 10, 1, "", 1, nullptr, "Anchura (alto = estrecho)" },
          { "highFreq", "Agudo Hz", 1500, 18000, 8000, "Hz", 6000, nullptr, "Frecuencia del estante de agudos" },
          { "highGain", "Agudo", -18, 18, 0, "dB", 0, nullptr, "Suma o resta agudos" },
          { "lpf", "Paso bajo", 1000, 20000, 20000, "Hz", 6000, nullptr, "Corta agudos por encima (20 kHz = apagado)" },
          { "output", "Salida", -24, 24, 0, "dB", 0, nullptr, "Compensa el nivel" } },
        "curva" };
    return d;
}

inline const FxDesc& compDesc()
{
    static const FxDesc d { "compressor", "AF-13", "AFO Compressor", "Dinámica y transitorios",
        "Compresión precisa con rodilla, detector Peak/RMS y mezcla paralela.",
        { { "threshold", "Umbral", -60, 0, -18, "dB", 0, nullptr, "Nivel a partir del que actúa" },
          { "ratio", "Ratio", 1, 20, 4, ":1", 4, nullptr, "Cuánto reduce por encima del umbral" },
          { "attack", "Ataque", 0.1f, 100, 15, "ms", 10, nullptr, "Cuánto transitorio deja pasar" },
          { "release", "Liberación", 10, 1000, 120, "ms", 150, nullptr, "Cuánto tarda en soltar" },
          { "knee", "Rodilla", 0, 24, 6, "dB", 0, nullptr, "Transición suave o brusca cerca del umbral" },
          { "detector", "Detector", 0, 1, 0, "", 0, "Peak|RMS", "Pico (rápido) o RMS (promedio)" },
          { "makeup", "Compensación", 0, 24, 0, "dB", 0, nullptr, "Recupera el nivel perdido" },
          { "mix", "Mezcla", 0, 100, 100, "%", 0, nullptr, "Compresión paralela (0 = seco)" } },
        "reducción dB" };
    return d;
}

inline const FxDesc& gateDesc()
{
    static const FxDesc d { "gate", "AF-18", "AFO Gate", "Dinámica y transitorios",
        "Puerta de ruido con histéresis y mantenimiento.",
        { { "threshold", "Umbral", -80, 0, -40, "dB", 0, nullptr, "Nivel de apertura" },
          { "range", "Rango", -80, 0, -60, "dB", 0, nullptr, "Atenuación al cerrar" },
          { "attack", "Ataque", 0.05f, 50, 0.5f, "ms", 5, nullptr, "Velocidad de apertura" },
          { "hold", "Mantener", 0, 500, 50, "ms", 80, nullptr, "Tiempo abierta tras caer bajo el umbral" },
          { "release", "Cierre", 5, 2000, 150, "ms", 200, nullptr, "Velocidad de cierre" },
          { "hysteresis", "Histéresis", 0, 12, 4, "dB", 0, nullptr, "Separa apertura y cierre (evita temblores)" } },
        "reducción dB|abierta" };
    return d;
}

inline const FxDesc& satDesc()
{
    static const FxDesc d { "saturator", "AF-26", "AFO Saturator", "Saturación y color",
        "Armónicos con sobremuestreo ×4; mismo volumen en señal baja para comparar con justicia.",
        { { "drive", "Drive", 0, 36, 12, "dB", 0, nullptr, "Cuánto empuja la etapa no lineal" },
          { "character", "Carácter", 0, 2, 0, "", 0, "Tubo|Cinta|Recorte", "Curva de transferencia" },
          { "tone", "Tono", -100, 100, 0, "%", 0, nullptr, "Inclina hacia graves (−) o agudos (+)" },
          { "bias", "Bias", 0, 100, 0, "%", 0, nullptr, "Asimetría: añade armónicos pares" },
          { "mix", "Mezcla", 0, 100, 100, "%", 0, nullptr, "Saturación paralela" },
          { "output", "Salida", -24, 12, 0, "dB", 0, nullptr, "Nivel final" } },
        "" };
    return d;
}

inline const FxDesc& delayDesc()
{
    static const FxDesc d { "delay", "AF-41", "AFO Digital Delay", "Delays y ecos",
        "Ecos precisos con sincronía al tempo, ping-pong, filtros y ducking.",
        { { "time", "Tiempo", 1, 2000, 375, "ms", 300, nullptr, "Retardo libre (si Sincronía = Libre)" },
          { "sync", "Sincronía", 0, 6, 3, "", 0, "Libre|1/2|1/4|1/8 con puntillo|1/8|1/16|1/4 tresillo", "Sigue el tempo del proyecto" },
          { "feedback", "Repeticiones", 0, 95, 35, "%", 0, nullptr, "Cuánto vuelve a entrar cada eco" },
          { "pingpong", "Ping-pong", 0, 1, 0, "", 0, "No|Sí", "Alterna los ecos entre L y R" },
          { "hp", "Paso alto", 20, 2000, 120, "Hz", 300, nullptr, "Quita graves a los ecos" },
          { "lp", "Paso bajo", 1000, 20000, 9000, "Hz", 5000, nullptr, "Oscurece los ecos" },
          { "ducking", "Ducking", 0, 100, 0, "%", 0, nullptr, "Baja los ecos mientras suena la señal seca" },
          { "mix", "Mezcla", 0, 100, 30, "%", 0, nullptr, "Cantidad de eco" } },
        "tiempo ms" };
    return d;
}

inline const FxDesc& spaceDesc()
{
    static const FxDesc d { "space", "AF-35", "AFO Space", "Reverberación y espacios",
        "Reverb algorítmica (red de 8 retardos) con RT60 exacto, reflexiones tempranas y anchura.",
        { { "mode", "Modo", 0, 3, 0, "", 0, "Sala|Hall|Placa|Cámara", "Topología: reflexiones, difusión y brillo" },
          { "size", "Tamaño", 0, 100, 50, "%", 0, nullptr, "Tamaño aparente del espacio" },
          { "predelay", "Pre-delay", 0, 250, 20, "ms", 50, nullptr, "Separa la voz seca del comienzo de la cola" },
          { "decay", "Caída", 0.2f, 20, 2.2f, "s", 2.5f, nullptr, "RT60: tiempo en caer 60 dB" },
          { "diffusion", "Difusión", 0, 100, 70, "%", 0, nullptr, "Densidad de reflexiones" },
          { "damping", "Amortiguar", 1000, 20000, 7000, "Hz", 5000, nullptr, "Absorción de agudos en la cola" },
          { "lowcut", "Corte grave", 20, 1000, 120, "Hz", 200, nullptr, "Quita graves a la reverb" },
          { "early", "Tempranas", 0, 100, 40, "%", 0, nullptr, "Nivel de las primeras reflexiones" },
          { "width", "Anchura", 0, 100, 100, "%", 0, nullptr, "Apertura estéreo de la cola" },
          { "mix", "Mezcla", 0, 100, 25, "%", 0, nullptr, "Seco/húmedo" } },
        "" };
    return d;
}

inline const FxDesc& analyzerDesc()
{
    static const FxDesc d { "analyzer", "AF-76", "AFO Spectrum Analyzer", "Medición y análisis",
        "Espectro FFT de 4096 puntos (ventana Hann); no modifica el audio.",
        { { "averaging", "Promedio", 0, 95, 70, "%", 0, nullptr, "Suaviza la lectura" },
          { "slope", "Pendiente", 0, 2, 1, "", 0, "0 dB/oct|3 dB/oct|4,5 dB/oct", "Compensación visual (3 dB/oct ≈ ruido rosa plano)" },
          { "channel", "Canal", 0, 4, 0, "", 0, "L+R|L|R|Mid|Side", "Señal analizada" } },
        "" };
    return d;
}

inline const FxDesc& stripDesc()
{
    static const FxDesc d { "strip", "AF-02", "AFO Channel Strip", "Racks y cadenas",
        "Canal completo: paso alto → puerta → EQ de 3 bandas → compresor → color → salida.",
        { { "hpf", "Paso alto", 20, 400, 20, "Hz", 100, nullptr, "Quita subgraves (20 Hz = apagado)" },
          { "gate", "Puerta", -80, 0, -80, "dB", 0, nullptr, "Umbral de la puerta (−80 = apagada)" },
          { "lowGain", "Grave", -15, 15, 0, "dB", 0, nullptr, "Estante a 100 Hz" },
          { "midFreq", "Medio Hz", 200, 5000, 1000, "Hz", 1000, nullptr, "Centro de la campana de medios" },
          { "midGain", "Medio", -15, 15, 0, "dB", 0, nullptr, "Ganancia de medios" },
          { "highGain", "Agudo", -15, 15, 0, "dB", 0, nullptr, "Estante a 8 kHz" },
          { "compThr", "Comp. umbral", -50, 0, 0, "dB", 0, nullptr, "Umbral del compresor (0 = sin compresión)" },
          { "ratio", "Ratio", 1, 10, 3, ":1", 3, nullptr, "Intensidad del compresor" },
          { "attack", "Ataque", 0.5f, 100, 10, "ms", 10, nullptr, "Ataque del compresor" },
          { "release", "Liberación", 20, 1000, 150, "ms", 150, nullptr, "Liberación del compresor" },
          { "drive", "Color", 0, 100, 0, "%", 0, nullptr, "Saturación suave" },
          { "output", "Salida", -24, 24, 0, "dB", 0, nullptr, "Compensa el nivel" } },
        "reducción dB|puerta abierta" };
    return d;
}

//==============================================================================
class GainFx : public FxBase
{
public:
    GainFx (te::PluginCreationInfo i) : FxBase (i, gainDesc()) {}
    AFO_FX_TYPE ("afoFxGain", gainDesc)
protected:
    void processFx (float* l, float* r, int n) override
    {
        const float g = dbToGain (p (0) + p (4)) * (1.0f - 2.0f * p (2));
        const float pan = p (1) / 100.0f, mono = p (3);
        const float gl = g * juce::jmin (1.0f, 1.0f - pan), gr = g * juce::jmin (1.0f, 1.0f + pan);
        for (int i = 0; i < n; ++i)
        {
            const float m = 0.5f * (l[i] + r[i]);
            l[i] = gl * (l[i] + mono * (m - l[i]));
            r[i] = gr * (r[i] + mono * (m - r[i]));
        }
    }
};

//==============================================================================
class EqFx : public FxBase
{
public:
    EqFx (te::PluginCreationInfo i) : FxBase (i, eqDesc()) {}
    AFO_FX_TYPE ("afoFxEq", eqDesc)

    // Respuesta en frecuencia real de los filtros configurados (dB en 64 puntos de 20 Hz a 20 kHz)
    std::vector<float> extraMeters() override
    {
        std::array<Biquad, 8> f;
        std::array<float, 14> v {};
        for (int i = 0; i < 14; ++i) v[(size_t) i] = target (i);
        const int used = design (f, v.data(), sampleRate);
        std::vector<float> curve (64);
        for (int k = 0; k < 64; ++k)
        {
            const double hz = 20.0 * std::pow (1000.0, k / 63.0);
            double db = v[13];
            for (int j = 0; j < used; ++j) db += f[(size_t) j].magnitudeDb (hz, sampleRate);
            curve[(size_t) k] = (float) db;
        }
        return curve;
    }

protected:
    void prepareFx (double) override { last.fill (-1.0e9f); for (auto& b : bank) b.reset(); }
    void resetFx() override          { for (auto& b : bank) b.reset(); }

    void processFx (float* l, float* r, int n) override
    {
        std::array<float, 14> v {};
        bool changed = false;
        for (int i = 0; i < 14; ++i) { v[(size_t) i] = p (i); changed = changed || v[(size_t) i] != last[(size_t) i]; }
        if (changed)
        {
            std::array<Biquad, 8> f;
            active = design (f, v.data(), sampleRate);
            for (int j = 0; j < active; ++j)        // conserva el estado: solo cambian los coeficientes
            {
                bank[(size_t) j].b0 = f[(size_t) j].b0; bank[(size_t) j].b1 = f[(size_t) j].b1; bank[(size_t) j].b2 = f[(size_t) j].b2;
                bank[(size_t) j].a1 = f[(size_t) j].a1; bank[(size_t) j].a2 = f[(size_t) j].a2;
            }
            last = v;
        }
        const float g = dbToGain (v[13]);
        for (int i = 0; i < n; ++i)
        {
            float a = l[i], b = r[i];
            for (int j = 0; j < active; ++j) { a = bank[(size_t) j].process (a, 0); b = bank[(size_t) j].process (b, 1); }
            l[i] = a * g; r[i] = b * g;
        }
    }

private:
    // Orden fijo de las ranuras: el estado de cada filtro no salta al encender o apagar el paso alto/bajo
    static int design (std::array<Biquad, 8>& f, const float* v, double sr)
    {
        using T = Biquad::Type;
        const bool hp = v[0] > 20.5f, hp24 = v[1] > 0.5f, lp = v[12] < 19900.0f;
        f[0].set (T::highpass, hp ? v[0] : 5.0, 0.7071, 0, sr);
        f[1].set (T::highpass, hp && hp24 ? v[0] : 5.0, 0.7071, 0, sr);
        f[2].set (T::lowShelf, v[2], 0.7071, v[3], sr);
        f[3].set (T::bell, v[4], v[6], v[5], sr);
        f[4].set (T::bell, v[7], v[9], v[8], sr);
        f[5].set (T::highShelf, v[10], 0.7071, v[11], sr);
        f[6].set (T::lowpass, lp ? v[12] : sr * 0.49, 0.7071, 0, sr);
        if (! lp) { f[6].b0 = 1; f[6].b1 = f[6].b2 = f[6].a1 = f[6].a2 = 0; }
        if (! hp)       { f[0].b0 = 1; f[0].b1 = f[0].b2 = f[0].a1 = f[0].a2 = 0; }
        if (! (hp && hp24)) { f[1].b0 = 1; f[1].b1 = f[1].b2 = f[1].a1 = f[1].a2 = 0; }
        return 7;
    }

    std::array<Biquad, 8> bank;
    std::array<float, 14> last {};
    int active = 0;
};

//==============================================================================
class CompressorFx : public FxBase
{
public:
    CompressorFx (te::PluginCreationInfo i) : FxBase (i, compDesc()) {}
    AFO_FX_TYPE ("afoFxCompressor", compDesc)
    std::vector<float> extraMeters() override { return { grMin.exchange (0.0f) }; }
protected:
    void prepareFx (double sr) override { comp.prepare (sr); }
    void resetFx() override { comp.reset(); }
    void processFx (float* l, float* r, int n) override
    {
        const float thr = p (0), ratio = p (1), att = p (2), rel = p (3), knee = p (4), makeup = dbToGain (p (6)), mix = p (7) / 100.0f;
        const bool rms = choice (5) == 1;
        for (int i = 0; i < n; ++i)
        {
            const float g = comp.next (l[i], r[i], thr, ratio, knee, att, rel, rms) * makeup;
            l[i] *= (1.0f - mix) + mix * g;
            r[i] *= (1.0f - mix) + mix * g;
        }
        grMin.store (juce::jmin (grMin.load(), comp.grDb));
    }
private:
    Compressor comp;
    std::atomic<float> grMin { 0.0f };
};

//==============================================================================
class GateFx : public FxBase
{
public:
    GateFx (te::PluginCreationInfo i) : FxBase (i, gateDesc()) {}
    AFO_FX_TYPE ("afoFxGate", gateDesc)
    std::vector<float> extraMeters() override { return { gainToDb (gMin.exchange (1.0f)), gate.open ? 1.0f : 0.0f }; }
protected:
    void prepareFx (double sr) override { gate.prepare (sr); }
    void resetFx() override { gate.reset(); }
    void processFx (float* l, float* r, int n) override
    {
        float lo = 1.0f;
        for (int i = 0; i < n; ++i)
        {
            const float g = gate.next (l[i], r[i], p (0), p (1), p (2), p (3), p (4), p (5));
            l[i] *= g; r[i] *= g; lo = juce::jmin (lo, g);
        }
        gMin.store (juce::jmin (gMin.load(), lo));
    }
private:
    Gate gate;
    std::atomic<float> gMin { 1.0f };
};

//==============================================================================
// Tilt EQ compartido (Saturator y master): estantes a 250 Hz y 4 kHz en sentidos opuestos
struct Tilt
{
    Biquad lo, hi;
    float last = 1.0e9f;
    void set (float amount, double sr)          // amount −1..1 → ±6 dB
    {
        if (amount == last) return;
        last = amount;
        Biquad a, b;
        a.set (Biquad::Type::lowShelf, 250, 0.7071, -6.0 * amount, sr);
        b.set (Biquad::Type::highShelf, 4000, 0.7071, 6.0 * amount, sr);
        lo.b0 = a.b0; lo.b1 = a.b1; lo.b2 = a.b2; lo.a1 = a.a1; lo.a2 = a.a2;
        hi.b0 = b.b0; hi.b1 = b.b1; hi.b2 = b.b2; hi.a1 = b.a1; hi.a2 = b.a2;
    }
    float process (float x, int ch) noexcept { return hi.process (lo.process (x, ch), ch); }
};

class SaturatorFx : public FxBase
{
public:
    SaturatorFx (te::PluginCreationInfo i) : FxBase (i, satDesc())
    {
        // La latencia del sobremuestreo no depende de la frecuencia: se conoce antes de initialise().
        // Es fraccional y Tracktion compensa muestras enteras: la parte que falta se añade a la señal
        // procesada (retardo fraccional), así seco, procesado y resto de pistas quedan alineados.
        os = std::make_unique<juce::dsp::Oversampling<float>> (2, 2, juce::dsp::Oversampling<float>::filterHalfBandPolyphaseIIR, true, false);
        const float osLatency = os->getLatencyInSamples();
        latency = std::ceil (osLatency) + 1.0f;
        wetDelay = latency - osLatency;                // entre 1 y 2 muestras (rango útil de Lagrange)
    }
    AFO_FX_TYPE ("afoFxSaturator", satDesc)
    double getLatencySeconds() override { return latency / sampleRate; }

protected:
    void prepareFx (double sr) override
    {
        os->initProcessing ((size_t) chunk);
        for (auto& d : dry) d.prepare (64);
        for (auto& d : wet) d.prepare (16);
        dc.set (Biquad::Type::highpass, 10, 0.7071, 0, sr);
        dc.reset(); tilt.last = 1.0e9f; tilt.set (0, sr); tilt.lo.reset(); tilt.hi.reset();
    }
    void resetFx() override { if (os) os->reset(); for (auto& d : dry) d.clear(); for (auto& d : wet) d.clear(); dc.reset(); tilt.lo.reset(); tilt.hi.reset(); }

    static float shape (int c, float x) noexcept
    {
        if (c == 0) return std::tanh (x);
        if (c == 1) return x / std::sqrt (1.0f + x * x);
        return juce::jlimit (-1.0f, 1.0f, x);
    }
    static float slope (int c, float b) noexcept
    {
        if (c == 0) { const float t = std::tanh (b); return 1.0f - t * t; }
        if (c == 1) return 1.0f / std::pow (1.0f + b * b, 1.5f);
        return 1.0f;
    }

    void processFx (float* l, float* r, int n) override
    {
        const int c = choice (1);
        const float g = dbToGain (p (0)), bias = 0.5f * p (3) / 100.0f, mix = p (4) / 100.0f, out = dbToGain (p (5));
        const float off = shape (c, bias), norm = 1.0f / (g * juce::jmax (0.05f, slope (c, bias)));
        std::array<float, chunk> dl {}, dr {};
        for (int i = 0; i < n; ++i) { dry[0].push (l[i]); dry[1].push (r[i]); }
        for (int i = 0; i < n; ++i)              // seco retrasado lo mismo que el sobremuestreo
        {
            dl[(size_t) i] = dry[0].readLagrange (latency + (float) (n - i));
            dr[(size_t) i] = dry[1].readLagrange (latency + (float) (n - i));
        }
        float* ch[2] = { l, r };
        juce::dsp::AudioBlock<float> block (ch, 2, (size_t) n);
        auto up = os->processSamplesUp (block);
        for (size_t k = 0; k < up.getNumChannels(); ++k)
        {
            auto* x = up.getChannelPointer (k);
            for (size_t i = 0; i < up.getNumSamples(); ++i)
                x[i] = (shape (c, g * x[i] + bias) - off) * norm;
        }
        os->processSamplesDown (block);
        tilt.set (p (2) / 100.0f, sampleRate);
        for (int i = 0; i < n; ++i)
        {
            wet[0].push (l[i]); wet[1].push (r[i]);
            const float wl = tilt.process (dc.process (wet[0].readLagrange (1.0f + wetDelay), 0), 0);
            const float wr = tilt.process (dc.process (wet[1].readLagrange (1.0f + wetDelay), 1), 1);
            l[i] = out * (dl[(size_t) i] + mix * (wl - dl[(size_t) i]));
            r[i] = out * (dr[(size_t) i] + mix * (wr - dr[(size_t) i]));
        }
    }

private:
    std::unique_ptr<juce::dsp::Oversampling<float>> os;
    float latency = 0.0f, wetDelay = 1.0f;     // latency: entera, la que se informa a Tracktion
    std::array<DelayLine, 2> dry, wet;
    Biquad dc;
    Tilt tilt;
};

//==============================================================================
class DelayFx : public FxBase
{
public:
    DelayFx (te::PluginCreationInfo i) : FxBase (i, delayDesc()) {}
    AFO_FX_TYPE ("afoFxDelay", delayDesc)
    double getTailLength() const override { return 10.0; }
    std::vector<float> extraMeters() override { return { (float) (delaySamples / sampleRate * 1000.0) }; }

    // Tiempo de eco en segundos para unos parámetros dados (Libre o figura al tempo)
    static double echoSeconds (int sync, float timeMs, float bpm)
    {
        static constexpr double beats[] = { 0, 2.0, 1.0, 0.75, 0.5, 0.25, 2.0 / 3.0 };
        return sync <= 0 ? timeMs / 1000.0 : beats[juce::jlimit (1, 6, sync)] * 60.0 / juce::jmax (20.0f, bpm);
    }

protected:
    void prepareFx (double sr) override
    {
        for (auto& d : line) d.prepare ((int) (6.1 * sr));
        delaySamples = echoSeconds (target (1) > 0.5f ? juce::roundToInt (target (1)) : 0, target (0), bpm.load()) * sr;
        resetFx();
    }
    void resetFx() override { for (auto& d : line) d.clear(); for (auto& f : hp) f.reset(); for (auto& f : lp) f.reset(); env = 0.0f; }

    void processFx (float* l, float* r, int n) override
    {
        const double want = juce::jlimit (1.0, 6.0 * sampleRate, echoSeconds (choice (1), p (0), bpm.load()) * sampleRate);
        const float fb = p (2) / 100.0f, mix = p (7) / 100.0f, duck = p (6) / 100.0f;
        const bool ping = choice (3) == 1;
        for (int c = 0; c < 2; ++c)
        {
            hp[(size_t) c].set (Biquad::Type::highpass, p (4), 0.7071, 0, sampleRate);
            lp[(size_t) c].set (Biquad::Type::lowpass, p (5), 0.7071, 0, sampleRate);
        }
        const double glide = 1.0 - std::exp (-1.0 / (0.05 * sampleRate));    // cambios de tiempo sin saltos
        const float up = onePole (5.0f, sampleRate), down = onePole (250.0f, sampleRate);
        for (int i = 0; i < n; ++i)
        {
            delaySamples += glide * (want - delaySamples);
            const float d = (float) delaySamples;
            const float el = lp[0].process (hp[0].process (line[0].read (d), 0), 0);
            const float er = lp[1].process (hp[1].process (line[1].read (d), 0), 0);
            const float inL = l[i], inR = r[i];
            if (ping)
            {
                line[0].push (std::tanh (0.5f * (inL + inR) + fb * er));
                line[1].push (std::tanh (fb * el));
            }
            else
            {
                line[0].push (std::tanh (inL + fb * el));
                line[1].push (std::tanh (inR + fb * er));
            }
            const float x = juce::jmax (std::abs (inL), std::abs (inR));
            env += (x > env ? up : down) * (x - env);
            const float dg = 1.0f - duck * juce::jlimit (0.0f, 1.0f, env * 4.0f);
            l[i] = inL * (1.0f - mix) + el * dg * mix;
            r[i] = inR * (1.0f - mix) + er * dg * mix;
        }
    }

private:
    std::array<DelayLine, 2> line;
    std::array<Biquad, 2> hp, lp;
    double delaySamples = 1000.0;
    float env = 0.0f;
};

//==============================================================================
class SpaceFx : public FxBase
{
public:
    SpaceFx (te::PluginCreationInfo i) : FxBase (i, spaceDesc()) {}
    AFO_FX_TYPE ("afoFxSpace", spaceDesc)
    double getTailLength() const override { return 30.0; }

protected:
    static constexpr std::array<float, 6> tapMs { 7.1f, 12.9f, 19.3f, 27.1f, 37.7f, 49.3f };
    static constexpr std::array<float, 6> tapGain { 0.8f, 0.62f, 0.5f, 0.4f, 0.3f, 0.22f };

    void prepareFx (double sr) override { pre.prepare ((int) (0.45 * sr)); fdn.prepare (sr); resetFx(); }
    void resetFx() override { pre.clear(); fdn.reset(); for (auto& f : low) f.reset(); }

    void processFx (float* l, float* r, int n) override
    {
        static constexpr float earlyMul[] = { 1.0f, 0.5f, 0.0f, 0.8f }, diffAdd[] = { 0.0f, 0.0f, 0.25f, 0.1f }, dampMul[] = { 1.0f, 0.85f, 1.4f, 1.0f };
        const int mode = juce::jlimit (0, 3, choice (0));
        const float size = p (1) / 100.0f, preS = p (2) * 0.001f * (float) sampleRate;
        fdn.set (size, p (3), p (5) * dampMul[mode], juce::jmin (1.0f, p (4) / 100.0f + diffAdd[mode]));
        for (auto& f : low) f.set (Biquad::Type::highpass, p (6), 0.7071, 0, sampleRate);
        const float early = p (7) / 100.0f * earlyMul[mode], width = p (8) / 100.0f, mix = p (9) / 100.0f;
        const float tapScale = (0.5f + size) * 0.001f * (float) sampleRate;
        for (int i = 0; i < n; ++i)
        {
            pre.push (0.5f * (l[i] + r[i]));
            float el = 0.0f, er = 0.0f;
            for (size_t k = 0; k < tapMs.size(); ++k)
                ((k & 1) ? er : el) += tapGain[k] * pre.read (preS + tapMs[k] * tapScale);
            float tl, tr;
            fdn.process (pre.read (juce::jmax (1.0f, preS)), tl, tr);
            float wl = low[0].process (tl + early * el, 0), wr = low[1].process (tr + early * er, 0);
            const float m = 0.5f * (wl + wr), s = 0.5f * (wl - wr) * width;
            wl = m + s; wr = m - s;
            l[i] += mix * (wl - l[i]);
            r[i] += mix * (wr - r[i]);
        }
    }

private:
    DelayLine pre;
    Fdn fdn;
    std::array<Biquad, 2> low;
};

//==============================================================================
class AnalyzerFx : public FxBase
{
public:
    AnalyzerFx (te::PluginCreationInfo i) : FxBase (i, analyzerDesc()) { ownsScope = true; }
    AFO_FX_TYPE ("afoFxAnalyzer", analyzerDesc)
    std::vector<float> extraMeters() override
    {
        static constexpr float slopes[] = { 0.0f, 3.0f, 4.5f };
        return spectrum (64, slopes[juce::jlimit (0, 2, juce::roundToInt (target (1)))], target (0) / 100.0f);
    }
protected:
    void processFx (float* l, float* r, int n) override
    {
        std::array<float, chunk> x {};
        const int ch = choice (2);
        for (int i = 0; i < n; ++i)
            x[(size_t) i] = ch == 1 ? l[i] : ch == 2 ? r[i] : ch == 4 ? 0.5f * (l[i] - r[i]) : 0.5f * (l[i] + r[i]);
        scope.push (x.data(), nullptr, n);
    }
};

//==============================================================================
class StripFx : public FxBase
{
public:
    StripFx (te::PluginCreationInfo i) : FxBase (i, stripDesc()) {}
    AFO_FX_TYPE ("afoFxStrip", stripDesc)
    std::vector<float> extraMeters() override { return { grMin.exchange (0.0f), gate.open ? 1.0f : 0.0f }; }
protected:
    void prepareFx (double sr) override { comp.prepare (sr); gate.prepare (sr); for (auto& b : eq) b.reset(); }
    void resetFx() override { comp.reset(); gate.reset(); for (auto& b : eq) b.reset(); }
    void processFx (float* l, float* r, int n) override
    {
        using T = Biquad::Type;
        const bool hp = p (0) > 20.5f, gateOn = p (1) > -79.5f, compOn = p (6) < -0.05f;
        eq[0].set (T::highpass, hp ? p (0) : 5.0, 0.7071, 0, sampleRate);
        eq[1].set (T::lowShelf, 100, 0.7071, p (2), sampleRate);
        eq[2].set (T::bell, p (3), 0.9, p (4), sampleRate);
        eq[3].set (T::highShelf, 8000, 0.7071, p (5), sampleRate);
        const float k = 1.0f + 4.0f * p (10) / 100.0f, out = dbToGain (p (11));
        for (int i = 0; i < n; ++i)
        {
            float a = l[i], b = r[i];
            if (hp) { a = eq[0].process (a, 0); b = eq[0].process (b, 1); }
            if (gateOn) { const float g = gate.next (a, b, p (1), -60, 0.5f, 30, 150, 4); a *= g; b *= g; }
            for (int j = 1; j < 4; ++j) { a = eq[(size_t) j].process (a, 0); b = eq[(size_t) j].process (b, 1); }
            if (compOn) { const float g = comp.next (a, b, p (6), p (7), 6, p (8), p (9), false); a *= g; b *= g; }
            if (k > 1.001f) { a = std::tanh (k * a) / k; b = std::tanh (k * b) / k; }
            l[i] = a * out; r[i] = b * out;
        }
        grMin.store (juce::jmin (grMin.load(), compOn ? comp.grDb : 0.0f));
    }
private:
    std::array<Biquad, 4> eq;
    Compressor comp;
    Gate gate;
    std::atomic<float> grMin { 0.0f };
};

//==============================================================================
// Registro y creación por clave
struct FxType { const FxDesc& (*desc)(); const char* xml; };
inline const std::vector<FxType>& fxTypes()
{
    static const std::vector<FxType> t {
        { gainDesc, GainFx::xmlTypeName }, { stripDesc, StripFx::xmlTypeName }, { eqDesc, EqFx::xmlTypeName },
        { compDesc, CompressorFx::xmlTypeName }, { gateDesc, GateFx::xmlTypeName }, { satDesc, SaturatorFx::xmlTypeName },
        { delayDesc, DelayFx::xmlTypeName }, { spaceDesc, SpaceFx::xmlTypeName }, { analyzerDesc, AnalyzerFx::xmlTypeName } };
    return t;
}

inline void registerFx (te::PluginManager& pm)
{
    pm.createBuiltInType<GainFx>();      pm.createBuiltInType<StripFx>();   pm.createBuiltInType<EqFx>();
    pm.createBuiltInType<CompressorFx>(); pm.createBuiltInType<GateFx>();   pm.createBuiltInType<SaturatorFx>();
    pm.createBuiltInType<DelayFx>();     pm.createBuiltInType<SpaceFx>();   pm.createBuiltInType<AnalyzerFx>();
}

inline const char* xmlTypeFor (const std::string& key)
{
    for (auto& t : fxTypes())
        if (key == t.desc().key) return t.xml;
    return nullptr;
}

} // namespace afo::fx

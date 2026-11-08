#include "AfoEngine.h"

#include <juce_audio_utils/juce_audio_utils.h>
#include <tracktion_engine/tracktion_engine.h>

#include "AfoPlugins.h"

#include <array>
#include <cmath>
#include <stdexcept>

namespace te = tracktion;

namespace afo
{

namespace
{
    synth::Params toParams (const SynthSettings& s)
    {
        synth::Params p;
        p.mode = s.mode; p.wave = s.wave; p.vel = s.vel; p.bri = s.bri; p.sus = s.sus; p.vol = s.vol; p.tun = s.tun; p.rev = s.rev;
        return p;
    }

    juce::File toFile (const std::string& p)  { return juce::File (juce::String::fromUTF8 (p.c_str())); }
    std::string toStd (const juce::String& s) { return s.toStdString(); }

    float clampDb (float db) { return juce::jlimit (-100.0f, 12.0f, db); }

    void requireMessageThread()
    {
        auto* mm = juce::MessageManager::getInstanceWithoutCreating();
        if (mm == nullptr || ! mm->isThisTheMessageThread())
            throw std::runtime_error ("afo_audio: el motor debe usarse desde el hilo que lo creó (hilo de mensajes).");
    }
}

//==============================================================================
struct TrackSlot
{
    int id = 0;
    te::AudioTrack::Ptr track;
    te::LevelMeasurer::Client meter;
    TrackInfo info;
    AfoSynthPlugin* synth = nullptr;         // solo en pistas de Instrumento/Batería
};

// Configuración de Tracktion dentro de la carpeta de datos de AllForOne (nada fuera de ella)
struct LocalPropertyStorage : public te::PropertyStorage
{
    LocalPropertyStorage (juce::String appName, juce::File dir) : te::PropertyStorage (appName), folder (dir) {}
    juce::File getAppPrefsFolder() override { folder.createDirectory(); return folder; }
    juce::File folder;
};

struct PreviewPlayer
{
    juce::AudioFormatManager formats;
    juce::AudioTransportSource transport;
    juce::AudioSourcePlayer player;
    std::unique_ptr<juce::PositionableAudioSource> source;   // archivo, o nota sintetizada en memoria
    juce::AudioDeviceManager* dm = nullptr;
    std::string path;

    PreviewPlayer() { formats.registerBasicFormats(); player.setSource (&transport); }
    ~PreviewPlayer() { detach(); transport.setSource (nullptr); }
    void attach (juce::AudioDeviceManager& d) { if (dm == nullptr) { dm = &d; dm->addAudioCallback (&player); } }
    void detach() { if (dm != nullptr) { dm->removeAudioCallback (&player); dm = nullptr; } }
};

struct Engine::Impl
{
    juce::ScopedJuceInitialiser_GUI juceInit;   // crea MessageManager en este hilo
    std::unique_ptr<te::Engine> engine;
    std::unique_ptr<te::Edit> edit;
    std::map<int, std::unique_ptr<TrackSlot>> slots;
    int nextId = 1;

    te::LevelMeasurer::Client masterClient;
    AfoMasterPlugin* master = nullptr;          // pertenece al Edit
    te::EditPlaybackContext* attachedContext = nullptr;
    PreviewPlayer preview;

    Impl (const std::string& appName, const std::string& dataDir)
    {
        juce::File base = dataDir.empty() ? juce::File::getSpecialLocation (juce::File::tempDirectory).getChildFile (appName)
                                          : toFile (dataDir);
        engine = std::make_unique<te::Engine> (std::make_unique<LocalPropertyStorage> (juce::String (appName), base.getChildFile ("tracktion")),
                                               nullptr, nullptr);
        engine->getPluginManager().createBuiltInType<AfoSynthPlugin>();
        engine->getPluginManager().createBuiltInType<AfoMasterPlugin>();

        // Edit vacío en memoria. El formato de proyecto .afo (V0.2) guardará su estado.
        auto editFile = base.getChildFile ("sesion").getChildFile ("session.tracktionedit");
        editFile.getParentDirectory().createDirectory();
        edit = te::createEmptyEdit (*engine, editFile);
        if (auto mv = edit->getMasterVolumePlugin())
            mv->setVolumeDb (0.0f);   // Tracktion crea el master a -3 dB; AllForOne parte de unidad
        // Sección master propia (fader, saturación, tono, limitador, VU) al final de la cadena del master
        auto mp = edit->getPluginCache().createNewPlugin (AfoMasterPlugin::xmlTypeName, {});
        master = dynamic_cast<AfoMasterPlugin*> (mp.get());
        if (master == nullptr)
            throw std::runtime_error ("afo_audio: no se pudo crear la sección master");
        edit->getMasterPluginList().insertPlugin (mp, -1, nullptr);
        edit->getTransport().ensureContextAllocated();
        attachMasterMeter();
    }

    ~Impl()
    {
        preview.transport.stop();
        preview.detach();
        if (edit != nullptr)
            edit->getTransport().stop (false, true);

        detachMasterMeter();

        for (auto& [id, slot] : slots)
            if (auto* lm = slot->track->getLevelMeterPlugin())
                lm->measurer.removeClient (slot->meter);

        slots.clear();
        edit.reset();
        engine.reset();
    }

    // Tracktion puede recrear el EditPlaybackContext (y el nuevo puede ocupar la misma dirección
    // que el anterior), así que no basta con comparar punteros: en cada lectura se vuelve a
    // registrar el cliente en el contexto ACTUAL. removeClient/addClient son baratos y seguros.
    void attachMasterMeter()
    {
        auto* ctx = edit->getCurrentPlaybackContext();
        if (ctx != nullptr)
        {
            ctx->masterLevels.removeClient (masterClient);
            ctx->masterLevels.addClient (masterClient);
        }
        attachedContext = ctx;
    }

    void detachMasterMeter()
    {
        if (edit != nullptr)
            if (auto* ctx = edit->getCurrentPlaybackContext())
                ctx->masterLevels.removeClient (masterClient);
        attachedContext = nullptr;
    }

    TrackSlot& slot (int id) const
    {
        auto it = slots.find (id);
        if (it == slots.end())
            throw std::out_of_range ("afo_audio: pista inexistente " + std::to_string (id));
        return *it->second;
    }
};

//==============================================================================
Engine::Engine (const std::string& appName, const std::string& dataDir) : impl (std::make_unique<Impl> (appName, dataDir)) {}

bool Engine::previewPlay (const std::string& path, double startSeconds)
{
    requireMessageThread();
    auto& pv = impl->preview;
    auto file = toFile (path);
    if (pv.path != path || pv.source == nullptr)
    {
        std::unique_ptr<juce::AudioFormatReader> reader (pv.formats.createReaderFor (file));
        if (reader == nullptr)
            return false;
        const double sr = reader->sampleRate;
        pv.transport.stop();
        pv.transport.setSource (nullptr);
        pv.source = std::make_unique<juce::AudioFormatReaderSource> (reader.release(), true);
        pv.transport.setSource (pv.source.get(), 0, nullptr, sr, 2);
        pv.path = path;
    }
    pv.attach (impl->engine->getDeviceManager().deviceManager);
    pv.transport.setPosition (juce::jlimit (0.0, juce::jmax (0.0, pv.transport.getLengthInSeconds() - 0.05), startSeconds));
    pv.transport.start();
    return true;
}

bool Engine::auditionSynth (const SynthSettings& s, int midiNote, double seconds)
{
    requireMessageThread();
    auto& pv = impl->preview;
    double sr = 48000.0;
    if (auto* dev = impl->engine->getDeviceManager().deviceManager.getCurrentAudioDevice())
        sr = dev->getCurrentSampleRate();
    const auto p = toParams (s);
    const int len = synth::hitLengthSamples (p, midiNote, seconds, sr);
    if (len <= 0)
        return false;
    juce::AudioBuffer<float> buf (2, len);
    synth::renderHit (p, midiNote, seconds, sr, buf.getWritePointer (0), len);
    buf.copyFrom (1, 0, buf, 0, 0, len);
    pv.transport.stop();
    pv.transport.setSource (nullptr);
    pv.source = std::make_unique<juce::MemoryAudioSource> (buf, true, false);
    pv.transport.setSource (pv.source.get(), 0, nullptr, sr, 2);
    pv.path.clear();
    pv.attach (impl->engine->getDeviceManager().deviceManager);
    pv.transport.setPosition (0.0);
    pv.transport.start();
    return true;
}

void Engine::previewStop()            { impl->preview.transport.stop(); }
bool Engine::previewPlaying() const   { return impl->preview.transport.isPlaying(); }
double Engine::previewPosition() const{ return impl->preview.transport.getCurrentPosition(); }
double Engine::previewLength() const  { return impl->preview.transport.getLengthInSeconds(); }
std::string Engine::previewPath() const { return impl->preview.path; }
Engine::~Engine() = default;

DeviceInfo Engine::deviceInfo() const
{
    DeviceInfo d;
    auto& dm = impl->engine->getDeviceManager().deviceManager;
    for (auto* type : dm.getAvailableDeviceTypes())
        d.availableTypes.push_back (toStd (type->getTypeName()));

    if (auto* dev = dm.getCurrentAudioDevice())
    {
        juce::AudioDeviceManager::AudioDeviceSetup setup;
        dm.getAudioDeviceSetup (setup);
        d.typeName = toStd (dev->getTypeName());
        d.outputName = toStd (setup.outputDeviceName);
        d.inputName = toStd (setup.inputDeviceName);
        d.sampleRate = dev->getCurrentSampleRate();
        d.bufferSize = dev->getCurrentBufferSizeSamples();
        d.numOutputChannels = dev->getActiveOutputChannels().countNumberOfSetBits();
        d.numInputChannels = dev->getActiveInputChannels().countNumberOfSetBits();
        d.open = dev->isOpen();
    }
    return d;
}

TrackInfo Engine::addAudioTrack (const std::string& filePath, const std::string& name)
{
    requireMessageThread();
    auto file = toFile (filePath);
    te::AudioFile audioFile (*impl->engine, file);
    if (! file.existsAsFile() || ! audioFile.isValid())
        throw std::runtime_error ("afo_audio: no se puede leer el audio: " + filePath);

    auto& edit = *impl->edit;
    edit.ensureNumberOfAudioTracks ((int) te::getAudioTracks (edit).size() + 1);
    auto* track = te::getAudioTracks (edit).getLast();
    const auto trackName = name.empty() ? file.getFileNameWithoutExtension() : juce::String::fromUTF8 (name.c_str());
    track->setName (trackName);

    const auto len = te::TimeDuration::fromSeconds (audioFile.getLength());
    auto clip = track->insertWaveClip (trackName, file, { { te::TimePosition(), len }, te::TimeDuration() }, false);
    if (clip == nullptr)
        throw std::runtime_error ("afo_audio: Tracktion no pudo crear el clip");

    auto slot = std::make_unique<TrackSlot>();
    slot->id = impl->nextId++;
    slot->track = track;
    slot->info.id = slot->id;
    slot->info.name = toStd (trackName);
    slot->info.sourcePath = filePath;
    slot->info.lengthSeconds = audioFile.getLength();
    slot->info.sampleRate = audioFile.getSampleRate();
    slot->info.numChannels = audioFile.getNumChannels();
    if (auto* lm = track->getLevelMeterPlugin())
        lm->measurer.addClient (slot->meter);

    auto info = slot->info;
    impl->slots[slot->id] = std::move (slot);
    edit.getTransport().ensureContextAllocated();
    impl->attachMasterMeter();
    return info;
}

TrackInfo Engine::addSynthTrack (const std::string& name, int mode)
{
    requireMessageThread();
    auto& edit = *impl->edit;
    edit.ensureNumberOfAudioTracks ((int) te::getAudioTracks (edit).size() + 1);
    auto* track = te::getAudioTracks (edit).getLast();
    track->setName (juce::String::fromUTF8 (name.c_str()));

    auto plugin = edit.getPluginCache().createNewPlugin (AfoSynthPlugin::xmlTypeName, {});
    auto* synthPlugin = dynamic_cast<AfoSynthPlugin*> (plugin.get());
    if (synthPlugin == nullptr)
        throw std::runtime_error ("afo_audio: no se pudo crear el sintetizador");
    track->pluginList.insertPlugin (plugin, 0, nullptr);
    synth::Params p;
    p.mode = mode;
    synthPlugin->params.store (p);

    auto slot = std::make_unique<TrackSlot>();
    slot->id = impl->nextId++;
    slot->track = track;
    slot->synth = synthPlugin;
    slot->info.id = slot->id;
    slot->info.name = name;
    slot->info.numChannels = 2;
    if (auto* lm = track->getLevelMeterPlugin())
        lm->measurer.addClient (slot->meter);
    auto info = slot->info;
    impl->slots[slot->id] = std::move (slot);
    edit.getTransport().ensureContextAllocated();
    impl->attachMasterMeter();
    return info;
}

void Engine::setSynthSettings (int id, const SynthSettings& s)
{
    requireMessageThread();
    auto& slot = impl->slot (id);
    if (slot.synth == nullptr)
        throw std::invalid_argument ("afo_audio: la pista no es de síntesis");
    slot.synth->params.store (toParams (s));
}

double Engine::setSynthNotes (int id, const std::vector<std::pair<double, int>>& notes, double lengthBeats)
{
    requireMessageThread();
    auto& slot = impl->slot (id);
    if (slot.synth == nullptr)
        throw std::invalid_argument ("afo_audio: la pista no es de síntesis");
    auto& edit = *impl->edit;
    for (auto* c : slot.track->getClips())          // el patrón se rehace entero: es pequeño
        c->removeFromParent();
    slot.info.lengthSeconds = 0.0;
    if (notes.empty())
        return 0.0;
    // Las notas van en tiempos de compás; la duración del clip se fija con el tempo actual
    // (al cambiar el tempo, la interfaz vuelve a mandar el patrón)
    const auto end = edit.tempoSequence.toTime (te::BeatPosition::fromBeats (juce::jmax (1.0, lengthBeats)));
    auto clip = slot.track->insertMIDIClip (slot.track->getName(), { te::TimePosition(), end }, nullptr);
    if (clip == nullptr)
        throw std::runtime_error ("afo_audio: Tracktion no pudo crear el clip MIDI");
    auto& seq = clip->getSequence();
    for (auto& [beat, note] : notes)
        seq.addNote (juce::jlimit (0, 127, note), te::BeatPosition::fromBeats (beat), te::BeatDuration::fromBeats (0.25), 100, 0, nullptr);
    slot.info.lengthSeconds = end.inSeconds();
    edit.getTransport().ensureContextAllocated();
    return slot.info.lengthSeconds;
}

bool Engine::removeTrack (int id)
{
    requireMessageThread();
    auto it = impl->slots.find (id);
    if (it == impl->slots.end())
        return false;
    auto& s = *it->second;
    if (auto* lm = s.track->getLevelMeterPlugin())
        lm->measurer.removeClient (s.meter);
    impl->edit->deleteTrack (s.track.get());
    impl->slots.erase (it);
    return true;
}

std::vector<TrackInfo> Engine::tracks() const
{
    std::vector<TrackInfo> r;
    for (auto& [id, s] : impl->slots)
        r.push_back (s->info);
    return r;
}

std::vector<float> Engine::trackPeaks (int id, int numBuckets) const
{
    auto& s = impl->slot (id);
    numBuckets = juce::jlimit (1, 20000, numBuckets);
    std::vector<float> peaks ((size_t) numBuckets, 0.0f);

    juce::AudioFormatManager fm;
    fm.registerBasicFormats();
    std::unique_ptr<juce::AudioFormatReader> reader (fm.createReaderFor (toFile (s.info.sourcePath)));
    if (reader == nullptr || reader->lengthInSamples <= 0)
        return peaks;

    const auto total = reader->lengthInSamples;
    for (int b = 0; b < numBuckets; ++b)
    {
        const auto start = total * b / numBuckets;
        const auto end = total * (b + 1) / numBuckets;
        float lowL = 0, highL = 0, lowR = 0, highR = 0;
        reader->readMaxLevels (start, juce::jmax ((juce::int64) 1, end - start), lowL, highL, lowR, highR);
        peaks[(size_t) b] = juce::jmax (std::abs (lowL), std::abs (highL), std::abs (lowR), std::abs (highR));
    }
    return peaks;
}

void Engine::setTrackGainDb (int id, float db)
{
    requireMessageThread();
    if (auto* vp = impl->slot (id).track->getVolumePlugin())
        vp->setVolumeDb (clampDb (db));
}

void Engine::setTrackPan (int id, float pan)
{
    requireMessageThread();
    if (auto* vp = impl->slot (id).track->getVolumePlugin())
        vp->setPan (juce::jlimit (-1.0f, 1.0f, pan));
}

void Engine::setTrackMute (int id, bool muted) { requireMessageThread(); impl->slot (id).track->setMute (muted); }
void Engine::setTrackSolo (int id, bool solo)  { requireMessageThread(); impl->slot (id).track->setSolo (solo); }

void Engine::setMasterGainDb (float db)
{
    requireMessageThread();
    impl->master->gainDb = clampDb (db);
}

float Engine::masterGainDb() const { return impl->master->gainDb.load(); }

void Engine::setMasterProcessing (float drive, float tone, bool limiter)
{
    requireMessageThread();
    impl->master->drive = juce::jlimit (0.0f, 100.0f, drive);
    impl->master->tone = juce::jlimit (0.0f, 100.0f, tone);
    impl->master->limiterOn = limiter;
}

void Engine::play()
{
    requireMessageThread();
    auto& t = impl->edit->getTransport();
    t.ensureContextAllocated();
    impl->attachMasterMeter();
    t.play (false);
}

void Engine::pause()  { requireMessageThread(); impl->edit->getTransport().stop (false, false); }

void Engine::stop()
{
    requireMessageThread();
    auto& t = impl->edit->getTransport();
    t.stop (false, false);
    t.setPosition (te::TimePosition());
}

bool Engine::isPlaying() const          { return impl->edit->getTransport().isPlaying(); }
double Engine::positionSeconds() const  { return impl->edit->getTransport().getPosition().inSeconds(); }
void Engine::setPositionSeconds (double s)
{
    requireMessageThread();
    impl->edit->getTransport().setPosition (te::TimePosition::fromSeconds (juce::jmax (0.0, s)));
}
double Engine::lengthSeconds() const    { return impl->edit->getLength().inSeconds(); }

void Engine::setTempo (double bpm)
{
    requireMessageThread();
    if (auto* t = impl->edit->tempoSequence.getTempo (0))
        t->setBpm (juce::jlimit (20.0, 400.0, bpm));
}

double Engine::tempo() const
{
    if (auto* t = impl->edit->tempoSequence.getTempo (0))
        return t->getBpm();
    return 0.0;
}

Levels Engine::readLevels()
{
    Levels l;
    impl->attachMasterMeter();
    l.masterL = impl->masterClient.getAndClearAudioLevel (0).dB;
    l.masterR = impl->masterClient.getAndClearAudioLevel (1).dB;
    l.masterVu = juce::jmax (-100.0f, impl->master->vuDb.load());
    for (auto& [id, s] : impl->slots)
        l.tracks[id] = juce::jmax (s->meter.getAndClearAudioLevel (0).dB, s->meter.getAndClearAudioLevel (1).dB);
    return l;
}

bool Engine::renderToWav (const std::string& path)
{
    requireMessageThread();
    auto& edit = *impl->edit;
    if (edit.getLength() <= te::TimeDuration())
        return false;

    // Tracktion renderiza todas las pistas que recibe, aunque estén silenciadas.
    // Exportamos lo que se escucha: con solo activo, solo esas; si no, las no silenciadas.
    auto all = te::getAllTracks (edit);
    bool anySolo = false;
    for (auto& [id, s] : impl->slots)
        anySolo = anySolo || s->track->isSolo (false);
    juce::BigInteger audible;
    for (auto& [id, s] : impl->slots)
    {
        const bool hear = anySolo ? s->track->isSolo (false) : ! s->track->isMuted (false);
        const int index = all.indexOf (s->track.get());
        if (hear && index >= 0)
            audible.setBit (index);
    }
    if (audible.isZero())
        return false;

    auto file = toFile (path);
    file.getParentDirectory().createDirectory();
    // Los streams de JUCE no truncan: un archivo existente quedaría con datos viejos/corruptos
    if (file.exists() && ! file.deleteFile())
        return false;
    if (edit.getTransport().isPlaying())
        edit.getTransport().stop (false, false);
    return te::Renderer::renderToFile ("AllForOne", file, edit, { te::TimePosition(), edit.getLength() },
                                       audible, true, true, {}, false)
           && file.existsAsFile();
}

void Engine::pumpMessages (int milliseconds)
{
   #if JUCE_MODAL_LOOPS_PERMITTED
    if (auto* mm = juce::MessageManager::getInstanceWithoutCreating())
        mm->runDispatchLoopUntil (juce::jmax (0, milliseconds));
   #else
    juce::ignoreUnused (milliseconds);
   #endif
}

//==============================================================================
std::string version()     { return AFO_VERSION; }
std::string juceVersion() { return toStd (juce::SystemStats::getJUCEVersion()); }

bool writeTestTone (const std::string& path, double frequency, double seconds, double sampleRate, float amplitudeDb)
{
    auto file = toFile (path);
    file.getParentDirectory().createDirectory();
    file.deleteFile();

    const int numSamples = (int) std::round (seconds * sampleRate);
    juce::AudioBuffer<float> buf (2, numSamples);
    const float amp = juce::Decibels::decibelsToGain (amplitudeDb);
    const int fade = juce::jmin (numSamples / 4, (int) (0.01 * sampleRate));   // 10 ms sin clics
    for (int i = 0; i < numSamples; ++i)
    {
        float env = 1.0f;
        if (i < fade) env = (float) i / (float) fade;
        else if (i > numSamples - fade) env = (float) (numSamples - i) / (float) fade;
        const float v = amp * env * (float) std::sin (juce::MathConstants<double>::twoPi * frequency * i / sampleRate);
        buf.setSample (0, i, v);
        buf.setSample (1, i, v);
    }

    juce::WavAudioFormat wav;
    auto os = file.createOutputStream();
    if (os == nullptr)
        return false;
    std::unique_ptr<juce::AudioFormatWriter> writer (wav.createWriterFor (os.get(), sampleRate, 2, 24, {}, 0));
    if (writer == nullptr)
        return false;
    os.release();   // el writer es ahora el dueño del stream
    return writer->writeFromAudioSampleBuffer (buf, 0, numSamples);
}

std::pair<float, float> measureFile (const std::string& path)
{
    juce::AudioFormatManager fm;
    fm.registerBasicFormats();
    std::unique_ptr<juce::AudioFormatReader> reader (fm.createReaderFor (toFile (path)));
    if (reader == nullptr || reader->lengthInSamples <= 0)
        throw std::runtime_error ("afo_audio: no se puede leer " + path);

    const int chans = (int) reader->numChannels;
    const int block = 65536;
    juce::AudioBuffer<float> buf (chans, block);
    double sumSq = 0.0; float peak = 0.0f; juce::int64 count = 0;
    for (juce::int64 pos = 0; pos < reader->lengthInSamples; pos += block)
    {
        const int n = (int) juce::jmin ((juce::int64) block, reader->lengthInSamples - pos);
        reader->read (&buf, 0, n, pos, true, true);
        for (int c = 0; c < chans; ++c)
        {
            auto* d = buf.getReadPointer (c);
            for (int i = 0; i < n; ++i) { peak = juce::jmax (peak, std::abs (d[i])); sumSq += (double) d[i] * d[i]; }
        }
        count += (juce::int64) n * chans;
    }
    const float rms = count > 0 ? (float) std::sqrt (sumSq / (double) count) : 0.0f;
    return { juce::Decibels::gainToDecibels (peak, -100.0f), juce::Decibels::gainToDecibels (rms, -100.0f) };
}

} // namespace afo

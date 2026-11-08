#include "AfoEngine.h"

#include <juce_audio_utils/juce_audio_utils.h>
#include <tracktion_engine/tracktion_engine.h>

#include "AfoPlugins.h"
#include "fx/FxPlugins.h"

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

    // Efectos nativos insertados (el Edit es el dueño; aquí solo referencias)
    struct FxSlot { int id = 0, trackId = 0; te::Plugin::Ptr plugin; fx::FxBase* fx = nullptr; };
    std::map<int, FxSlot> fxSlots;
    int nextFxId = 1;

    // Grabación
    int armedTrack = 0;
    bool monitor = false;
    te::WaveInputDevice* armedInput = nullptr;
    te::LevelMeasurer::Client inputClient;
    double recordStart = 0.0;
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
        fx::registerFx (engine->getPluginManager());

        // Edit vacío en memoria. El formato de proyecto .afo (V0.2) guardará su estado.
        auto editFile = base.getChildFile ("sesion").getChildFile ("session.tracktionedit");
        editFile.getParentDirectory().createDirectory();
        edit = te::createEmptyEdit (*engine, editFile);
        if (auto mv = edit->getMasterVolumePlugin())
            mv->setVolumeDb (0.0f);   // Tracktion crea el master a -3 dB; AllForOne parte de unidad
        edit->setCountInMode (te::Edit::CountIn::none);   // grabar empieza al pulsar
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
        if (armedInput != nullptr)
            armedInput->levelMeasurer.removeClient (inputClient);
        fxSlots.clear();

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

    te::PluginList& pluginList (int trackId) const
    {
        return trackId == 0 ? edit->getMasterPluginList() : slot (trackId).track->pluginList;
    }

    // Efectos de una pista en el orden de la cadena
    std::vector<const FxSlot*> chain (int trackId) const
    {
        std::vector<const FxSlot*> c;
        for (auto& [id, f] : fxSlots)
            if (f.trackId == trackId) c.push_back (&f);
        auto& list = pluginList (trackId);
        std::sort (c.begin(), c.end(), [&] (auto* a, auto* b) { return list.indexOf (a->plugin.get()) < list.indexOf (b->plugin.get()); });
        return c;
    }

    // Plugin delante del cual van los efectos: el volumen/pan de la pista o la sección master
    te::Plugin* anchor (int trackId) const
    {
        if (trackId == 0) return master;
        return slot (trackId).track->getVolumePlugin();
    }

    FxSlot& fxSlot (int id)
    {
        auto it = fxSlots.find (id);
        if (it == fxSlots.end())
            throw std::out_of_range ("afo_audio: efecto inexistente " + std::to_string (id));
        return it->second;
    }

    EffectInfo describe (const FxSlot& f) const
    {
        EffectInfo e;
        e.id = f.id; e.trackId = f.trackId; e.key = f.fx->desc.key; e.enabled = f.plugin->isEnabled();
        for (auto& p : f.fx->desc.params) e.values.push_back (f.fx->value (p.id));
        e.latencySeconds = f.plugin->getLatencySeconds();
        return e;
    }

    te::WaveInputDevice* findInput (const std::string& name) const
    {
        auto& dm = engine->getDeviceManager();
        for (int i = 0; i < dm.getNumWaveInDevices(); ++i)
            if (auto* w = dm.getWaveInDevice (i); w != nullptr && (name.empty() || toStd (w->getName()) == name))
                return w;
        return nullptr;
    }

    te::InputDeviceInstance* instanceFor (te::InputDevice* dev) const
    {
        for (auto* inst : edit->getAllInputDevices())
            if (&inst->getInputDevice() == dev)
                return inst;
        return nullptr;
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
    if (impl->armedTrack == id)
        disarm();
    for (auto f = impl->fxSlots.begin(); f != impl->fxSlots.end();)
        f = f->second.trackId == id ? impl->fxSlots.erase (f) : std::next (f);
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
    for (auto& [id, f] : impl->fxSlots)
        f.fx->bpm = (float) juce::jlimit (20.0, 400.0, bpm);
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

//==============================================================================
// Dispositivo de audio
AudioDeviceOptions Engine::audioDeviceOptions (const std::string& typeName) const
{
    AudioDeviceOptions o;
    auto& dm = impl->engine->getDeviceManager().deviceManager;
    const auto wanted = typeName.empty() ? dm.getCurrentAudioDeviceType() : juce::String::fromUTF8 (typeName.c_str());
    juce::AudioIODeviceType* type = nullptr;
    for (auto* t : dm.getAvailableDeviceTypes())
        if (t->getTypeName() == wanted)
            type = t;
    if (type == nullptr)
        return o;
    type->scanForDevices();
    o.typeName = toStd (type->getTypeName());
    for (auto& n : type->getDeviceNames (false)) o.outputs.push_back (toStd (n));
    for (auto& n : type->getDeviceNames (true))  o.inputs.push_back (toStd (n));
    o.separateInputsAndOutputs = type->hasSeparateInputsAndOutputs();
    if (auto* dev = dm.getCurrentAudioDevice(); dev != nullptr && dev->getTypeName() == type->getTypeName())
    {
        for (auto r : dev->getAvailableSampleRates()) o.sampleRates.push_back (r);
        for (auto b : dev->getAvailableBufferSizes()) o.bufferSizes.push_back (b);
        for (auto& n : dev->getInputChannelNames())  o.inputChannels.push_back (toStd (n));
        for (auto& n : dev->getOutputChannelNames()) o.outputChannels.push_back (toStd (n));
        o.hasControlPanel = dev->hasControlPanel();
        const double sr = juce::jmax (1.0, dev->getCurrentSampleRate());
        o.inputLatencyMs = 1000.0 * dev->getInputLatencyInSamples() / sr;
        o.outputLatencyMs = 1000.0 * dev->getOutputLatencyInSamples() / sr;
    }
    return o;
}

std::string Engine::setAudioDevice (const std::string& typeName, const std::string& output, const std::string& input,
                                    double sampleRate, int bufferSize)
{
    requireMessageThread();
    auto& tdm = impl->engine->getDeviceManager();
    auto& dm = tdm.deviceManager;
    auto& transport = impl->edit->getTransport();
    if (transport.isRecording())
        return "No se puede cambiar el dispositivo mientras se graba";
    transport.stop (false, false);
    impl->preview.transport.stop();
    if (impl->armedTrack != 0)
        disarm();

    // Lo que funcionaba antes: si el driver nuevo no abre, se vuelve a él (nunca quedarse sin audio)
    const auto prevType = dm.getCurrentAudioDeviceType();
    juce::AudioDeviceManager::AudioDeviceSetup prevSetup;
    dm.getAudioDeviceSetup (prevSetup);
    const bool prevOpen = dm.getCurrentAudioDevice() != nullptr;

    const auto type = juce::String::fromUTF8 (typeName.c_str());
    if (type.isNotEmpty() && type != dm.getCurrentAudioDeviceType())
        dm.setCurrentAudioDeviceType (type, true);
    juce::AudioDeviceManager::AudioDeviceSetup setup;
    dm.getAudioDeviceSetup (setup);
    bool separate = true;
    if (auto* t = dm.getCurrentDeviceTypeObject())
        separate = t->hasSeparateInputsAndOutputs();
    if (! output.empty()) setup.outputDeviceName = juce::String::fromUTF8 (output.c_str());
    setup.inputDeviceName = separate ? juce::String::fromUTF8 (input.c_str()) : setup.outputDeviceName;
    if (sampleRate > 0) setup.sampleRate = sampleRate;
    if (bufferSize > 0) setup.bufferSize = bufferSize;
    // Todos los canales: Tracktion los ofrece como entradas/salidas mono y estéreo
    setup.useDefaultInputChannels = setup.useDefaultOutputChannels = false;
    setup.inputChannels.clear();  setup.inputChannels.setRange (0, 64, true);
    setup.outputChannels.clear(); setup.outputChannels.setRange (0, 64, true);
    auto err = dm.setAudioDeviceSetup (setup, true);
    if (err.isEmpty() && dm.getCurrentAudioDevice() == nullptr)
        err = "El driver no abrió ningún dispositivo";
    if (err.isNotEmpty() && prevOpen)
    {
        dm.setCurrentAudioDeviceType (prevType, true);
        if (dm.setAudioDeviceSetup (prevSetup, true).isEmpty())
            err << " (se mantiene " << prevType << " · " << prevSetup.outputDeviceName << ")";
    }

    // JUCE avisa del cambio y Tracktion rehace sus entradas/salidas de forma asíncrona: se aplica
    // ya, para que al volver de aquí las entradas existan y nada pendiente pare luego el transporte
    dm.dispatchPendingMessages();
    tdm.rescanWaveDeviceList();
    tdm.dispatchPendingUpdates();
    tdm.saveSettings();
    transport.freePlaybackContext();
    transport.ensureContextAllocated();
    impl->attachMasterMeter();
    return toStd (err);
}

bool Engine::showAudioControlPanel()
{
    requireMessageThread();
    auto& dm = impl->engine->getDeviceManager().deviceManager;
    auto* dev = dm.getCurrentAudioDevice();
    if (dev == nullptr || ! dev->hasControlPanel())
        return false;
    if (dev->showControlPanel())          // el driver pide reiniciar (cambió búfer o frecuencia)
    {
        dm.closeAudioDevice();
        dm.restartLastAudioDevice();
    }
    impl->engine->getDeviceManager().saveSettings();
    return true;
}

//==============================================================================
// Grabación
std::vector<std::string> Engine::recordInputs() const
{
    std::vector<std::string> r;
    auto& dm = impl->engine->getDeviceManager();
    for (int i = 0; i < dm.getNumWaveInDevices(); ++i)
        if (auto* w = dm.getWaveInDevice (i))
            r.push_back (toStd (w->getName()));
    return r;
}

TrackInfo Engine::addRecordTrack (const std::string& name)
{
    requireMessageThread();
    auto& edit = *impl->edit;
    edit.ensureNumberOfAudioTracks ((int) te::getAudioTracks (edit).size() + 1);
    auto* track = te::getAudioTracks (edit).getLast();
    track->setName (juce::String::fromUTF8 (name.c_str()));
    auto slot = std::make_unique<TrackSlot>();
    slot->id = impl->nextId++;
    slot->track = track;
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

std::string Engine::armTrack (int trackId, const std::string& input, bool monitor)
{
    requireMessageThread();
    auto& slot = impl->slot (trackId);
    auto& edit = *impl->edit;
    auto& transport = edit.getTransport();
    if (transport.isRecording())
        return "Ya se está grabando";
    auto* dev = impl->findInput (input);
    if (dev == nullptr)
        return "No hay entradas de audio en el dispositivo actual (revisa la configuración de audio)";
    if (! dev->isEnabled())
        dev->setEnabled (true);
    dev->setMonitorMode (monitor ? te::InputDevice::MonitorMode::on : te::InputDevice::MonitorMode::off);

    transport.ensureContextAllocated();
    auto* inst = impl->instanceFor (dev);
    if (inst == nullptr)                       // entrada recién activada: el contexto debe recrearse
    {
        transport.freePlaybackContext();
        transport.ensureContextAllocated();
        inst = impl->instanceFor (dev);
    }
    if (inst == nullptr)
        return "La entrada no está disponible";

    for (auto* other : edit.getAllInputDevices())      // una sola entrada armada a la vez
        for (auto id : other->getTargets())
        {
            other->setRecordingEnabled (id, false);
            [[maybe_unused]] auto r = other->removeTarget (id, nullptr);
        }
    auto res = inst->setTarget (slot.track->itemID, true, nullptr);
    if (! res)
        return toStd (res.error());
    inst->setRecordingEnabled (slot.track->itemID, true);

    if (impl->armedInput != nullptr)
        impl->armedInput->levelMeasurer.removeClient (impl->inputClient);
    dev->levelMeasurer.addClient (impl->inputClient);
    impl->armedInput = dev;
    impl->armedTrack = trackId;
    impl->monitor = monitor;
    edit.restartPlayback();
    impl->attachMasterMeter();
    return {};
}

void Engine::disarm()
{
    requireMessageThread();
    auto& edit = *impl->edit;
    if (edit.getTransport().isRecording())
        edit.getTransport().stop (true, false);
    for (auto* inst : edit.getAllInputDevices())
        for (auto id : inst->getTargets())
        {
            inst->setRecordingEnabled (id, false);
            [[maybe_unused]] auto r = inst->removeTarget (id, nullptr);
        }
    if (impl->armedInput != nullptr)
    {
        impl->armedInput->levelMeasurer.removeClient (impl->inputClient);
        impl->armedInput->setMonitorMode (te::InputDevice::MonitorMode::off);
    }
    impl->armedInput = nullptr;
    impl->armedTrack = 0;
}

std::string Engine::startRecording()
{
    requireMessageThread();
    if (impl->armedTrack == 0 || impl->armedInput == nullptr)
        return "Arma una pista primero";
    auto& t = impl->edit->getTransport();
    if (t.isRecording())
        return {};
    impl->recordStart = t.getPosition().inSeconds();
    t.record (false, false);
    impl->attachMasterMeter();
    if (! t.isRecording())
        return "Tracktion no pudo empezar a grabar (¿dispositivo cerrado?)";
    return {};
}

TrackInfo Engine::stopRecording (bool discard)
{
    requireMessageThread();
    auto& t = impl->edit->getTransport();
    if (impl->armedTrack == 0)
        throw std::runtime_error ("afo_audio: no hay pista armada");
    auto& slot = impl->slot (impl->armedTrack);
    if (t.isRecording() || t.isPlaying())
        t.stop (discard, false);

    // La toma más reciente queda como el audio de la pista (las anteriores salen del Edit; sus archivos siguen en disco)
    te::WaveAudioClip* take = nullptr;
    for (auto* c : slot.track->getClips())
        if (auto* w = dynamic_cast<te::WaveAudioClip*> (c))
            if (take == nullptr || w->getPosition().getStart() >= take->getPosition().getStart())
                take = w;
    if (take != nullptr && ! discard)
    {
        for (auto* c : slot.track->getClips())
            if (c != take) c->removeFromParent();
        te::AudioFile af (*impl->engine, take->getOriginalFile());
        slot.info.sourcePath = toStd (take->getOriginalFile().getFullPathName());
        slot.info.startSeconds = take->getPosition().getStart().inSeconds();
        slot.info.lengthSeconds = take->getPosition().getLength().inSeconds();
        slot.info.sampleRate = af.getSampleRate();
        slot.info.numChannels = af.getNumChannels();
    }
    return slot.info;
}

RecordState Engine::recordState()
{
    RecordState s;
    auto& t = impl->edit->getTransport();
    s.recording = t.isRecording();
    s.armedTrack = impl->armedTrack;
    s.monitor = impl->monitor;
    if (impl->armedInput != nullptr)
    {
        s.input = toStd (impl->armedInput->getName());
        s.inputDb = juce::jmax (impl->inputClient.getAndClearAudioLevel (0).dB, impl->inputClient.getAndClearAudioLevel (1).dB);
        if (s.recording && impl->armedTrack != 0)
            if (auto* inst = impl->instanceFor (impl->armedInput))
                s.file = toStd (inst->getRecordingFile (impl->slot (impl->armedTrack).track->itemID).getFullPathName());
    }
    if (s.recording)
        s.seconds = juce::jmax (0.0, t.getPosition().inSeconds() - impl->recordStart);
    return s;
}

//==============================================================================
// Efectos nativos
std::vector<EffectTypeInfo> Engine::effectCatalog()
{
    std::vector<EffectTypeInfo> r;
    for (auto& t : fx::fxTypes())
    {
        auto& d = t.desc();
        EffectTypeInfo e { d.key, d.af, d.name, d.family, d.summary, {}, {} };
        for (auto& p : d.params)
        {
            EffectParamInfo pi;
            pi.id = p.id; pi.name = p.name; pi.unit = p.unit; pi.help = p.help;
            pi.min = p.min; pi.max = p.max; pi.def = p.def; pi.centre = p.centre;
            if (p.choices != nullptr)
                for (auto& c : juce::StringArray::fromTokens (juce::String::fromUTF8 (p.choices), "|", {}))
                    pi.choices.push_back (toStd (c));
            e.params.push_back (pi);
        }
        for (auto& m : juce::StringArray::fromTokens (juce::String::fromUTF8 (d.meters), "|", {}))
            if (m.isNotEmpty()) e.meters.push_back (toStd (m));
        r.push_back (e);
    }
    return r;
}

EffectInfo Engine::addEffect (int trackId, const std::string& key, int index)
{
    requireMessageThread();
    auto* xml = fx::xmlTypeFor (key);
    if (xml == nullptr)
        throw std::invalid_argument ("afo_audio: efecto desconocido " + key);
    auto& list = impl->pluginList (trackId);
    auto plugin = impl->edit->getPluginCache().createNewPlugin (xml, {});
    auto* f = dynamic_cast<fx::FxBase*> (plugin.get());
    if (f == nullptr)
        throw std::runtime_error ("afo_audio: no se pudo crear el efecto " + key);
    f->bpm = (float) tempo();
    auto c = impl->chain (trackId);
    int at = list.indexOf (impl->anchor (trackId));
    if (index >= 0 && index < (int) c.size())
        at = list.indexOf (c[(size_t) index]->plugin.get());
    list.insertPlugin (plugin, juce::jmax (0, at), nullptr);
    Impl::FxSlot s { impl->nextFxId++, trackId, plugin, f };
    impl->fxSlots[s.id] = s;
    impl->edit->getTransport().ensureContextAllocated();
    return impl->describe (impl->fxSlots[s.id]);
}

bool Engine::removeEffect (int effectId)
{
    requireMessageThread();
    auto it = impl->fxSlots.find (effectId);
    if (it == impl->fxSlots.end())
        return false;
    it->second.plugin->deleteFromParent();
    impl->fxSlots.erase (it);
    return true;
}

bool Engine::moveEffect (int effectId, int newIndex)
{
    requireMessageThread();
    auto& f = impl->fxSlot (effectId);
    auto c = impl->chain (f.trackId);
    const int from = (int) (std::find (c.begin(), c.end(), &f) - c.begin());
    newIndex = juce::jlimit (0, (int) c.size() - 1, newIndex);
    if (from == newIndex || from >= (int) c.size())
        return false;
    // Se mueve el nodo del plugin dentro del árbol de la pista; Tracktion reordena la cadena
    auto parent = f.plugin->state.getParent();
    parent.moveChild (parent.indexOf (f.plugin->state), parent.indexOf (c[(size_t) newIndex]->plugin->state), nullptr);
    return true;
}

bool Engine::setEffectParam (int effectId, const std::string& paramId, float value)
{
    requireMessageThread();
    return impl->fxSlot (effectId).fx->setValue (juce::String::fromUTF8 (paramId.c_str()), value);
}

void Engine::setEffectEnabled (int effectId, bool enabled)
{
    requireMessageThread();
    impl->fxSlot (effectId).plugin->setEnabled (enabled);
}

std::vector<EffectInfo> Engine::effects (int trackId) const
{
    std::vector<EffectInfo> r;
    for (auto* f : impl->chain (trackId))
        r.push_back (impl->describe (*f));
    return r;
}

std::vector<float> Engine::effectMeters (int effectId)              { return impl->fxSlot (effectId).fx->readMeters(); }
std::vector<float> Engine::effectSpectrum (int effectId, int bands) { return impl->fxSlot (effectId).fx->spectrum (bands); }

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

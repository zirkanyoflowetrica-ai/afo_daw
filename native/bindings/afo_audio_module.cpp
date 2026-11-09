// afo_audio — extensión Python (pybind11) del motor nativo de AllForOne.
// API pensada para crecer sin romper la interfaz: dicts simples hacia Python.
#include <pybind11/pybind11.h>
#include <pybind11/functional.h>
#include <pybind11/stl.h>

#include "AfoEngine.h"

namespace py = pybind11;

namespace
{
py::dict toDict (const afo::TrackInfo& t)
{
    py::dict d;
    d["id"] = t.id;
    d["name"] = t.name;
    d["source_path"] = t.sourcePath;
    d["start_seconds"] = t.startSeconds;
    d["length_seconds"] = t.lengthSeconds;
    d["sample_rate"] = t.sampleRate;
    d["num_channels"] = t.numChannels;
    return d;
}

py::dict toDict (const afo::ClipInfo& c)
{
    py::dict d;
    d["id"] = c.id; d["track_id"] = c.trackId; d["start"] = c.start; d["length"] = c.length; d["offset"] = c.offset;
    d["gain_db"] = c.gainDb; d["fade_in"] = c.fadeIn; d["fade_out"] = c.fadeOut; d["source_length"] = c.sourceLength;
    return d;
}

py::list toList (const std::vector<afo::ClipInfo>& v)
{
    py::list l;
    for (auto& c : v) l.append (toDict (c));
    return l;
}

py::dict toDict (const afo::PluginDesc& p)
{
    py::dict d;
    d["id"] = p.id; d["name"] = p.name; d["vendor"] = p.vendor; d["category"] = p.category;
    d["path"] = p.path; d["format"] = p.format; d["instrument"] = p.instrument;
    return d;
}

py::list toList (const std::vector<afo::PluginDesc>& v)
{
    py::list l;
    for (auto& p : v) l.append (toDict (p));
    return l;
}

py::dict toDict (const afo::Loudness& l)
{
    py::dict d;
    d["peak_db"] = l.peakDb; d["max_peak_db"] = l.maxPeakDb; d["rms_db"] = l.rmsDb;
    d["lufs_m"] = l.momentary; d["lufs_s"] = l.shortTerm; d["lufs_i"] = l.integrated;
    return d;
}

py::dict toDict (const afo::EffectInfo& e)
{
    py::dict d;
    d["id"] = e.id; d["track_id"] = e.trackId; d["key"] = e.key; d["enabled"] = e.enabled;
    d["values"] = e.values; d["latency_seconds"] = e.latencySeconds; d["automated"] = e.automated;
    d["name"] = e.name; d["plugin_id"] = e.pluginId;
    return d;
}

afo::SynthSettings settings (int mode, int wave, float vel, float bri, bool sus, float vol, float tun, float rev)
{
    afo::SynthSettings s;
    s.mode = mode; s.wave = wave; s.vel = vel; s.bri = bri; s.sus = sus; s.vol = vol; s.tun = tun; s.rev = rev;
    return s;
}
}

PYBIND11_MODULE (afo_audio, m)
{
    m.doc() = "AllForOne: motor de audio nativo (JUCE + Tracktion Engine)";
    m.attr("API_VERSION") = 11;

    m.def ("version", &afo::version);
    m.def ("scan_plugin_folders", [] (const std::string& listFile, const std::vector<std::string>& extra,
                                      std::function<void (const std::string&)> progress)
           {
               auto r = afo::scanPluginFolders (listFile, extra, progress);
               py::dict d;
               d["plugins"] = toList (r.plugins); d["failed"] = r.failed; d["folders"] = r.folders;
               return d;
           }, py::arg ("list_file"), py::arg ("extra_folders") = std::vector<std::string>(), py::arg ("progress") = nullptr,
           "Busca VST3 sin motor (para un proceso aparte); guarda la lista tras cada archivo.");
    m.def ("juce_version", &afo::juceVersion);
    m.def ("write_test_tone", &afo::writeTestTone,
           py::arg ("path"), py::arg ("frequency") = 440.0, py::arg ("seconds") = 4.0,
           py::arg ("sample_rate") = 48000.0, py::arg ("amplitude_db") = -12.0f,
           "Escribe un WAV 24 bits estéreo con una senoidal (señal de prueba sintética).");
    m.def ("measure_file", [] (const std::string& p)
           {
               auto [peak, rms] = afo::measureFile (p);
               py::dict d; d["peak_db"] = peak; d["rms_db"] = rms; return d;
           }, py::arg ("path"));
    m.def ("pump_messages", &afo::Engine::pumpMessages, py::arg ("milliseconds") = 0,
           "Procesa mensajes pendientes de JUCE. En Windows lo hace el bucle de Qt; úsese en otras plataformas.");

    m.def ("effect_catalog", []
           {
               py::list l;
               for (auto& t : afo::Engine::effectCatalog())
               {
                   py::dict d;
                   d["key"] = t.key; d["af"] = t.af; d["name"] = t.name; d["family"] = t.family; d["summary"] = t.summary;
                   d["meters"] = t.meters;
                   py::list ps;
                   for (auto& p : t.params)
                   {
                       py::dict q;
                       q["id"] = p.id; q["name"] = p.name; q["unit"] = p.unit; q["help"] = p.help;
                       q["min"] = p.min; q["max"] = p.max; q["def"] = p.def; q["centre"] = p.centre; q["choices"] = p.choices;
                       ps.append (q);
                   }
                   d["params"] = ps;
                   l.append (d);
               }
               return l;
           }, "Efectos nativos disponibles (Hito 1 de la biblioteca).");

    py::class_<afo::Engine> (m, "Engine")
        .def (py::init<const std::string&, const std::string&>(), py::arg ("app_name") = "AllForOne", py::arg ("data_dir") = "")
        .def ("device_info", [] (const afo::Engine& e)
              {
                  auto i = e.deviceInfo();
                  py::dict d;
                  d["type"] = i.typeName; d["output"] = i.outputName; d["input"] = i.inputName;
                  d["sample_rate"] = i.sampleRate; d["buffer_size"] = i.bufferSize;
                  d["output_channels"] = i.numOutputChannels; d["input_channels"] = i.numInputChannels;
                  d["open"] = i.open; d["available_types"] = i.availableTypes;
                  return d;
              })
        .def ("audio_device_options", [] (const afo::Engine& e, const std::string& type)
              {
                  auto o = e.audioDeviceOptions (type);
                  py::dict d;
                  d["type"] = o.typeName; d["outputs"] = o.outputs; d["inputs"] = o.inputs;
                  d["separate_io"] = o.separateInputsAndOutputs; d["sample_rates"] = o.sampleRates;
                  d["buffer_sizes"] = o.bufferSizes; d["input_channels"] = o.inputChannels;
                  d["output_channels"] = o.outputChannels; d["has_control_panel"] = o.hasControlPanel;
                  d["input_latency_ms"] = o.inputLatencyMs; d["output_latency_ms"] = o.outputLatencyMs;
                  return d;
              }, py::arg ("type") = "")
        .def ("set_audio_device", &afo::Engine::setAudioDevice, py::arg ("type"), py::arg ("output"), py::arg ("input") = "",
              py::arg ("sample_rate") = 0.0, py::arg ("buffer_size") = 0)
        .def ("show_audio_control_panel", &afo::Engine::showAudioControlPanel)
        .def ("record_inputs", &afo::Engine::recordInputs)
        .def ("add_record_track", [] (afo::Engine& e, const std::string& name) { return toDict (e.addRecordTrack (name)); }, py::arg ("name"))
        .def ("arm_track", &afo::Engine::armTrack, py::arg ("track_id"), py::arg ("input") = "", py::arg ("monitor") = false)
        .def ("disarm", &afo::Engine::disarm)
        .def ("start_recording", &afo::Engine::startRecording)
        .def ("stop_recording", [] (afo::Engine& e, bool discard) { return toDict (e.stopRecording (discard)); }, py::arg ("discard") = false)
        .def ("record_state", [] (afo::Engine& e)
              {
                  auto r = e.recordState();
                  py::dict d;
                  d["recording"] = r.recording; d["armed_track"] = r.armedTrack; d["input"] = r.input; d["monitor"] = r.monitor;
                  d["seconds"] = r.seconds; d["input_db"] = r.inputDb; d["file"] = r.file;
                  return d;
              })
        .def ("add_effect", [] (afo::Engine& e, int track, const std::string& key, int index) { return toDict (e.addEffect (track, key, index)); },
              py::arg ("track_id"), py::arg ("key"), py::arg ("index") = -1)
        .def ("remove_effect", &afo::Engine::removeEffect, py::arg ("effect_id"))
        .def ("move_effect", &afo::Engine::moveEffect, py::arg ("effect_id"), py::arg ("index"))
        .def ("set_effect_param", &afo::Engine::setEffectParam, py::arg ("effect_id"), py::arg ("param"), py::arg ("value"))
        .def ("set_effect_enabled", &afo::Engine::setEffectEnabled, py::arg ("effect_id"), py::arg ("enabled"))
        .def ("effects", [] (const afo::Engine& e, int track)
              { py::list l; for (auto& f : e.effects (track)) l.append (toDict (f)); return l; }, py::arg ("track_id"))
        .def ("effect_info", [] (const afo::Engine& e, int id) { return toDict (e.effectInfo (id)); }, py::arg ("effect_id"))
        .def ("set_effect_automation", &afo::Engine::setEffectAutomation, py::arg ("effect_id"), py::arg ("param"), py::arg ("points"),
              "Puntos (segundos, valor) de la automatización de un parámetro; [] la quita.")
        .def ("effect_automation", &afo::Engine::effectAutomation, py::arg ("effect_id"), py::arg ("param"))
        .def ("set_track_audio", [] (afo::Engine& e, int id, const std::string& path, double start)
              { return toDict (e.setTrackAudio (id, path, start)); }, py::arg ("track_id"), py::arg ("path"), py::arg ("start_seconds") = 0.0)
        .def ("effect_meters", &afo::Engine::effectMeters, py::arg ("effect_id"))
        .def ("effect_spectrum", &afo::Engine::effectSpectrum, py::arg ("effect_id"), py::arg ("bands") = 64)
        .def ("chain_scope", [] (afo::Engine& e, int track, int bands)
              {
                  auto c = e.chainScope (track, bands);
                  py::dict d;
                  d["pre"] = c.pre; d["post"] = c.post; d["pre_db"] = c.preDb; d["post_db"] = c.postDb; d["active"] = c.active;
                  return d;
              }, py::arg ("track_id"), py::arg ("bands") = 64,
              "Espectro y nivel antes y después de la cadena de efectos de una pista (0 = master).")
        .def ("add_audio_track", [] (afo::Engine& e, const std::string& path, const std::string& name)
              { return toDict (e.addAudioTrack (path, name)); }, py::arg ("path"), py::arg ("name") = "")
        .def ("remove_track", &afo::Engine::removeTrack)
        .def ("add_synth_track", [] (afo::Engine& e, const std::string& name, int mode)
              { return toDict (e.addSynthTrack (name, mode)); }, py::arg ("name"), py::arg ("mode") = 0)
        .def ("set_synth_settings", [] (afo::Engine& e, int id, int mode, int wave, float vel, float bri, bool sus, float vol, float tun, float rev)
              { e.setSynthSettings (id, settings (mode, wave, vel, bri, sus, vol, tun, rev)); },
              py::arg ("track_id"), py::arg ("mode") = 0, py::arg ("wave") = 0, py::arg ("vel") = 70.0f, py::arg ("bri") = 50.0f,
              py::arg ("sus") = false, py::arg ("vol") = 80.0f, py::arg ("tun") = 50.0f, py::arg ("rev") = 0.0f)
        .def ("set_synth_notes", &afo::Engine::setSynthNotes, py::arg ("track_id"), py::arg ("notes"), py::arg ("length_beats") = 64.0)
        .def ("audition_synth", [] (afo::Engine& e, int note, double seconds, int mode, int wave, float vel, float bri, bool sus, float vol, float tun, float rev)
              { return e.auditionSynth (settings (mode, wave, vel, bri, sus, vol, tun, rev), note, seconds); },
              py::arg ("note"), py::arg ("seconds") = 0.4, py::arg ("mode") = 0, py::arg ("wave") = 0, py::arg ("vel") = 70.0f,
              py::arg ("bri") = 50.0f, py::arg ("sus") = false, py::arg ("vol") = 80.0f, py::arg ("tun") = 50.0f, py::arg ("rev") = 0.0f)
        .def ("set_master_processing", &afo::Engine::setMasterProcessing, py::arg ("drive"), py::arg ("tone"), py::arg ("limiter"))
        .def ("set_master_ceiling", &afo::Engine::setMasterCeiling, py::arg ("db"))
        .def ("master_ceiling", &afo::Engine::masterCeiling)
        .def ("tracks", [] (const afo::Engine& e)
              { py::list l; for (auto& t : e.tracks()) l.append (toDict (t)); return l; })
        .def ("track_peaks", &afo::Engine::trackPeaks, py::arg ("track_id"), py::arg ("buckets") = 600)
        .def ("set_track_gain_db", &afo::Engine::setTrackGainDb)
        .def ("set_track_pan", &afo::Engine::setTrackPan)
        .def ("set_track_mute", &afo::Engine::setTrackMute)
        .def ("set_track_solo", &afo::Engine::setTrackSolo)
        // clips de audio (editar en Pistas)
        .def ("clips", [] (afo::Engine& e, int t) { return toList (e.clips (t)); }, py::arg ("track_id"))
        .def ("set_clip_range", [] (afo::Engine& e, long long id, double start, double length, double offset)
              { return toDict (e.setClipRange (id, start, length, offset)); },
              py::arg ("clip_id"), py::arg ("start"), py::arg ("length"), py::arg ("offset"))
        .def ("split_clip", [] (afo::Engine& e, long long id, double at) { return toList (e.splitClip (id, at)); },
              py::arg ("clip_id"), py::arg ("at_seconds"))
        .def ("duplicate_clip", [] (afo::Engine& e, long long id) { return toDict (e.duplicateClip (id)); }, py::arg ("clip_id"))
        .def ("remove_clip", &afo::Engine::removeClip, py::arg ("clip_id"))
        .def ("set_clip_gain", [] (afo::Engine& e, long long id, float db) { return toDict (e.setClipGain (id, db)); },
              py::arg ("clip_id"), py::arg ("db"))
        .def ("set_clip_fades", [] (afo::Engine& e, long long id, double fi, double fo) { return toDict (e.setClipFades (id, fi, fo)); },
              py::arg ("clip_id"), py::arg ("fade_in"), py::arg ("fade_out"))
        .def ("clip_peak_db", &afo::Engine::clipPeakDb, py::arg ("clip_id"))
        // plugins VST3 externos
        .def ("scan_plugins", [] (afo::Engine& e, const std::vector<std::string>& extra)
              {
                  auto r = e.scanPlugins (extra);
                  py::dict d;
                  d["plugins"] = toList (r.plugins); d["failed"] = r.failed; d["folders"] = r.folders;
                  return d;
              }, py::arg ("extra_folders") = std::vector<std::string>())
        .def ("known_plugins", [] (afo::Engine& e) { return toList (e.knownPlugins()); })
        .def ("reload_plugins", &afo::Engine::reloadPlugins)
        .def ("add_plugin_effect", [] (afo::Engine& e, int t, const std::string& id, int index, const std::string& state)
              { return toDict (e.addPluginEffect (t, id, index, state)); },
              py::arg ("track_id"), py::arg ("plugin_id"), py::arg ("index") = -1, py::arg ("state") = "")
        .def ("effect_state", &afo::Engine::effectState, py::arg ("effect_id"))
        .def ("show_effect_editor", &afo::Engine::showEffectEditor, py::arg ("effect_id"))
        .def ("set_track_instrument", &afo::Engine::setTrackInstrument, py::arg ("track_id"), py::arg ("plugin_id"), py::arg ("state") = "")
        .def ("track_instrument", &afo::Engine::trackInstrument, py::arg ("track_id"))
        .def ("track_instrument_state", &afo::Engine::trackInstrumentState, py::arg ("track_id"))
        .def ("show_instrument_editor", &afo::Engine::showInstrumentEditor, py::arg ("track_id"))
        .def ("set_clips", [] (afo::Engine& e, int t, const py::list& items)
              {
                  std::vector<afo::ClipInfo> v;
                  for (auto h : items)
                  {
                      auto d = h.cast<py::dict>();
                      afo::ClipInfo c;
                      c.start = d["start"].cast<double>(); c.length = d["length"].cast<double>();
                      c.offset = d.contains ("offset") ? d["offset"].cast<double>() : 0.0;
                      c.gainDb = d.contains ("gain_db") ? d["gain_db"].cast<float>() : 0.0f;
                      c.fadeIn = d.contains ("fade_in") ? d["fade_in"].cast<double>() : 0.0;
                      c.fadeOut = d.contains ("fade_out") ? d["fade_out"].cast<double>() : 0.0;
                      v.push_back (c);
                  }
                  return toList (e.setClips (t, v));
              }, py::arg ("track_id"), py::arg ("clips"))
        .def ("set_master_gain_db", &afo::Engine::setMasterGainDb)
        .def ("master_gain_db", &afo::Engine::masterGainDb)
        .def ("play", &afo::Engine::play)
        .def ("pause", &afo::Engine::pause)
        .def ("stop", &afo::Engine::stop)
        .def ("is_playing", &afo::Engine::isPlaying)
        .def ("position_seconds", &afo::Engine::positionSeconds)
        .def ("set_position_seconds", &afo::Engine::setPositionSeconds)
        .def ("length_seconds", &afo::Engine::lengthSeconds)
        .def ("set_tempo", &afo::Engine::setTempo)
        .def ("tempo", &afo::Engine::tempo)
        .def ("read_levels", [] (afo::Engine& e)
              {
                  auto l = e.readLevels();
                  py::dict d, tr;
                  d["master_l_db"] = l.masterL; d["master_r_db"] = l.masterR; d["master_vu_db"] = l.masterVu;
                  for (auto& [id, db] : l.tracks) tr[py::int_ (id)] = db;
                  d["tracks"] = tr;
                  py::dict lo;
                  for (auto& [id, v] : l.loud) lo[py::int_ (id)] = toDict (v);
                  d["loud"] = lo;
                  d["master_loud"] = toDict (l.master);
                  return d;
              })
        .def ("reset_loudness", &afo::Engine::resetLoudness)
        .def ("measure_mix", [] (afo::Engine& e)
              {
                  auto m = e.measureMix();
                  py::dict d, tr;
                  d["ok"] = m.ok; d["seconds"] = m.seconds; d["master"] = toDict (m.master);
                  for (auto& [id, v] : m.tracks) tr[py::int_ (id)] = toDict (v);
                  d["tracks"] = tr;
                  return d;
              }, "Sonoridad (LUFS, RMS, pico) del master y de cada pista procesando la sesión en memoria, sin archivos.")
        .def ("render_to_wav", &afo::Engine::renderToWav, py::arg ("path"), py::call_guard<py::gil_scoped_release>())
        .def ("preview_play", &afo::Engine::previewPlay, py::arg ("path"), py::arg ("start_seconds") = 0.0)
        .def ("preview_stop", &afo::Engine::previewStop)
        .def ("preview_playing", &afo::Engine::previewPlaying)
        .def ("preview_position", &afo::Engine::previewPosition)
        .def ("preview_length", &afo::Engine::previewLength)
        .def ("preview_path", &afo::Engine::previewPath);
}

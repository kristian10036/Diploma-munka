#include "rf_agent/sdrangel_demod_settings.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <stdexcept>

namespace rf_agent {

using Json = nlohmann::json;

std::string normalized_demodulator(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char character) {
        return static_cast<char>(std::toupper(character));
    });
    return value;
}

DemodulatorProfile demodulator_profile(const std::string& requested) {
    static const std::map<std::string, DemodulatorProfile> profiles{
        {"AM", {"AMDemod", "AMDemodSettings", true}},
        {"NFM", {"NFMDemod", "NFMDemodSettings", true}},
        {"WFM", {"WFMDemod", "WFMDemodSettings", true}},
        {"BFM", {"BFMDemod", "BFMDemodSettings", true}},
        {"USB", {"SSBDemod", "SSBDemodSettings", true}},
        {"LSB", {"SSBDemod", "SSBDemodSettings", true}},
        {"DSB", {"SSBDemod", "SSBDemodSettings", true}},
        {"CW", {"SSBDemod", "SSBDemodSettings", true}},
        {"DSD", {"DSDDemod", "DSDDemodSettings", true}},
        {"FREEDV", {"FreeDVDemod", "FreeDVDemodSettings", true}},
        {"M17", {"M17Demod", "M17DemodSettings", true}},
        {"DAB", {"DABDemod", "DABDemodSettings", true}},
    };
    const auto found = profiles.find(normalized_demodulator(requested));
    if (found == profiles.end()) throw std::runtime_error("unsupported SDRangel demodulator");
    return found->second;
}

std::string channel_settings_key(const Json& current, const std::string& preferred) {
    if (current.contains(preferred) && current.at(preferred).is_object()) return preferred;
    for (const auto& item : current.items()) {
        if (item.value().is_object() && item.key().size() >= 8 &&
            item.key().compare(item.key().size() - 8, 8, "Settings") == 0) {
            return item.key();
        }
    }
    throw std::runtime_error("SDRangel channel settings schema is unavailable");
}

bool set_first_supported(
    Json& patch,
    const Json& current,
    std::initializer_list<const char*> candidate_keys,
    const Json& value,
    Json& applied) {
    for (const char* key : candidate_keys) {
        if (current.contains(key)) {
            patch[key] = value;
            applied[key] = value;
            return true;
        }
    }
    return false;
}

std::pair<Json, Json> buildDemodulatorChannelSettings(
    const std::string& normalized_mode,
    const Json& current,
    const DemodulatorSettingsParams& params) {
    const std::string mode = normalized_demodulator(normalized_mode);
    Json settings = Json::object();
    Json applied = Json::object();

    if (params.input_frequency_offset_hz.has_value()) {
        set_first_supported(
            settings, current, {"inputFrequencyOffset"}, *params.input_frequency_offset_hz, applied);
    }

    // Sávszélesség (a CW alapértelmezett 500 Hz, ha nincs megadva érték).
    std::optional<int> requested_bandwidth = params.bandwidth_hz;
    if (mode == "CW" && (!requested_bandwidth.has_value() || *requested_bandwidth <= 0)) {
        requested_bandwidth = 500;
    }
    const bool bandwidth_engaged = requested_bandwidth.has_value() && *requested_bandwidth > 0;
    if (bandwidth_engaged) {
        int signed_bandwidth = *requested_bandwidth;
        if (mode == "LSB") signed_bandwidth = -*requested_bandwidth;
        set_first_supported(
            settings, current, {"rfBandwidth", "bandwidth", "rfBandwidthHz"}, signed_bandwidth, applied);
    }

    // SSB-jellegű módok geometriája. Akkor frissítjük, ha a sávszélesség is
    // állítva van (indítás vagy mód/BW módosítás), hogy az egyoldalas/DSB és a
    // szimmetrikus geometria konzisztens maradjon.
    if (bandwidth_engaged && (mode == "USB" || mode == "LSB" || mode == "DSB" || mode == "CW")) {
        const bool is_lsb = mode == "LSB";
        const bool is_dsb = mode == "DSB";
        const int low_cutoff = mode == "CW" ? 100 : 300;
        set_first_supported(
            settings, current, {"lowCutoff", "lowCutoffHz"}, is_lsb ? -low_cutoff : low_cutoff, applied);
        set_first_supported(settings, current, {"dsb"}, is_dsb ? 1 : 0, applied);
    }

    if (params.squelch_db.has_value() && std::isfinite(*params.squelch_db)) {
        set_first_supported(
            settings, current, {"squelch", "squelchDB", "squelchDb"}, *params.squelch_db, applied);
    }

    if (params.volume.has_value()) {
        set_first_supported(settings, current, {"volume", "audioVolume"}, *params.volume, applied);
    }

    // Audio-routing csak indításkor (vagy explicit kérésre): a passband-húzás
    // nem konfigurálja újra a hangkimenetet minden mozdulatnál.
    if (params.include_audio_routing) {
        set_first_supported(settings, current, {"audioMute", "mute"}, false, applied);
        if (params.audio_device.has_value() &&
            normalized_demodulator(*params.audio_device) != "DEFAULT" &&
            !params.audio_device->empty()) {
            set_first_supported(
                settings, current, {"audioDeviceName", "audioDevice"}, *params.audio_device, applied);
        }
        if (params.audio_sample_rate.has_value() && *params.audio_sample_rate > 0) {
            set_first_supported(
                settings, current, {"audioSampleRate", "audioSampleRateHz"}, *params.audio_sample_rate, applied);
        }
        if (mode == "BFM") {
            set_first_supported(settings, current, {"audioStereo", "stereo"}, true, applied);
        }
    }

    return {settings, applied};
}

}  // namespace rf_agent

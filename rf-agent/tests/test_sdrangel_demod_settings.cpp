#include "rf_agent/sdrangel_demod_settings.hpp"

#include <nlohmann/json.hpp>

#include <cassert>
#include <iostream>

using Json = nlohmann::json;
using namespace rf_agent;

// Egy NFM plugin tipikus settings-felülete (a kulcsok jelenléte dönti el, mit
// állítunk be).
static Json nfm_current() {
    return Json{
        {"inputFrequencyOffset", 0},
        {"rfBandwidth", 12500},
        {"squelch", -60.0},
        {"volume", 1.0},
        {"audioMute", true},
        {"audioSampleRate", 48000},
        {"audioDeviceName", "default"},
    };
}

// SSB plugin: rfBandwidth + lowCutoff + dsb.
static Json ssb_current() {
    return Json{
        {"inputFrequencyOffset", 0},
        {"rfBandwidth", 2700},
        {"lowCutoff", 300},
        {"dsb", 0},
        {"squelch", -60.0},
        {"volume", 1.0},
    };
}

int main() {
    int checks = 0;
    auto check = [&](bool ok, const char* msg) {
        if (!ok) { std::cerr << "FAIL: " << msg << "\n"; std::exit(1); }
        ++checks;
    };

    // 1. Profil-feloldás: SSB-családra mind az SSBDemod plugin.
    check(demodulator_profile("USB").channel_type == "SSBDemod", "USB -> SSBDemod");
    check(demodulator_profile("nfm").channel_type == "NFMDemod", "case-insensitive NFM");

    // 2. Update: csak az offset + bandwidth + squelch + volume kerül a patch-be,
    //    az audio-routing NEM (include_audio_routing=false).
    {
        DemodulatorSettingsParams p;
        p.input_frequency_offset_hz = 500000;
        p.bandwidth_hz = 25000;
        p.squelch_db = -55.0;
        p.volume = 0.8;
        p.include_audio_routing = false;
        auto [settings, applied] = buildDemodulatorChannelSettings("NFM", nfm_current(), p);
        check(settings["inputFrequencyOffset"] == 500000, "update: offset set");
        check(settings["rfBandwidth"] == 25000, "update: bandwidth set");
        check(settings["squelch"] == -55.0, "update: squelch set");
        check(settings["volume"] == 0.8, "update: volume set");
        check(!settings.contains("audioMute"), "update: audio routing skipped");
        check(!settings.contains("audioDeviceName"), "update: audio device skipped");
    }

    // 3. LSB előjel: a sávszélesség negatív, a lowCutoff is negatív, dsb=0.
    {
        DemodulatorSettingsParams p;
        p.bandwidth_hz = 2700;
        auto [settings, applied] = buildDemodulatorChannelSettings("LSB", ssb_current(), p);
        check(settings["rfBandwidth"] == -2700, "LSB: negative bandwidth");
        check(settings["lowCutoff"] == -300, "LSB: negative lowCutoff");
        check(settings["dsb"] == 0, "LSB: dsb 0");
    }

    // 4. DSB: dsb=1.
    {
        DemodulatorSettingsParams p;
        p.bandwidth_hz = 6000;
        auto [settings, applied] = buildDemodulatorChannelSettings("DSB", ssb_current(), p);
        check(settings["dsb"] == 1, "DSB: dsb 1");
        check(settings["rfBandwidth"] == 6000, "DSB: positive bandwidth");
    }

    // 5. CW alapértelmezett 500 Hz, ha nincs megadva bandwidth.
    {
        DemodulatorSettingsParams p;  // bandwidth nincs megadva
        auto [settings, applied] = buildDemodulatorChannelSettings("CW", ssb_current(), p);
        check(settings["rfBandwidth"] == 500, "CW: default 500 Hz");
        check(settings["lowCutoff"] == 100, "CW: lowCutoff 100");
    }

    // 6. Start (include_audio_routing=true): mute=false + device + stereo BFM-nél.
    {
        DemodulatorSettingsParams p;
        p.input_frequency_offset_hz = 0;
        p.bandwidth_hz = 12500;
        p.volume = 1.0;
        p.audio_device = std::string("HDA Intel");
        p.audio_sample_rate = 48000;
        p.include_audio_routing = true;
        auto [settings, applied] = buildDemodulatorChannelSettings("NFM", nfm_current(), p);
        check(settings["audioMute"] == false, "start: unmute");
        check(settings["audioDeviceName"] == "HDA Intel", "start: device set");
        check(settings["audioSampleRate"] == 48000, "start: sample rate set");
    }

    // 7. Ismeretlen mező nem kerül be (a plugin nem támogatja).
    {
        DemodulatorSettingsParams p;
        p.squelch_db = -70.0;
        Json no_squelch = Json{{"inputFrequencyOffset", 0}, {"rfBandwidth", 12500}};
        auto [settings, applied] = buildDemodulatorChannelSettings("NFM", no_squelch, p);
        check(!settings.contains("squelch"), "unsupported squelch field not added");
    }

    // 8. "default" audio eszköz nem kerül beállításra.
    {
        DemodulatorSettingsParams p;
        p.audio_device = std::string("default");
        p.include_audio_routing = true;
        auto [settings, applied] = buildDemodulatorChannelSettings("NFM", nfm_current(), p);
        check(!settings.contains("audioDeviceName"), "default device not patched");
    }

    std::cout << "sdrangel demod settings: PASS (" << checks << " checks)\n";
    return 0;
}

#pragma once

// -----------------------------------------------------------------------------
// Közös, hálózatmentes SDRangel demodulátor-settings logika.
//
// A korábban a startDemodulator()-ba ágyazott "keresd meg a plugin által
// támogatott settings mezőt és állítsd be" logika ide került, hogy a
// demodulátor INDÍTÁSA és az aktív csatorna ÉLŐ FRISSÍTÉSE (updateDemodulator)
// ugyanazt a tesztelt kódot használja, duplikáció nélkül.
//
// A függvények tiszták: bemenet az SDRangel pillanatnyi channel settings
// objektuma + a kívánt paraméterek, kimenet a PATCH-elendő mezők és az
// alkalmazott értékek. Így hálózat nélkül, egységtesztben ellenőrizhető, hogy a
// helyes plugin-mezők kerülnek-e beállításra.
// -----------------------------------------------------------------------------

#include <map>
#include <optional>
#include <string>
#include <utility>

#include <nlohmann/json.hpp>

namespace rf_agent {

std::string normalized_demodulator(std::string value);

struct DemodulatorProfile {
    std::string channel_type;
    std::string settings_key;
    bool audio_output{true};
};

// SDRangel Rx channel plugin azonosítók. USB/LSB/DSB/CW mind az SSB demodot
// használja, mód-specifikus settings-szel (lowCutoff / dsb) a létrehozás után.
DemodulatorProfile demodulator_profile(const std::string& requested);

// A pillanatnyi settings válaszból kiválasztja a "*Settings" kulcsot.
std::string channel_settings_key(const nlohmann::json& current, const std::string& preferred);

// Az első olyan jelölt kulcsot állítja be, amelyet a plugin ténylegesen
// támogat (a current alapján). Igazat ad vissza, ha sikerült.
bool set_first_supported(
    nlohmann::json& patch,
    const nlohmann::json& current,
    std::initializer_list<const char*> candidate_keys,
    const nlohmann::json& value,
    nlohmann::json& applied);

// Az élő frissítéshez és az indításhoz egyaránt használt paraméterek. Csak a
// megadott (engaged) optionalok kerülnek beállításra, így egy passband-húzás
// nem írja felül az audio-routingot.
struct DemodulatorSettingsParams {
    std::optional<std::int64_t> input_frequency_offset_hz;
    std::optional<int> bandwidth_hz;            // előjel nélkül; LSB esetén a fv. negálja
    std::optional<double> squelch_db;
    std::optional<double> volume;
    std::optional<std::string> audio_device;    // jellemzően csak indításkor
    std::optional<int> audio_sample_rate;       // jellemzően csak indításkor
    bool include_audio_routing{false};          // indítás: true (mute/eszköz/stereo)
};

// Felépíti a PATCH-elendő settings mezőket a mód geometriájának megfelelően.
// @returns {settings_patch, applied}
std::pair<nlohmann::json, nlohmann::json> buildDemodulatorChannelSettings(
    const std::string& normalized_mode,
    const nlohmann::json& current_settings,
    const DemodulatorSettingsParams& params);

}  // namespace rf_agent

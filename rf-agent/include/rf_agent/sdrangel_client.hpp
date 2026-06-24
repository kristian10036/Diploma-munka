#pragma once

#include <chrono>
#include <cstdint>
#include <optional>
#include <string>
#include <mutex>

namespace rf_agent {

struct SdrangelConfig {
    bool enabled{false};
    std::string api_url{"http://127.0.0.1:8091/sdrangel"};
    std::chrono::milliseconds timeout{5000};
    int default_device_set_index{0};
    std::string device_settings_key;

    // Data plane is intentionally configuration/status only until a concrete,
    // tested SDRangel sample source or input plugin is selected.
    std::string data_plane_mode{"not_configured"};
    std::string data_plane_endpoint;
    std::string iq_sample_format{"cf32_le"};
    std::uint64_t iq_sample_rate_hz{0};

    // SDRangel can mirror the selected output device as raw L16/S16LE audio
    // over UDP. The ingest service relays this stream to the browser.
    std::string audio_udp_address{"127.0.0.1"};
    std::uint16_t audio_udp_port{9998};
    int audio_udp_sample_rate_hz{48000};
};

class SdrangelClient {
public:
    explicit SdrangelClient(SdrangelConfig config);

    [[nodiscard]] std::string status() const;
    [[nodiscard]] std::string deviceSets() const;
    [[nodiscard]] std::string devices() const;
    [[nodiscard]] std::string createDeviceSet(const std::string& hardware_type) const;
    [[nodiscard]] std::string tune(std::uint64_t center_frequency_hz, int device_set_index) const;
    [[nodiscard]] std::string startDemodulator(
        const std::string& demodulator,
        int device_set_index,
        std::int64_t offset_hz,
        int audio_sample_rate,
        int bandwidth_hz,
        double squelch_db,
        const std::string& audio_device,
        double volume) const;
    [[nodiscard]] std::string stopDemodulator(int device_set_index, int channel_index) const;

    // Egy már futó SDRangel csatorna élő frissítése (passband húzás/mód/squelch).
    // Nem hoz létre és nem töröl csatornát. A retune_device_center_hz csak akkor
    // van megadva, ha a kiválasztott frekvencia kívül esik a capture tartományon.
    [[nodiscard]] std::string updateDemodulator(
        const std::string& demodulator,
        int device_set_index,
        int channel_index,
        std::optional<std::int64_t> input_frequency_offset_hz,
        std::optional<int> bandwidth_hz,
        std::optional<double> squelch_db,
        std::optional<double> volume,
        std::optional<std::uint64_t> retune_device_center_hz) const;

private:
    SdrangelConfig config_;
    mutable std::mutex status_mutex_;
    mutable std::string last_success_at_;
};

}  // namespace rf_agent

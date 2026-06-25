#pragma once

#include "rf_agent/rf_source.hpp"

#include <chrono>
#include <mutex>
#include <string>
#include <sys/types.h>

namespace rf_agent {

struct AaroniaRfConfig {
    bool enabled{true};
    std::string executable{"/usr/local/bin/aaronia-worker"};
    std::string sensor_id{"aaronia-v6-01"};
    std::string session_id{"aaronia-live"};
    std::uint64_t start_frequency_hz{75'000'000ULL};
    std::uint64_t stop_frequency_hz{6'000'000'000ULL};
    std::string receiver_clock{"245MHz"};
    double rbw_hz{100'000.0};
    double reference_level_dbm{-20.0};
    std::size_t maximum_points{16'384};
    double maximum_fps{10.0};
};

class AaroniaRfSource final : public IRfSource {
public:
    explicit AaroniaRfSource(AaroniaRfConfig config);
    ~AaroniaRfSource() override;

    bool initialize() override;
    bool start() override;
    void stop() override;
    [[nodiscard]] SourceStatus status() const override;
    [[nodiscard]] SourceCapabilities capabilities() const override;
    bool setCenterFrequency(std::uint64_t frequency_hz) override;
    bool setSampleRate(std::uint64_t sample_rate_hz) override;
    bool setGain(double gain_db) override;
    bool setSpan(std::uint64_t span_hz) override;
    bool setSpectrumPointCount(std::size_t point_count) override;
    bool configureViewport(std::uint64_t center_frequency_hz, std::uint64_t span_hz,
                           std::size_t point_count);
    std::optional<SpectrumFrame> readSpectrumFrame() override;
    std::optional<IqFrame> readIqFrame() override;

private:
    bool launchLocked();
    void stopLocked();
    void noteExitLocked(int wait_status);
    std::optional<SpectrumFrame> parseLineLocked(const std::string& line);

    mutable std::mutex mutex_;
    AaroniaRfConfig config_;
    // A legutóbbi konfiguráció, amely tényleg érvényes frame-et hozott. Ha egy
    // viewport-kérés (pl. szűk span/finom RBW) ismételten lefagyasztja a
    // workert -- amit az SDK belső kivétele okoz, nem a mi kódunk --, ide
    // esik vissza a forrás, hogy ne fagyjon le végtelenül egy rossz kérésen.
    AaroniaRfConfig last_good_config_;
    SourceStatus status_;
    pid_t worker_pid_{-1};
    int output_fd_{-1};
    std::string input_buffer_;
    std::uint64_t sequence_{0};
    std::uint64_t worker_dropped_frames_{0};
    std::uint64_t hardware_min_frequency_hz_{0};
    std::uint64_t hardware_max_frequency_hz_{0};
    unsigned int restart_attempts_{0};
    std::chrono::steady_clock::time_point next_restart_{};
    bool stop_requested_{false};
};

}  // namespace rf_agent

#pragma once

#include "rf_agent/rf_source.hpp"

#include <cstddef>
#include <cstdint>
#include <mutex>
#include <random>
#include <string>

namespace rf_agent {

struct MockRfConfig {
    std::string sensor_id{"hp-demo-01"};
    std::string session_id{"mock-session"};
    std::uint64_t start_frequency_hz{88'000'000};
    std::uint64_t stop_frequency_hz{108'000'000};
    std::uint64_t sample_rate_hz{20'000'000};
    std::size_t point_count{2'048};
    double noise_floor_dbm{-95.0};
    double noise_deviation_db{2.0};
    double gain_db{0.0};
    double max_fps{5.0};
    std::uint32_t random_seed{0x5A17U};
};

class MockRfSource final : public IRfSource {
public:
    explicit MockRfSource(MockRfConfig config = {});

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

    std::optional<SpectrumFrame> readSpectrumFrame() override;
    std::optional<IqFrame> readIqFrame() override;

private:
    void addSignal(
        SpectrumFrame& frame,
        double center_hz,
        double peak_dbm,
        double sigma_hz) const;
    [[nodiscard]] std::string nowIso8601() const;
    void setError(std::string message);

    mutable std::mutex mutex_;
    MockRfConfig config_;
    SourceStatus status_;
    std::uint64_t sequence_{0};
    std::mt19937 random_;
};

}  // namespace rf_agent

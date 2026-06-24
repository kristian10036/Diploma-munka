#pragma once

#include "rf_agent/aaronia_rf_source.hpp"
#include "rf_agent/soapy_rf_source.hpp"

#include <chrono>
#include <memory>
#include <mutex>

namespace rf_agent {

struct AutoRfConfig {
    SoapyRfConfig usrp;
    SoapyRfConfig hackrf;
    AaroniaRfConfig aaronia;
    std::chrono::milliseconds poll_interval{2000};
};

class AutoRfSource final : public IRfSource {
public:
    explicit AutoRfSource(AutoRfConfig config);
    ~AutoRfSource() override;
    bool initialize() override;
    bool start() override;
    void stop() override;
    [[nodiscard]] SourceStatus status() const override;
    [[nodiscard]] SourceCapabilities capabilities() const override;
    bool setCenterFrequency(std::uint64_t value) override;
    bool setSampleRate(std::uint64_t value) override;
    bool setGain(double value) override;
    bool setSpan(std::uint64_t value) override;
    bool setSpectrumPointCount(std::size_t value) override;
    bool configureViewport(std::uint64_t center_frequency_hz, std::uint64_t span_hz,
                           std::size_t maximum_points);
    std::optional<SpectrumFrame> readSpectrumFrame() override;
    std::optional<IqFrame> readIqFrame() override;
    [[nodiscard]] bool supportsNativeAudio() const override;
    std::string startNativeAudio(const std::string& demodulator, int audio_sample_rate, double volume) override;
    std::string stopNativeAudio() override;

private:
    std::string desiredMode() const;
    bool switchTo(const std::string& mode);
    std::shared_ptr<IRfSource> active() const;

    AutoRfConfig config_;
    mutable std::mutex mutex_;
    std::shared_ptr<IRfSource> active_;
    std::string active_mode_;
    bool running_{false};
    std::chrono::steady_clock::time_point next_probe_{};
};

}  // namespace rf_agent

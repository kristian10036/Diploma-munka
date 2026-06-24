#pragma once

#include "rf_agent/dsp/fft_pipeline.hpp"
#include "rf_agent/rf_source.hpp"

#include <chrono>
#include <memory>
#include <mutex>
#include <string>

namespace rf_agent {

struct SoapyRfConfig {
    bool enabled{true};
    std::string driver;
    std::string device_args;
    std::string sensor_id{"soapy-sensor"};
    std::string session_id{"soapy-live"};
    std::uint64_t center_frequency_hz{100'000'000};
    std::uint64_t sample_rate_hz{2'000'000};
    double gain_db{20.0};
    std::size_t fft_size{2048};
    double max_fps{5.0};
    double calibration_offset_db{0.0};
    std::string audio_udp_address{"127.0.0.1"};
    std::uint16_t audio_udp_port{9998};
    int audio_sample_rate_hz{48'000};
};

class SoapyRfSource final : public IRfSource {
public:
    SoapyRfSource(SoapyRfConfig config, SourceType source_type);
    ~SoapyRfSource() override;

    static bool deviceAvailable(const std::string& driver, const std::string& device_args = {});

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
    [[nodiscard]] bool supportsNativeAudio() const override { return true; }
    std::string startNativeAudio(const std::string& demodulator, int audio_sample_rate, double volume) override;
    std::string stopNativeAudio() override;

private:
    struct Impl;
    void processAudio(const std::vector<std::complex<float>>& samples);
    void setError(const std::string& message);

    SoapyRfConfig config_;
    SourceType source_type_;
    std::unique_ptr<Impl> impl_;
    mutable std::mutex mutex_;
    SourceStatus status_;
    std::string device_model_{"unknown"};
    std::string source_device_;
    std::uint64_t sequence_{0};
    std::optional<IqFrame> latest_iq_;
    dsp::FftProcessor fft_;
    dsp::FrameRateLimiter limiter_;
    dsp::CalibrationProcessor calibration_;
    bool audio_enabled_{false};
    std::string audio_mode_{"NFM"};
    double audio_volume_{1.0};
    std::complex<float> previous_sample_{1.0F, 0.0F};
    double audio_phase_{0.0};
    double audio_dc_{0.0};
    double audio_resample_accumulator_{0.0};
    double audio_integrator_{0.0};
    std::size_t audio_integrator_samples_{0};
};

}  // namespace rf_agent

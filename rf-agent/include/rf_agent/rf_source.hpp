#pragma once

#include "rf_agent/models.hpp"

#include <cstdint>
#include <optional>
#include <string>

namespace rf_agent {

enum class SourceState { Disabled, NotInitialized, Ready, Running, Paused, Stopped, Error };

std::string to_string(SourceState state);

struct SourceStatus {
    SourceType backend{SourceType::Unknown};
    SourceState state{SourceState::NotInitialized};
    bool enabled{true};
    bool available{false};
    std::string message;
    std::uint64_t frames_produced{0};
    std::uint64_t frames_dropped{0};
};

struct SourceCapabilities {
    bool spectrum{false};
    bool iq{false};
    bool tuning{false};
    bool sample_rate_control{false};
    bool gain_control{false};
    bool recording{false};
    std::uint64_t minimum_frequency_hz{0};
    std::uint64_t maximum_frequency_hz{0};
    std::size_t maximum_spectrum_points{0};
    bool viewport_control{false};
};

class IRfSource {
public:
    virtual ~IRfSource() = default;

    virtual bool initialize() = 0;
    virtual bool start() = 0;
    virtual void stop() = 0;

    [[nodiscard]] virtual SourceStatus status() const = 0;
    [[nodiscard]] virtual SourceCapabilities capabilities() const = 0;

    virtual bool setCenterFrequency(std::uint64_t frequency_hz) = 0;
    virtual bool setSampleRate(std::uint64_t sample_rate_hz) = 0;
    virtual bool setGain(double gain_db) = 0;
    virtual bool setSpan(std::uint64_t span_hz) = 0;
    virtual bool setSpectrumPointCount(std::size_t point_count) = 0;

    virtual std::optional<SpectrumFrame> readSpectrumFrame() = 0;
    virtual std::optional<IqFrame> readIqFrame() = 0;

    // IQ-capable sources may provide local audio demodulation without the
    // optional external SDRangel control plane.
    [[nodiscard]] virtual bool supportsNativeAudio() const { return false; }
    virtual std::string startNativeAudio(const std::string&, int, double) { return {}; }
    virtual std::string stopNativeAudio() { return {}; }
};

}  // namespace rf_agent

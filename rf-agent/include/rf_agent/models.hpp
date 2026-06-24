#pragma once

#include <complex>
#include <cstddef>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace rf_agent {

inline constexpr std::uint32_t kFrameSchemaVersion = 1;
inline constexpr std::size_t kDefaultMaxSpectrumPoints = 65'536;
inline constexpr std::size_t kDefaultMaxIqSamples = 4'194'304;

enum class SourceType { Mock, Replay, Aaronia, Usrp, Hackrf, Unknown };

std::string to_string(SourceType source_type);

struct FrameMetadata {
    std::optional<double> gain_db;
    std::optional<std::string> antenna;
    bool is_simulated{false};
    std::map<std::string, std::string> attributes;
};

struct FrameFlags {
    bool overflow{false};
    bool dropped{false};
    bool inaccurate{false};
};

struct SpectrumFrame {
    std::uint32_t schema_version{kFrameSchemaVersion};
    std::string sensor_id;
    SourceType source_type{SourceType::Unknown};
    std::string source_device;
    std::string device_model{"unknown"};
    std::string measurement_mode{"spectrum"};
    std::string session_id;
    std::string timestamp;
    std::uint64_t sequence{0};
    std::uint64_t center_frequency_hz{0};
    std::uint64_t start_frequency_hz{0};
    std::uint64_t stop_frequency_hz{0};
    std::uint64_t step_frequency_hz{0};
    std::uint64_t sample_rate_hz{0};
    double rbw_hz{0.0};
    std::size_t num_points{0};
    std::string power_unit{"dBm"};
    std::vector<double> powers_dbm;
    FrameFlags flags;
    FrameMetadata metadata;
};

struct IqFrame {
    std::uint32_t schema_version{kFrameSchemaVersion};
    std::string sensor_id;
    SourceType source_type{SourceType::Unknown};
    std::string source_device;
    std::string session_id;
    std::string timestamp;
    std::uint64_t sequence{0};
    std::uint64_t center_frequency_hz{0};
    std::uint64_t sample_rate_hz{0};
    std::vector<std::complex<float>> samples;
    FrameMetadata metadata;
};

struct ValidationResult {
    std::vector<std::string> errors;

    [[nodiscard]] bool valid() const noexcept { return errors.empty(); }
};

[[nodiscard]] ValidationResult validate_spectrum_frame(
    const SpectrumFrame& frame,
    std::size_t max_points = kDefaultMaxSpectrumPoints);

[[nodiscard]] ValidationResult validate_iq_frame(
    const IqFrame& frame,
    std::size_t max_samples = kDefaultMaxIqSamples);

class FrameSequenceValidator {
public:
    [[nodiscard]] ValidationResult validate(const SpectrumFrame& frame);
    [[nodiscard]] ValidationResult validate(const IqFrame& frame);
    void reset();
    void reset_session(const std::string& session_id);

private:
    [[nodiscard]] ValidationResult validate_and_update(
        const std::string& key,
        std::uint64_t sequence,
        ValidationResult result);

    std::unordered_map<std::string, std::uint64_t> last_sequences_;
};

// Compatibility adapter for the existing browser contract:
// [{"x": <MHz>, "y": <dBm>}, ...]
[[nodiscard]] std::string to_frontend_points_json(const SpectrumFrame& frame);

}  // namespace rf_agent

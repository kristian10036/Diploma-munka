#include "rf_agent/models.hpp"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <regex>
#include <sstream>
#include <utility>

namespace rf_agent {
namespace {

bool valid_timestamp(const std::string& value) {
    static const std::regex pattern(
        R"(^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]{1,9})?(Z|[+-][0-9]{2}:[0-9]{2})$)");
    std::smatch match;
    if (!std::regex_match(value, match, pattern)) {
        return false;
    }
    const int year = std::stoi(match[1]);
    const int month = std::stoi(match[2]);
    const int day = std::stoi(match[3]);
    const int hour = std::stoi(match[4]);
    const int minute = std::stoi(match[5]);
    const int second = std::stoi(match[6]);
    if (year < 1970 || month < 1 || month > 12 || hour > 23 || minute > 59 || second > 60) {
        return false;
    }
    static const int days[] = {0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    int max_day = days[month];
    const bool leap = (year % 4 == 0 && year % 100 != 0) || year % 400 == 0;
    if (month == 2 && leap) {
        max_day = 29;
    }
    if (day < 1 || day > max_day) {
        return false;
    }
    if (match[8] != "Z") {
        const std::string zone = match[8];
        if (std::stoi(zone.substr(1, 2)) > 23 || std::stoi(zone.substr(4, 2)) > 59) {
            return false;
        }
    }
    return true;
}

void validate_common(
    std::uint32_t schema_version,
    const std::string& sensor_id,
    SourceType source_type,
    const std::string& source_device,
    const std::string& session_id,
    const std::string& timestamp,
    ValidationResult& result) {
    if (schema_version != kFrameSchemaVersion) result.errors.emplace_back("unsupported schema_version");
    if (sensor_id.empty()) result.errors.emplace_back("sensor_id is required");
    if (source_type == SourceType::Unknown) result.errors.emplace_back("source_type is required");
    if (source_device.empty()) result.errors.emplace_back("source_device is required");
    if (session_id.empty()) result.errors.emplace_back("session_id is required");
    if (!valid_timestamp(timestamp)) result.errors.emplace_back("timestamp must be ISO-8601 with timezone");
}

std::string sequence_key(
    const std::string& sensor_id,
    const std::string& session_id,
    SourceType source_type) {
    return sensor_id + "\x1f" + session_id + "\x1f" + to_string(source_type);
}

}  // namespace

std::string to_string(SourceType source_type) {
    switch (source_type) {
        case SourceType::Mock: return "mock";
        case SourceType::Replay: return "replay";
        case SourceType::Aaronia: return "aaronia";
        case SourceType::Usrp: return "usrp";
        case SourceType::Hackrf: return "hackrf";
        case SourceType::Unknown: return "unknown";
    }
    return "unknown";
}

ValidationResult validate_spectrum_frame(const SpectrumFrame& frame, std::size_t max_points) {
    ValidationResult result;
    validate_common(frame.schema_version, frame.sensor_id, frame.source_type, frame.source_device,
                    frame.session_id, frame.timestamp, result);
    if (frame.device_model.empty()) result.errors.emplace_back("device_model is required");
    if (frame.measurement_mode.empty()) result.errors.emplace_back("measurement_mode is required");
    if (frame.num_points == 0) result.errors.emplace_back("num_points must be positive");
    if (frame.step_frequency_hz == 0) result.errors.emplace_back("step_frequency_hz must be positive");
    if (frame.start_frequency_hz >= frame.stop_frequency_hz) {
        result.errors.emplace_back("start_frequency_hz must be lower than stop_frequency_hz");
    }
    if (frame.num_points > 0 && frame.step_frequency_hz > 0) {
        const auto intervals = frame.num_points - 1;
        if (intervals > (std::numeric_limits<std::uint64_t>::max() - frame.start_frequency_hz) /
                            frame.step_frequency_hz ||
            frame.start_frequency_hz + frame.step_frequency_hz * intervals != frame.stop_frequency_hz) {
            result.errors.emplace_back("stop_frequency_hz must equal start + step * (num_points - 1)");
        }
    }
    if (frame.center_frequency_hz < frame.start_frequency_hz ||
        frame.center_frequency_hz > frame.stop_frequency_hz) {
        result.errors.emplace_back("center_frequency_hz must be inside the frame range");
    }
    if (frame.sample_rate_hz == 0) result.errors.emplace_back("sample_rate_hz must be positive");
    if (!std::isfinite(frame.rbw_hz) || frame.rbw_hz <= 0.0) {
        result.errors.emplace_back("rbw_hz must be finite and positive");
    }
    if (frame.powers_dbm.size() != frame.num_points) {
        result.errors.emplace_back("powers_dbm size must equal num_points");
    }
    if (frame.num_points > max_points) result.errors.emplace_back("spectrum frame is too large");
    if (frame.power_unit != "dBm") result.errors.emplace_back("power_unit must be dBm");
    if (std::any_of(frame.powers_dbm.begin(), frame.powers_dbm.end(),
                    [](double value) { return !std::isfinite(value); })) {
        result.errors.emplace_back("power contains NaN or Infinity");
    }
    return result;
}

ValidationResult validate_iq_frame(const IqFrame& frame, std::size_t max_samples) {
    ValidationResult result;
    validate_common(frame.schema_version, frame.sensor_id, frame.source_type, frame.source_device,
                    frame.session_id, frame.timestamp, result);
    if (frame.center_frequency_hz == 0) result.errors.emplace_back("center_frequency_hz must be positive");
    if (frame.sample_rate_hz == 0) result.errors.emplace_back("sample_rate_hz must be positive");
    if (frame.samples.empty()) result.errors.emplace_back("IQ samples must not be empty");
    if (frame.samples.size() > max_samples) result.errors.emplace_back("IQ frame is too large");
    if (std::any_of(frame.samples.begin(), frame.samples.end(), [](const std::complex<float>& sample) {
            return !std::isfinite(sample.real()) || !std::isfinite(sample.imag());
        })) {
        result.errors.emplace_back("IQ samples contain NaN or Infinity");
    }
    return result;
}

ValidationResult FrameSequenceValidator::validate(const SpectrumFrame& frame) {
    return validate_and_update(sequence_key(frame.sensor_id, frame.session_id, frame.source_type),
                               frame.sequence, validate_spectrum_frame(frame));
}

ValidationResult FrameSequenceValidator::validate(const IqFrame& frame) {
    return validate_and_update(sequence_key(frame.sensor_id, frame.session_id, frame.source_type),
                               frame.sequence, validate_iq_frame(frame));
}

ValidationResult FrameSequenceValidator::validate_and_update(
    const std::string& key, std::uint64_t sequence, ValidationResult result) {
    const auto found = last_sequences_.find(key);
    if (found != last_sequences_.end() && sequence <= found->second) {
        result.errors.emplace_back("sequence must increase within a source session");
    }
    if (result.valid()) last_sequences_[key] = sequence;
    return result;
}

void FrameSequenceValidator::reset() { last_sequences_.clear(); }

void FrameSequenceValidator::reset_session(const std::string& session_id) {
    const std::string token = "\x1f" + session_id + "\x1f";
    for (auto iterator = last_sequences_.begin(); iterator != last_sequences_.end();) {
        if (iterator->first.find(token) != std::string::npos) iterator = last_sequences_.erase(iterator);
        else ++iterator;
    }
}

std::string to_frontend_points_json(const SpectrumFrame& frame) {
    std::ostringstream output;
    output << '[' << std::fixed << std::setprecision(6);
    const std::size_t count = std::min(frame.num_points, frame.powers_dbm.size());
    for (std::size_t index = 0; index < count; ++index) {
        if (index > 0) output << ',';
        const auto frequency_hz = frame.start_frequency_hz + frame.step_frequency_hz * index;
        output << "{\"x\":" << static_cast<double>(frequency_hz) / 1'000'000.0
               << ",\"y\":" << std::setprecision(2) << frame.powers_dbm[index]
               << std::setprecision(6) << '}';
    }
    output << ']';
    return output.str();
}

}  // namespace rf_agent

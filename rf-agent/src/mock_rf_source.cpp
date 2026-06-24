#include "rf_agent/mock_rf_source.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <ctime>
#include <iomanip>
#include <limits>
#include <sstream>
#include <utility>

namespace rf_agent {
namespace {

double add_dbm(double first_dbm, double second_dbm) {
    const double milliwatts = std::pow(10.0, first_dbm / 10.0) +
                              std::pow(10.0, second_dbm / 10.0);
    return 10.0 * std::log10(milliwatts);
}

}  // namespace

MockRfSource::MockRfSource(MockRfConfig config)
    : config_(std::move(config)), random_(config_.random_seed) {
    status_.backend = SourceType::Mock;
    status_.state = SourceState::NotInitialized;
    status_.enabled = true;
    status_.message = "Mock source is not initialized";
}

bool MockRfSource::initialize() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (config_.sensor_id.empty() || config_.session_id.empty()) {
        setError("sensor_id and session_id are required");
        return false;
    }
    if (config_.start_frequency_hz >= config_.stop_frequency_hz ||
        config_.point_count < 2 || config_.point_count > kDefaultMaxSpectrumPoints ||
        config_.sample_rate_hz == 0 || !std::isfinite(config_.noise_floor_dbm) ||
        !std::isfinite(config_.noise_deviation_db) || config_.noise_deviation_db < 0.0 ||
        !std::isfinite(config_.max_fps) || config_.max_fps <= 0.0) {
        setError("Invalid mock source configuration");
        return false;
    }
    random_.seed(config_.random_seed);
    sequence_ = 0;
    status_.state = SourceState::Ready;
    status_.available = true;
    status_.frames_produced = 0;
    status_.message = "Mock source ready";
    return true;
}

bool MockRfSource::start() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (status_.state != SourceState::Ready && status_.state != SourceState::Stopped) {
        return false;
    }
    status_.state = SourceState::Running;
    status_.available = true;
    status_.message = "Mock source running";
    return true;
}

void MockRfSource::stop() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (status_.state == SourceState::Running || status_.state == SourceState::Ready) {
        status_.state = SourceState::Stopped;
        status_.message = "Mock source stopped";
    }
}

SourceStatus MockRfSource::status() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return status_;
}

SourceCapabilities MockRfSource::capabilities() const {
    auto capabilities = SourceCapabilities{
        true, false, true, true, true, false,
        1, 24'000'000'000ULL, kDefaultMaxSpectrumPoints};
    capabilities.viewport_control = true;
    return capabilities;
}

bool MockRfSource::setCenterFrequency(std::uint64_t frequency_hz) {
    std::lock_guard<std::mutex> lock(mutex_);
    const std::uint64_t span = config_.stop_frequency_hz - config_.start_frequency_hz;
    const std::uint64_t half_span = span / 2;
    if (frequency_hz <= half_span || frequency_hz > std::numeric_limits<std::uint64_t>::max() - half_span) {
        return false;
    }
    config_.start_frequency_hz = frequency_hz - half_span;
    config_.stop_frequency_hz = config_.start_frequency_hz + span;
    return true;
}

bool MockRfSource::setSampleRate(std::uint64_t sample_rate_hz) {
    if (sample_rate_hz == 0) return false;
    std::lock_guard<std::mutex> lock(mutex_);
    config_.sample_rate_hz = sample_rate_hz;
    return true;
}

bool MockRfSource::setGain(double gain_db) {
    if (!std::isfinite(gain_db)) return false;
    std::lock_guard<std::mutex> lock(mutex_);
    config_.gain_db = gain_db;
    return true;
}

bool MockRfSource::setSpan(std::uint64_t span_hz) {
    if (span_hz == 0 || span_hz >= 24'000'000'000ULL) return false;
    std::lock_guard<std::mutex> lock(mutex_);
    const auto center = config_.start_frequency_hz + (config_.stop_frequency_hz - config_.start_frequency_hz) / 2;
    const auto left = span_hz / 2;
    if (center <= left || center > 24'000'000'000ULL - (span_hz - left)) return false;
    config_.start_frequency_hz = center - left;
    config_.stop_frequency_hz = config_.start_frequency_hz + span_hz;
    config_.sample_rate_hz = span_hz;
    return true;
}

bool MockRfSource::setSpectrumPointCount(std::size_t point_count) {
    if (point_count < 2 || point_count > kDefaultMaxSpectrumPoints) return false;
    std::lock_guard<std::mutex> lock(mutex_);
    config_.point_count = point_count;
    return true;
}

std::optional<SpectrumFrame> MockRfSource::readSpectrumFrame() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (status_.state != SourceState::Running) return std::nullopt;

    SpectrumFrame frame;
    frame.sensor_id = config_.sensor_id;
    frame.source_type = SourceType::Mock;
    frame.source_device = "mock-generator";
    frame.session_id = config_.session_id;
    frame.timestamp = nowIso8601();
    frame.sequence = sequence_;
    frame.start_frequency_hz = config_.start_frequency_hz;
    frame.step_frequency_hz =
        (config_.stop_frequency_hz - config_.start_frequency_hz) / (config_.point_count - 1);
    frame.stop_frequency_hz =
        frame.start_frequency_hz + frame.step_frequency_hz * (config_.point_count - 1);
    frame.center_frequency_hz = config_.start_frequency_hz +
                                (config_.stop_frequency_hz - config_.start_frequency_hz) / 2;
    frame.sample_rate_hz = config_.sample_rate_hz;
    const double span = static_cast<double>(frame.stop_frequency_hz - frame.start_frequency_hz);
    const double bin_width = static_cast<double>(frame.step_frequency_hz);
    frame.rbw_hz = bin_width;
    frame.num_points = config_.point_count;
    frame.powers_dbm.reserve(config_.point_count);

    std::normal_distribution<double> noise(0.0, config_.noise_deviation_db);
    for (std::size_t index = 0; index < config_.point_count; ++index) {
        frame.powers_dbm.push_back(config_.noise_floor_dbm + config_.gain_db + noise(random_));
    }

    // Stable narrowband carrier.
    addSignal(frame, static_cast<double>(config_.start_frequency_hz) + span * 0.37,
              -43.0 + config_.gain_db, bin_width * 1.5);
    // Moving narrowband carrier with changing amplitude.
    const double phase = static_cast<double>(sequence_) * 0.11;
    addSignal(frame, static_cast<double>(frame.center_frequency_hz) + std::sin(phase) * span * 0.18,
              -52.0 + std::sin(phase * 1.7) * 6.0 + config_.gain_db, bin_width * 2.0);
    // Broadband signal.
    addSignal(frame, static_cast<double>(config_.start_frequency_hz) + span * 0.68,
              -70.0 + std::sin(phase * 0.4) * 3.0 + config_.gain_db, span * 0.065);
    // Independently varying narrowband signal.
    addSignal(frame, static_cast<double>(config_.start_frequency_hz) + span * 0.84,
              -58.0 + std::sin(phase * 2.3) * 9.0 + config_.gain_db, bin_width * 2.5);
    // Short burst for three frames in every twenty-frame cycle.
    if (sequence_ % 20 < 3) {
        addSignal(frame, static_cast<double>(config_.start_frequency_hz) + span * 0.22,
                  -32.0 + config_.gain_db, bin_width * 1.2);
        frame.metadata.attributes["burst_active"] = "true";
    } else {
        frame.metadata.attributes["burst_active"] = "false";
    }

    frame.metadata.gain_db = config_.gain_db;
    frame.metadata.antenna = "SIMULATED";
    frame.metadata.is_simulated = true;
    frame.metadata.attributes["generator"] = "multi-signal-v1";
    frame.metadata.attributes["max_fps"] = std::to_string(config_.max_fps);

    const ValidationResult validation = validate_spectrum_frame(frame);
    if (!validation.valid()) {
        setError("Generated mock frame failed validation: " + validation.errors.front());
        return std::nullopt;
    }
    ++sequence_;
    ++status_.frames_produced;
    return frame;
}

std::optional<IqFrame> MockRfSource::readIqFrame() { return std::nullopt; }

void MockRfSource::addSignal(
    SpectrumFrame& frame, double center_hz, double peak_dbm, double sigma_hz) const {
    if (sigma_hz <= 0.0) return;
    for (std::size_t index = 0; index < frame.num_points; ++index) {
        const double frequency_hz = static_cast<double>(frame.start_frequency_hz) +
                                    static_cast<double>(frame.step_frequency_hz) * index;
        const double offset = (frequency_hz - center_hz) / sigma_hz;
        if (std::abs(offset) > 6.0) continue;
        const double attenuation_db = (offset * offset) * 4.342944819;
        frame.powers_dbm[index] = add_dbm(frame.powers_dbm[index], peak_dbm - attenuation_db);
    }
}

std::string MockRfSource::nowIso8601() const {
    const auto now = std::chrono::system_clock::now();
    const auto milliseconds = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()) % 1000;
    const std::time_t time = std::chrono::system_clock::to_time_t(now);
    std::tm utc{};
    gmtime_r(&time, &utc);
    std::ostringstream output;
    output << std::put_time(&utc, "%Y-%m-%dT%H:%M:%S") << '.'
           << std::setfill('0') << std::setw(3) << milliseconds.count() << 'Z';
    return output.str();
}

void MockRfSource::setError(std::string message) {
    status_.state = SourceState::Error;
    status_.available = false;
    status_.message = std::move(message);
}

}  // namespace rf_agent

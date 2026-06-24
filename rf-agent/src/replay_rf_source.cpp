#include "rf_agent/replay_rf_source.hpp"

#include <nlohmann/json.hpp>
#include <openssl/evp.h>
#include <zstd.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <ctime>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <utility>

namespace rf_agent {
namespace {

using Json = nlohmann::json;

SourceType parse_source_type(const std::string& value) {
    if (value == "mock") return SourceType::Mock;
    if (value == "replay") return SourceType::Replay;
    if (value == "aaronia") return SourceType::Aaronia;
    if (value == "usrp") return SourceType::Usrp;
    if (value == "hackrf") return SourceType::Hackrf;
    return SourceType::Unknown;
}

bool allowed_speed(double speed) {
    static constexpr std::array<double, 4> allowed{0.5, 1.0, 2.0, 5.0};
    return std::find(allowed.begin(), allowed.end(), speed) != allowed.end();
}

std::optional<double> timestamp_ms(const std::string& value) {
    if (value.size() < 20 || value.back() != 'Z') return std::nullopt;
    std::tm parsed{};
    std::istringstream input(value.substr(0, 19));
    input >> std::get_time(&parsed, "%Y-%m-%dT%H:%M:%S");
    if (input.fail()) return std::nullopt;
    double fractional_ms = 0.0;
    if (value.size() > 20 && value[19] == '.') {
        const std::string fraction = value.substr(20, value.size() - 21);
        if (fraction.empty() || fraction.find_first_not_of("0123456789") != std::string::npos) return std::nullopt;
        fractional_ms = std::stod("0." + fraction) * 1000.0;
    }
    const std::time_t seconds = timegm(&parsed);
    if (seconds < 0) return std::nullopt;
    return static_cast<double>(seconds) * 1000.0 + fractional_ms;
}

double frame_delay_ms(const SpectrumFrame& current, const SpectrumFrame* next, double fallback) {
    if (!next) return fallback;
    const auto current_ms = timestamp_ms(current.timestamp);
    const auto next_ms = timestamp_ms(next->timestamp);
    if (!current_ms || !next_ms) return fallback;
    const double difference = *next_ms - *current_ms;
    return std::isfinite(difference) && difference >= 0.0 && difference <= 3600000.0
        ? difference : fallback;
}

std::string sha256_file(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("Cannot open frame file for checksum");
    EVP_MD_CTX* context = EVP_MD_CTX_new();
    if (context == nullptr) throw std::runtime_error("Cannot allocate SHA-256 context");
    std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
    unsigned int digest_size = 0;
    std::array<char, 64 * 1024> buffer{};
    bool ok = EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1;
    while (ok && input) {
        input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
        const std::streamsize count = input.gcount();
        if (count > 0) {
            ok = EVP_DigestUpdate(context, buffer.data(), static_cast<std::size_t>(count)) == 1;
        }
    }
    ok = ok && EVP_DigestFinal_ex(context, digest.data(), &digest_size) == 1;
    EVP_MD_CTX_free(context);
    if (!ok) throw std::runtime_error("SHA-256 calculation failed");
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for (unsigned int index = 0; index < digest_size; ++index) {
        output << std::setw(2) << static_cast<unsigned int>(digest[index]);
    }
    return output.str();
}

SpectrumFrame parse_frame(const Json& value) {
    SpectrumFrame frame;
    frame.schema_version = value.at("schema_version").get<std::uint32_t>();
    frame.sensor_id = value.at("sensor_id").get<std::string>();
    frame.source_type = parse_source_type(value.at("source_type").get<std::string>());
    frame.source_device = value.at("source_device").get<std::string>();
    frame.session_id = value.at("session_id").get<std::string>();
    frame.timestamp = value.at("timestamp").get<std::string>();
    frame.sequence = value.at("sequence").get<std::uint64_t>();
    frame.center_frequency_hz = value.at("center_frequency_hz").get<std::uint64_t>();
    frame.start_frequency_hz = value.at("start_frequency_hz").get<std::uint64_t>();
    frame.stop_frequency_hz = value.at("stop_frequency_hz").get<std::uint64_t>();
    frame.step_frequency_hz = value.value("step_frequency_hz", std::uint64_t{0});
    frame.sample_rate_hz = value.at("sample_rate_hz").get<std::uint64_t>();
    frame.rbw_hz = value.at("rbw_hz").get<double>();
    frame.powers_dbm = value.at("powers_dbm").get<std::vector<double>>();
    frame.num_points = value.value("num_points", frame.powers_dbm.size());
    frame.power_unit = value.value("power_unit", "dBm");
    if (frame.step_frequency_hz == 0 && frame.num_points > 1) {
        frame.step_frequency_hz =
            (frame.stop_frequency_hz - frame.start_frequency_hz) / (frame.num_points - 1);
        frame.stop_frequency_hz =
            frame.start_frequency_hz + frame.step_frequency_hz * (frame.num_points - 1);
    }
    if (value.contains("flags")) {
        const auto& flags = value.at("flags");
        frame.flags.overflow = flags.value("overflow", false);
        frame.flags.dropped = flags.value("dropped", false);
        frame.flags.inaccurate = flags.value("inaccurate", false);
    }
    const Json& metadata = value.at("metadata");
    frame.metadata.is_simulated = metadata.at("is_simulated").get<bool>();
    if (metadata.contains("gain_db")) frame.metadata.gain_db = metadata.at("gain_db").get<double>();
    if (metadata.contains("antenna")) frame.metadata.antenna = metadata.at("antenna").get<std::string>();
    return frame;
}

}  // namespace

ReplayRfSource::ReplayRfSource(ReplayRfConfig config) : config_(std::move(config)) {
    status_.backend = SourceType::Replay;
    status_.state = SourceState::NotInitialized;
    status_.message = "Replay source is not initialized";
}

bool ReplayRfSource::initialize() {
    std::lock_guard<std::mutex> lock(mutex_);
    frames_.clear();
    current_index_ = 0;
    playback_sequence_ = 0;
    status_.frames_produced = 0;
    status_.frames_dropped = 0;
    if (config_.recording_directory.empty() || config_.max_frames == 0 ||
        config_.max_line_bytes == 0 || config_.max_decompressed_bytes == 0 ||
        !allowed_speed(config_.speed)) {
        setError("Invalid replay configuration");
        return false;
    }
    if (!loadRecording()) return false;
    status_.state = SourceState::Ready;
    status_.available = true;
    status_.message = "Replay recording ready";
    return true;
}

bool ReplayRfSource::start() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (status_.state != SourceState::Ready && status_.state != SourceState::Stopped) return false;
    if (current_index_ >= frames_.size()) current_index_ = 0;
    status_.state = SourceState::Running;
    status_.available = true;
    status_.message = "Replay running";
    next_frame_at_ = std::chrono::steady_clock::now();
    return true;
}

void ReplayRfSource::stop() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (status_.state == SourceState::Running || status_.state == SourceState::Paused ||
        status_.state == SourceState::Ready) {
        status_.state = SourceState::Stopped;
        status_.message = "Replay stopped";
    }
}

bool ReplayRfSource::pause() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (status_.state != SourceState::Running) return false;
    status_.state = SourceState::Paused;
    status_.message = "Replay paused";
    return true;
}

bool ReplayRfSource::resume() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (status_.state != SourceState::Paused) return false;
    status_.state = SourceState::Running;
    status_.message = "Replay running";
    next_frame_at_ = std::chrono::steady_clock::now();
    return true;
}

bool ReplayRfSource::seek(std::size_t frame_index) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (frame_index >= frames_.size()) return false;
    current_index_ = frame_index;
    next_frame_at_ = std::chrono::steady_clock::now();
    return true;
}

bool ReplayRfSource::setPlaybackSpeed(double speed) {
    if (!allowed_speed(speed)) return false;
    std::lock_guard<std::mutex> lock(mutex_);
    config_.speed = speed;
    return true;
}

void ReplayRfSource::setLoop(bool loop) {
    std::lock_guard<std::mutex> lock(mutex_);
    config_.loop = loop;
}

SourceStatus ReplayRfSource::status() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return status_;
}

SourceCapabilities ReplayRfSource::capabilities() const {
    return SourceCapabilities{true, false, false, false, false, false,
                              0, 0, kDefaultMaxSpectrumPoints};
}

std::size_t ReplayRfSource::frameCount() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return frames_.size();
}

std::size_t ReplayRfSource::currentFrameIndex() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return current_index_;
}

double ReplayRfSource::playbackSpeed() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return config_.speed;
}

bool ReplayRfSource::setCenterFrequency(std::uint64_t) { return false; }
bool ReplayRfSource::setSampleRate(std::uint64_t) { return false; }
bool ReplayRfSource::setGain(double) { return false; }
bool ReplayRfSource::setSpan(std::uint64_t) { return false; }
bool ReplayRfSource::setSpectrumPointCount(std::size_t) { return false; }
std::optional<IqFrame> ReplayRfSource::readIqFrame() { return std::nullopt; }

std::optional<SpectrumFrame> ReplayRfSource::readSpectrumFrame() {
    std::unique_lock<std::mutex> lock(mutex_);
    if (status_.state != SourceState::Running) return std::nullopt;
    if (current_index_ >= frames_.size()) {
        if (config_.loop) current_index_ = 0;
        else {
            status_.state = SourceState::Stopped;
            status_.message = "Replay reached end of recording";
            return std::nullopt;
        }
    }
    const auto deadline = next_frame_at_;
    lock.unlock();
    std::this_thread::sleep_until(deadline);
    lock.lock();
    if (status_.state != SourceState::Running) return std::nullopt;

    SpectrumFrame frame = frames_[current_index_++];
    const SourceType original_type = frame.source_type;
    const std::uint64_t original_sequence = frame.sequence;
    frame.source_type = SourceType::Replay;
    frame.source_device = "replay:" + config_.recording_directory.filename().string();
    if (!config_.replay_session_id.empty()) frame.session_id = config_.replay_session_id;
    frame.sequence = playback_sequence_++;
    frame.metadata.attributes["replayed"] = "true";
    frame.metadata.attributes["original_source_type"] = to_string(original_type);
    frame.metadata.attributes["original_sequence"] = std::to_string(original_sequence);
    ++status_.frames_produced;
    const SpectrumFrame* next = current_index_ < frames_.size() ? &frames_[current_index_] : nullptr;
    const double original_delay_ms = frame_delay_ms(frames_[current_index_ - 1], next, frame_interval_ms_);
    const auto delay = std::chrono::duration<double, std::milli>(original_delay_ms / config_.speed);
    next_frame_at_ = std::chrono::steady_clock::now() +
                     std::chrono::duration_cast<std::chrono::steady_clock::duration>(delay);
    return frame;
}

bool ReplayRfSource::loadRecording() {
    try {
        const auto metadata_path = config_.recording_directory / "metadata.json";
        std::ifstream metadata_input(metadata_path);
        if (!metadata_input) throw std::runtime_error("metadata.json is missing");
        Json metadata;
        metadata_input >> metadata;
        if (metadata.at("schema_version").get<int>() != 1) {
            throw std::runtime_error("Unsupported recording schema_version");
        }
        const std::string frame_file = metadata.value("frame_file", "frames.ndjson.zst");
        frame_interval_ms_ = metadata.value("frame_interval_ms", 200.0);
        if (!std::isfinite(frame_interval_ms_) || frame_interval_ms_ < 0.0) {
            throw std::runtime_error("Invalid frame_interval_ms");
        }
        const auto frame_path = config_.recording_directory / frame_file;
        if (!std::filesystem::is_regular_file(frame_path)) {
            throw std::runtime_error("Recording frame file is missing");
        }
        if (!verifyChecksum(frame_path)) throw std::runtime_error("Recording checksum mismatch");
        if (!parseFrames(readFrameData(frame_path))) return false;
        const std::size_t expected_count = metadata.value("frame_count", frames_.size());
        if (expected_count != frames_.size() + status_.frames_dropped) {
            throw std::runtime_error("Recording frame_count mismatch");
        }
        return true;
    } catch (const std::exception& error) {
        setError(error.what());
        return false;
    }
}

bool ReplayRfSource::verifyChecksum(const std::filesystem::path& frame_path) const {
    std::ifstream checksum_input(config_.recording_directory / "checksum.sha256");
    if (!checksum_input) throw std::runtime_error("checksum.sha256 is missing");
    std::string expected;
    checksum_input >> expected;
    return expected.size() == 64 && expected == sha256_file(frame_path);
}

bool ReplayRfSource::parseFrames(const std::string& ndjson) {
    std::istringstream input(ndjson);
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        if (line.size() > config_.max_line_bytes) {
            ++status_.frames_dropped;
            continue;
        }
        if (frames_.size() >= config_.max_frames) {
            setError("Recording exceeds max_frames");
            return false;
        }
        try {
            SpectrumFrame frame = parse_frame(Json::parse(line));
            if (!validate_spectrum_frame(frame).valid()) {
                ++status_.frames_dropped;
                continue;
            }
            frames_.push_back(std::move(frame));
        } catch (const std::exception&) {
            ++status_.frames_dropped;
        }
    }
    if (frames_.empty()) {
        setError("Recording contains no valid spectrum frame");
        return false;
    }
    return true;
}

std::string ReplayRfSource::readFrameData(const std::filesystem::path& frame_path) const {
    std::ifstream input(frame_path, std::ios::binary);
    if (!input) throw std::runtime_error("Cannot open recording frame file");
    if (frame_path.extension() != ".zst") {
        std::ostringstream output;
        output << input.rdbuf();
        const std::string data = output.str();
        if (data.size() > config_.max_decompressed_bytes) {
            throw std::runtime_error("Recording exceeds max_decompressed_bytes");
        }
        return data;
    }

    ZSTD_DStream* stream = ZSTD_createDStream();
    if (stream == nullptr) throw std::runtime_error("Cannot create Zstandard decoder");
    const std::size_t init_result = ZSTD_initDStream(stream);
    if (ZSTD_isError(init_result)) {
        ZSTD_freeDStream(stream);
        throw std::runtime_error("Cannot initialize Zstandard decoder");
    }
    std::vector<char> input_buffer(ZSTD_DStreamInSize());
    std::vector<char> output_buffer(ZSTD_DStreamOutSize());
    std::string output;
    std::size_t last_result = 1;
    while (input) {
        input.read(input_buffer.data(), static_cast<std::streamsize>(input_buffer.size()));
        ZSTD_inBuffer source{input_buffer.data(), static_cast<std::size_t>(input.gcount()), 0};
        while (source.pos < source.size) {
            ZSTD_outBuffer destination{output_buffer.data(), output_buffer.size(), 0};
            last_result = ZSTD_decompressStream(stream, &destination, &source);
            if (ZSTD_isError(last_result)) {
                ZSTD_freeDStream(stream);
                throw std::runtime_error("Invalid Zstandard recording");
            }
            if (output.size() + destination.pos > config_.max_decompressed_bytes) {
                ZSTD_freeDStream(stream);
                throw std::runtime_error("Recording exceeds max_decompressed_bytes");
            }
            output.append(output_buffer.data(), destination.pos);
        }
    }
    ZSTD_freeDStream(stream);
    if (last_result != 0) throw std::runtime_error("Truncated Zstandard recording");
    return output;
}

void ReplayRfSource::setError(std::string message) {
    status_.state = SourceState::Error;
    status_.available = false;
    status_.message = std::move(message);
}

}  // namespace rf_agent

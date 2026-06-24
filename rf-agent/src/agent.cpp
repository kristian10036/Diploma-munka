#include "rf_agent/agent.hpp"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <nlohmann/json.hpp>
#include <sstream>
#include <stdexcept>
#include <system_error>
#include <utility>

namespace rf_agent {
namespace {

std::string env_string(const char* name, const std::string& fallback) {
    const char* value = std::getenv(name);
    return value == nullptr || *value == '\0' ? fallback : value;
}

std::uint64_t env_u64(const char* name, std::uint64_t fallback) {
    const std::string value = env_string(name, "");
    if (value.empty()) return fallback;
    std::size_t consumed = 0;
    const auto parsed = std::stoull(value, &consumed);
    if (consumed != value.size()) throw std::runtime_error(std::string("Invalid ") + name);
    return parsed;
}

std::int64_t env_i64(const char* name, std::int64_t fallback) {
    const std::string value = env_string(name, "");
    if (value.empty()) return fallback;
    std::size_t consumed = 0;
    const auto parsed = std::stoll(value, &consumed);
    if (consumed != value.size()) throw std::runtime_error(std::string("Invalid ") + name);
    return parsed;
}

double env_double(const char* name, double fallback) {
    const std::string value = env_string(name, "");
    if (value.empty()) return fallback;
    std::size_t consumed = 0;
    const double parsed = std::stod(value, &consumed);
    if (consumed != value.size()) throw std::runtime_error(std::string("Invalid ") + name);
    return parsed;
}

bool env_bool(const char* name, bool fallback) {
    std::string value = env_string(name, fallback ? "true" : "false");
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char character) {
        return static_cast<char>(std::tolower(character));
    });
    if (value == "1" || value == "true" || value == "yes" || value == "on") return true;
    if (value == "0" || value == "false" || value == "no" || value == "off") return false;
    throw std::runtime_error(std::string("Invalid ") + name);
}

}  // namespace

AgentConfig AgentConfig::fromEnvironment() {
    AgentConfig config;
    config.bind_address = env_string("RF_AGENT_BIND_ADDRESS", config.bind_address);
    const std::uint64_t port = env_u64("RF_AGENT_PORT", config.port);
    if (port == 0 || port > 65535) throw std::runtime_error("Invalid RF_AGENT_PORT");
    config.port = static_cast<std::uint16_t>(port);
    config.source_mode = env_string("RF_SOURCE_MODE", config.source_mode);
    config.recordings_root = env_string("RF_RECORDINGS_ROOT", config.recordings_root.string());

    config.mock.sensor_id = env_string("RF_SENSOR_ID", config.mock.sensor_id);
    config.mock.session_id = env_string("RF_SESSION_ID", config.mock.session_id);
    config.mock.start_frequency_hz = env_u64("RF_START_FREQUENCY_HZ", config.mock.start_frequency_hz);
    config.mock.stop_frequency_hz = env_u64("RF_STOP_FREQUENCY_HZ", config.mock.stop_frequency_hz);
    config.mock.sample_rate_hz = env_u64("RF_SAMPLE_RATE_HZ", config.mock.sample_rate_hz);
    config.mock.point_count = static_cast<std::size_t>(env_u64("RF_MOCK_POINT_COUNT", config.mock.point_count));
    config.mock.noise_floor_dbm = env_double("RF_MOCK_NOISE_FLOOR_DBM", config.mock.noise_floor_dbm);
    config.mock.noise_deviation_db = env_double("RF_MOCK_NOISE_DEVIATION_DB", config.mock.noise_deviation_db);
    config.mock.gain_db = env_double("RF_GAIN_DB", config.mock.gain_db);
    config.mock.max_fps = env_double("FFT_MAX_FPS", config.mock.max_fps);
    config.mock.random_seed = static_cast<std::uint32_t>(env_u64("RF_MOCK_RANDOM_SEED", config.mock.random_seed));

    config.replay.recording_directory = env_string("RF_REPLAY_DIRECTORY", "");
    config.replay.replay_session_id = env_string("RF_SESSION_ID", "replay-session");
    config.replay.loop = env_bool("RF_REPLAY_LOOP", false);
    config.replay.speed = env_double("RF_REPLAY_SPEED", 1.0);

    config.aaronia_probe.enabled = env_bool("ENABLE_AARONIA", true);
    config.aaronia_probe.executable = env_string("AARONIA_PROBE_EXECUTABLE", config.aaronia_probe.executable);
    config.aaronia_probe.timeout = std::chrono::milliseconds(
        env_u64("AARONIA_PROBE_TIMEOUT_MS", config.aaronia_probe.timeout.count()));
    config.aaronia.enabled = config.aaronia_probe.enabled;
    config.aaronia.executable = env_string("AARONIA_WORKER_EXECUTABLE", config.aaronia.executable);
    config.aaronia.sensor_id = env_string("RF_SENSOR_ID", config.aaronia.sensor_id);
    config.aaronia.session_id = env_string("RF_SESSION_ID", config.aaronia.session_id);
    config.aaronia.start_frequency_hz =
        env_u64("AARONIA_START_FREQUENCY_HZ", config.aaronia.start_frequency_hz);
    config.aaronia.stop_frequency_hz =
        env_u64("AARONIA_STOP_FREQUENCY_HZ", config.aaronia.stop_frequency_hz);
    config.aaronia.receiver_clock =
        env_string("AARONIA_RECEIVER_CLOCK", config.aaronia.receiver_clock);
    config.aaronia.rbw_hz = env_double("AARONIA_RBW_HZ", config.aaronia.rbw_hz);
    config.aaronia.reference_level_dbm = env_double("AARONIA_REFERENCE_LEVEL_DBM", config.aaronia.reference_level_dbm);
    config.aaronia.maximum_points = static_cast<std::size_t>(env_u64("AARONIA_MAX_SPECTRUM_POINTS", config.aaronia.maximum_points));
    config.aaronia.maximum_fps = env_double("AARONIA_MAX_FPS", config.aaronia.maximum_fps);

    config.usrp_probe.enabled = env_bool("ENABLE_USRP", false);
    config.usrp_probe.executable = env_string("USRP_PROBE_EXECUTABLE", config.usrp_probe.executable);
    config.usrp_probe.device_args = env_string("USRP_DEVICE_ARGS", "");
    config.usrp_probe.timeout = std::chrono::milliseconds(
        env_u64("USRP_PROBE_TIMEOUT_MS", config.usrp_probe.timeout.count()));

    config.usrp.enabled = config.usrp_probe.enabled;
    config.usrp.driver = "uhd";
    config.usrp.device_args = config.usrp_probe.device_args;
    config.usrp.sensor_id = env_string("RF_SENSOR_ID", "usrp-auto");
    config.usrp.session_id = env_string("RF_SESSION_ID", "usrp-live");
    config.usrp.center_frequency_hz = env_u64("USRP_CENTER_FREQUENCY_HZ", 100'000'000);
    config.usrp.sample_rate_hz = env_u64("USRP_SAMPLE_RATE_HZ", 2'000'000);
    config.usrp.gain_db = env_double("USRP_GAIN_DB", 20.0);
    config.usrp.fft_size = static_cast<std::size_t>(env_u64("FFT_SIZE", 2048));
    config.usrp.max_fps = env_double("FFT_MAX_FPS", 5.0);
    config.usrp.calibration_offset_db = env_double("FFT_CALIBRATION_OFFSET_DB", 0.0);

    config.hackrf.enabled = env_bool("ENABLE_HACKRF", true);
    config.hackrf.driver = "hackrf";
    config.hackrf.device_args = env_string("HACKRF_DEVICE_ARGS", "");
    config.hackrf.sensor_id = env_string("RF_SENSOR_ID", "hackrf-auto");
    config.hackrf.session_id = env_string("RF_SESSION_ID", "hackrf-live");
    config.hackrf.center_frequency_hz = env_u64("HACKRF_CENTER_FREQUENCY_HZ", 100'000'000);
    config.hackrf.sample_rate_hz = env_u64("HACKRF_SAMPLE_RATE_HZ", 2'000'000);
    config.hackrf.gain_db = env_double("HACKRF_GAIN_DB", 20.0);
    config.hackrf.fft_size = static_cast<std::size_t>(env_u64("FFT_SIZE", 2048));
    config.hackrf.max_fps = env_double("FFT_MAX_FPS", 5.0);
    config.hackrf.calibration_offset_db = env_double("FFT_CALIBRATION_OFFSET_DB", 0.0);

    const auto audio_address = env_string("NATIVE_AUDIO_UDP_ADDRESS", "127.0.0.1");
    const auto audio_port = env_u64("SDRANGEL_AUDIO_UDP_PORT", 9998);
    const auto audio_rate = env_u64("SDRANGEL_AUDIO_SAMPLE_RATE_HZ", 48000);
    if (audio_port == 0 || audio_port > 65535 || audio_rate < 8000 || audio_rate > 192000) {
        throw std::runtime_error("Invalid native audio configuration");
    }
    for (auto* source : {&config.usrp, &config.hackrf}) {
        source->audio_udp_address = audio_address;
        source->audio_udp_port = static_cast<std::uint16_t>(audio_port);
        source->audio_sample_rate_hz = static_cast<int>(audio_rate);
    }

    config.automatic.usrp = config.usrp;
    config.automatic.hackrf = config.hackrf;
    config.automatic.aaronia = config.aaronia;
    config.automatic.poll_interval = std::chrono::milliseconds(env_u64("RF_HOTPLUG_POLL_MS", 5000));

    config.sdrangel.enabled = env_bool("SDRANGEL_ENABLED", false);
    config.sdrangel.api_url = env_string("SDRANGEL_API_URL", config.sdrangel.api_url);
    config.sdrangel.timeout = std::chrono::milliseconds(
        static_cast<std::uint64_t>(env_double("SDRANGEL_TIMEOUT_SECONDS", 5.0) * 1000.0));
    config.sdrangel.default_device_set_index = static_cast<int>(
        env_i64("SDRANGEL_DEVICE_SET_INDEX", config.sdrangel.default_device_set_index));
    config.sdrangel.device_settings_key = env_string("SDRANGEL_DEVICE_SETTINGS_KEY", "");
    config.sdrangel.data_plane_mode = env_string("SDRANGEL_DATA_PLANE_MODE", "not_configured");
    config.sdrangel.data_plane_endpoint = env_string("SDRANGEL_DATA_PLANE_ENDPOINT", "");
    config.sdrangel.iq_sample_format = env_string("SDRANGEL_IQ_SAMPLE_FORMAT", "cf32_le");
    config.sdrangel.iq_sample_rate_hz = env_u64("SDRANGEL_IQ_SAMPLE_RATE_HZ", 0);
    config.sdrangel.audio_udp_address = env_string(
        "SDRANGEL_AUDIO_UDP_ADDRESS", config.sdrangel.audio_udp_address);
    const std::uint64_t audio_udp_port = env_u64(
        "SDRANGEL_AUDIO_UDP_PORT", config.sdrangel.audio_udp_port);
    if (audio_udp_port == 0 || audio_udp_port > 65535) {
        throw std::runtime_error("Invalid SDRANGEL_AUDIO_UDP_PORT");
    }
    config.sdrangel.audio_udp_port = static_cast<std::uint16_t>(audio_udp_port);
    const std::uint64_t audio_udp_sample_rate = env_u64(
        "SDRANGEL_AUDIO_SAMPLE_RATE_HZ", config.sdrangel.audio_udp_sample_rate_hz);
    if (audio_udp_sample_rate < 8000 || audio_udp_sample_rate > 384000) {
        throw std::runtime_error("Invalid SDRANGEL_AUDIO_SAMPLE_RATE_HZ");
    }
    config.sdrangel.audio_udp_sample_rate_hz = static_cast<int>(audio_udp_sample_rate);
    return config;
}

SourceManager::SourceManager(AgentConfig config)
    : config_(std::move(config)), current_mode_(config_.source_mode),
      recording_writer_(config_.recordings_root),
      aaronia_probe_(config_.aaronia_probe),
      usrp_probe_(config_.usrp_probe),
      sdrangel_(config_.sdrangel) {}

SourceManager::~SourceManager() { stop(); }

bool SourceManager::initializeSelected() {
    std::optional<std::filesystem::path> recording;
    if (!config_.replay.recording_directory.empty()) recording = config_.replay.recording_directory;
    return select(current_mode_, recording);
}

bool SourceManager::select(
    const std::string& mode, const std::optional<std::filesystem::path>& recording) {
    auto candidate = createSource(mode, recording);
    if (!candidate || !candidate->initialize()) return false;
    stop();
    std::lock_guard<std::mutex> lock(mutex_);
    source_ = std::move(candidate);
    current_mode_ = mode;
    latest_frame_.reset();
    return true;
}

bool SourceManager::start() {
    stopProducer();
    std::shared_ptr<IRfSource> source;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        source = source_;
    }
    if (!source || !source->start()) return false;
    producer_running_.store(true);
    producer_thread_ = std::thread(&SourceManager::producerLoop, this);
    return true;
}

void SourceManager::stopProducer() {
    producer_running_.store(false);
    if (producer_thread_.joinable()) producer_thread_.join();
}

void SourceManager::stop() {
    producer_running_.store(false);
    std::shared_ptr<IRfSource> source;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        source = source_;
    }
    if (source) source->stop();
    if (producer_thread_.joinable()) producer_thread_.join();
}

void SourceManager::producerLoop() {
    const auto mock_interval = std::chrono::duration<double>(1.0 / std::max(0.1, config_.mock.max_fps));
    while (producer_running_.load()) {
        const auto started = std::chrono::steady_clock::now();
        std::shared_ptr<IRfSource> source;
        std::string mode;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            source = source_;
            mode = current_mode_;
        }
        if (!source) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            continue;
        }
        auto frame = source->readSpectrumFrame();
        if (frame) {
            std::lock_guard<std::mutex> lock(mutex_);
            latest_frame_ = *frame;
            if (recording_writer_.active() && !recording_writer_.append(*frame)) {
                // Writer retains the structured diagnostic in recording status.
            }
        } else {
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
        if (mode == "mock") {
            std::this_thread::sleep_until(
                started + std::chrono::duration_cast<std::chrono::steady_clock::duration>(mock_interval));
        }
    }
}

bool SourceManager::configure(
    const std::optional<std::uint64_t>& center_frequency_hz,
    const std::optional<std::uint64_t>& sample_rate_hz,
    const std::optional<double>& gain_db) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!source_) return false;
    if (center_frequency_hz && !source_->setCenterFrequency(*center_frequency_hz)) return false;
    if (sample_rate_hz && !source_->setSampleRate(*sample_rate_hz)) return false;
    if (gain_db && !source_->setGain(*gain_db)) return false;
    return center_frequency_hz.has_value() || sample_rate_hz.has_value() || gain_db.has_value();
}

bool SourceManager::configureViewport(std::uint64_t center_frequency_hz,
                                      std::uint64_t span_hz,
                                      std::size_t maximum_points) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!source_ || center_frequency_hz == 0 || span_hz == 0 || maximum_points < 2) return false;
    const auto capabilities = source_->capabilities();
    if (!capabilities.viewport_control || maximum_points > capabilities.maximum_spectrum_points) return false;
    if (auto aaronia = std::dynamic_pointer_cast<AaroniaRfSource>(source_)) {
        return aaronia->configureViewport(center_frequency_hz, span_hz, maximum_points);
    }
    if (auto automatic = std::dynamic_pointer_cast<AutoRfSource>(source_)) {
        return automatic->configureViewport(center_frequency_hz, span_hz, maximum_points);
    }
    if (!source_->setCenterFrequency(center_frequency_hz)) return false;
    if (!source_->setSpan(span_hz)) return false;
    return source_->setSpectrumPointCount(maximum_points);
}

bool SourceManager::replayPause() {
    std::lock_guard<std::mutex> lock(mutex_);
    auto replay = std::dynamic_pointer_cast<ReplayRfSource>(source_);
    return replay && replay->pause();
}

bool SourceManager::replayResume() {
    std::lock_guard<std::mutex> lock(mutex_);
    auto replay = std::dynamic_pointer_cast<ReplayRfSource>(source_);
    return replay && replay->resume();
}

bool SourceManager::replaySeek(std::size_t frame_index) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto replay = std::dynamic_pointer_cast<ReplayRfSource>(source_);
    latest_frame_.reset();
    return replay && replay->seek(frame_index);
}

bool SourceManager::replaySpeed(double speed) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto replay = std::dynamic_pointer_cast<ReplayRfSource>(source_);
    return replay && replay->setPlaybackSpeed(speed);
}

void SourceManager::replayLoop(bool loop) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto replay = std::dynamic_pointer_cast<ReplayRfSource>(source_);
    if (replay) replay->setLoop(loop);
}

bool SourceManager::recordingStart(const RecordingStartOptions& options) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!source_ || source_->status().state == SourceState::Error) return false;
    return recording_writer_.start(options);
}

std::optional<std::string> SourceManager::recordingStop() {
    std::lock_guard<std::mutex> lock(mutex_);
    return recording_writer_.stop();
}

std::string SourceManager::recordingStatus() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return recording_writer_.statusJson();
}

std::string SourceManager::recordingError() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return recording_writer_.lastError();
}

SourceStatus SourceManager::status() const {
    std::lock_guard<std::mutex> lock(mutex_);
    if (source_) return source_->status();
    return SourceStatus{SourceType::Unknown, SourceState::Disabled, true, false,
                        "Configured source is unavailable", 0, 0};
}

SourceCapabilities SourceManager::capabilities() const {
    std::lock_guard<std::mutex> lock(mutex_);
    auto capabilities = source_ ? source_->capabilities() : SourceCapabilities{};
    capabilities.recording = source_ && capabilities.spectrum;
    return capabilities;
}

std::string SourceManager::currentMode() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return current_mode_;
}

std::vector<std::filesystem::path> SourceManager::recordings() const {
    std::vector<std::filesystem::path> result;
    std::error_code error;
    if (!std::filesystem::is_directory(config_.recordings_root, error)) return result;
    for (const auto& entry : std::filesystem::directory_iterator(config_.recordings_root, error)) {
        if (entry.is_directory() && std::filesystem::is_regular_file(entry.path() / "metadata.json")) {
            result.push_back(entry.path().filename());
        }
    }
    std::sort(result.begin(), result.end());
    return result;
}

std::optional<std::string> SourceManager::recordingMetadata(const std::string& id) const {
    if (id.empty() || id.size() > 128) return std::nullopt;
    const auto directory = safeRecordingPath(id);
    if (!directory) return std::nullopt;
    const auto metadata_path = *directory / "metadata.json";
    std::error_code error;
    const auto size = std::filesystem::file_size(metadata_path, error);
    if (error || size == 0 || size > 1024 * 1024) return std::nullopt;
    std::ifstream input(metadata_path, std::ios::binary);
    if (!input) return std::nullopt;
    std::ostringstream content;
    content << input.rdbuf();
    return content.str();
}

std::optional<SpectrumFrame> SourceManager::readSpectrumFrame() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return latest_frame_;
}

std::string SourceManager::runAaroniaProbe() { return aaronia_probe_.run(); }
std::string SourceManager::aaroniaStatus() const { return aaronia_probe_.status(); }
std::string SourceManager::runUsrpProbe() { return usrp_probe_.run(); }
std::string SourceManager::usrpStatus() const { return usrp_probe_.status(); }
std::string SourceManager::hackrfStatus() const {
    const bool available = config_.hackrf.enabled &&
        SoapyRfSource::deviceAvailable("hackrf", config_.hackrf.device_args);
    return nlohmann::json{{"backend", "hackrf"}, {"enabled", config_.hackrf.enabled},
                          {"probe_attempted", true}, {"available", available},
                          {"probe_result", available ? "device_found" : (config_.hackrf.enabled ? "no_devices" : "disabled")},
                          {"data_plane", "soapy_iq_spectrum_native_audio"}}.dump();
}
std::string SourceManager::sdrangelStatus() const { return sdrangel_.status(); }
std::string SourceManager::sdrangelDeviceSets() const { return sdrangel_.deviceSets(); }
std::string SourceManager::sdrangelDevices() const { return sdrangel_.devices(); }
std::string SourceManager::sdrangelCreateDeviceSet(const std::string& hardware_type) const {
    return sdrangel_.createDeviceSet(hardware_type);
}
std::string SourceManager::sdrangelTune(std::uint64_t frequency, int index) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (source_ && source_->supportsNativeAudio()) {
            if (!source_->setCenterFrequency(frequency)) throw std::runtime_error("native IQ tuning failed");
            return nlohmann::json{{"status", "ok"}, {"native_iq", true},
                                  {"center_frequency_hz", frequency}, {"device_set_index", 0}}.dump();
        }
    }
    return sdrangel_.tune(frequency, index);
}
std::string SourceManager::sdrangelDemodStart(
    const std::string& demodulator, int index, std::int64_t offset, int audio_rate,
    int bandwidth_hz, double squelch_db, const std::string& audio_device,
    double volume) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (source_ && source_->supportsNativeAudio()) {
            return source_->startNativeAudio(demodulator, audio_rate, volume);
        }
    }
    return sdrangel_.startDemodulator(
        demodulator, index, offset, audio_rate, bandwidth_hz, squelch_db,
        audio_device, volume);
}
std::string SourceManager::sdrangelDemodStop(int index, int channel) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (source_ && source_->supportsNativeAudio()) return source_->stopNativeAudio();
    }
    return sdrangel_.stopDemodulator(index, channel);
}
std::string SourceManager::sdrangelDemodUpdate(
    const std::string& demodulator, int index, int channel,
    std::optional<std::int64_t> input_frequency_offset_hz,
    std::optional<int> bandwidth_hz, std::optional<double> squelch_db,
    std::optional<double> volume, std::optional<std::uint64_t> retune_device_center_hz) {
    return sdrangel_.updateDemodulator(
        demodulator, index, channel, input_frequency_offset_hz, bandwidth_hz,
        squelch_db, volume, retune_device_center_hz);
}

std::shared_ptr<IRfSource> SourceManager::createSource(
    const std::string& mode, const std::optional<std::filesystem::path>& recording) const {
    if (mode == "mock") return std::make_shared<MockRfSource>(config_.mock);
    if (mode == "auto") return std::make_shared<AutoRfSource>(config_.automatic);
    if (mode == "aaronia") return std::make_shared<AaroniaRfSource>(config_.aaronia);
    if (mode == "usrp") return std::make_shared<SoapyRfSource>(config_.usrp, SourceType::Usrp);
    if (mode == "hackrf") return std::make_shared<SoapyRfSource>(config_.hackrf, SourceType::Hackrf);
    if (mode == "replay") {
        if (!recording) return nullptr;
        const auto safe_path = safeRecordingPath(*recording);
        if (!safe_path) return nullptr;
        ReplayRfConfig replay_config = config_.replay;
        replay_config.recording_directory = *safe_path;
        return std::make_shared<ReplayRfSource>(std::move(replay_config));
    }
    // Remaining hardware data sources stay unavailable until an isolated
    // worker implements their real frame contract.
    return nullptr;
}

std::optional<std::filesystem::path> SourceManager::safeRecordingPath(
    const std::filesystem::path& requested) const {
    std::error_code error;
    const auto root = std::filesystem::weakly_canonical(config_.recordings_root, error);
    if (error) return std::nullopt;
    const auto candidate = std::filesystem::weakly_canonical(
        requested.is_absolute() ? requested : root / requested, error);
    if (error || !std::filesystem::is_directory(candidate)) return std::nullopt;
    const auto relative = std::filesystem::relative(candidate, root, error);
    if (error || relative.empty() || *relative.begin() == "..") return std::nullopt;
    return candidate;
}

}  // namespace rf_agent

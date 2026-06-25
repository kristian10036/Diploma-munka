#include "rf_agent/aaronia_rf_source.hpp"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <csignal>
#include <fcntl.h>
#include <filesystem>
#include <sys/wait.h>
#include <unistd.h>

namespace rf_agent {
namespace {
using Json = nlohmann::json;

// Hány egymást követő sikertelen worker-indítás után adjuk fel az aktuális
// (pl. viewport-zoom miatt kért) konfigurációt, és álljunk vissza az utolsó
// olyanra, amely valódi frame-et adott.
constexpr unsigned int kMaxConsecutiveFailuresBeforeFallback = 3;

// Megfigyelés (élesben tesztelve): egy viewport-váltás
// utáni AZONNALI worker-újraindítás konzisztensen "FunctionFailedException"-t
// dob az SDK belsejében, függetlenül a kért span/RBW értékektől -- ez nem egy
// konkrét rossz paraméter, hanem valószínűleg egy device-szintű erőforrás
// (USB/FPGA) felszabadulására váró race. Egy ~3 másodperces szünet a
// leállítás és az újraindítás között NEM oldotta meg élesben, ezért ide
// szándékosan NEM kerül ilyen várakozás vissza -- csak az API-hívás
// (RF_AGENT_TIMEOUT_SECONDS) időtúllépését okozná anélkül, hogy a tényleges
// hibát megszüntetné. A megoldás valószínűleg csak egy teljes
// rf-agent-konténer-/process-újraindítással érhető el (ez konzisztensen
// működött), amit a fallback logika nem tud kiváltani.


void child_environment(const AaroniaRfConfig& config) {
    const auto set = [](const char* name, const std::string& value) {
        setenv(name, value.c_str(), 1);
    };
    set("AARONIA_SENSOR_ID", config.sensor_id);
    set("AARONIA_SESSION_ID", config.session_id);
    set("AARONIA_START_FREQUENCY_HZ", std::to_string(config.start_frequency_hz));
    set("AARONIA_STOP_FREQUENCY_HZ", std::to_string(config.stop_frequency_hz));
    set("AARONIA_RECEIVER_CLOCK", config.receiver_clock);
    set("AARONIA_RBW_HZ", std::to_string(config.rbw_hz));
    set("AARONIA_REFERENCE_LEVEL_DBM", std::to_string(config.reference_level_dbm));
    set("AARONIA_MAX_SPECTRUM_POINTS", std::to_string(config.maximum_points));
    set("AARONIA_MAX_FPS", std::to_string(config.maximum_fps));
}
}

AaroniaRfSource::AaroniaRfSource(AaroniaRfConfig config) : config_(std::move(config)), last_good_config_(config_) {
    // Sequence numbers restart with the rf-agent process. Give each process a
    // distinct session key so downstream reconnects never mix sequence spaces.
    const auto epoch_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    config_.session_id += "-" + std::to_string(epoch_ms) + "-" + std::to_string(getpid());
    status_ = {SourceType::Aaronia, config_.enabled ? SourceState::NotInitialized : SourceState::Disabled,
               config_.enabled, false, config_.enabled ? "Aaronia worker not initialized" : "Aaronia disabled", 0, 0};
}

AaroniaRfSource::~AaroniaRfSource() { stop(); }

bool AaroniaRfSource::initialize() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!config_.enabled || !std::filesystem::is_regular_file(config_.executable) ||
        config_.start_frequency_hz == 0 ||
        config_.start_frequency_hz >= config_.stop_frequency_hz ||
        config_.stop_frequency_hz > 24'000'000'000ULL ||
        config_.receiver_clock.empty() ||
        config_.rbw_hz <= 0 ||
        config_.maximum_points < 2 || config_.maximum_points > kDefaultMaxSpectrumPoints) {
        status_.state = SourceState::Error;
        status_.available = false;
        status_.message = "Aaronia worker configuration is invalid";
        return false;
    }
    status_.state = SourceState::Ready;
    status_.available = true;
    status_.message = "Aaronia worker ready";
    return true;
}

bool AaroniaRfSource::launchLocked() {
    int pipe_fd[2]{};
    if (pipe(pipe_fd) != 0) return false;
    const pid_t child = fork();
    if (child < 0) {
        close(pipe_fd[0]); close(pipe_fd[1]);
        return false;
    }
    if (child == 0) {
        dup2(pipe_fd[1], STDOUT_FILENO);
        close(pipe_fd[0]); close(pipe_fd[1]);
        child_environment(config_);
        execl(config_.executable.c_str(), config_.executable.c_str(), nullptr);
        _exit(127);
    }
    close(pipe_fd[1]);
    fcntl(pipe_fd[0], F_SETFL, fcntl(pipe_fd[0], F_GETFL) | O_NONBLOCK);
    worker_pid_ = child;
    output_fd_ = pipe_fd[0];
    input_buffer_.clear();
    status_.state = SourceState::Running;
    status_.available = true;
    status_.message = "Aaronia worker running";
    return true;
}

bool AaroniaRfSource::start() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (status_.state != SourceState::Ready && status_.state != SourceState::Stopped &&
        status_.state != SourceState::Error) return false;
    stop_requested_ = false;
    restart_attempts_ = 0;
    return launchLocked();
}

void AaroniaRfSource::stopLocked() {
    stop_requested_ = true;
    if (worker_pid_ > 0) {
        kill(worker_pid_, SIGTERM);
        for (int attempt = 0; attempt < 50; ++attempt) {
            int state = 0;
            if (waitpid(worker_pid_, &state, WNOHANG) == worker_pid_) break;
            usleep(10'000);
        }
        int state = 0;
        if (waitpid(worker_pid_, &state, WNOHANG) == 0) {
            kill(worker_pid_, SIGKILL);
            waitpid(worker_pid_, &state, 0);
        }
    }
    worker_pid_ = -1;
    if (output_fd_ >= 0) close(output_fd_);
    output_fd_ = -1;
    input_buffer_.clear();
}

void AaroniaRfSource::stop() {
    std::lock_guard<std::mutex> lock(mutex_);
    stopLocked();
    status_.state = SourceState::Stopped;
    status_.message = "Aaronia worker stopped";
}

SourceStatus AaroniaRfSource::status() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return status_;
}

SourceCapabilities AaroniaRfSource::capabilities() const {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto minimum = hardware_min_frequency_hz_ > 0
        ? hardware_min_frequency_hz_ : std::uint64_t{5'000'000ULL};
    const auto maximum = hardware_max_frequency_hz_ > minimum
        ? hardware_max_frequency_hz_ : std::uint64_t{18'000'000'000ULL};
    return SourceCapabilities{true, false, true, false, true, true,
                              minimum, maximum,
                              kDefaultMaxSpectrumPoints, true};
}

bool AaroniaRfSource::setCenterFrequency(std::uint64_t frequency_hz) {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto current_span = config_.stop_frequency_hz - config_.start_frequency_hz;
    if (frequency_hz <= current_span / 2 ||
        frequency_hz > 24'000'000'000ULL - (current_span - current_span / 2)) {
        return false;
    }
    config_.start_frequency_hz = frequency_hz - current_span / 2;
    config_.stop_frequency_hz = config_.start_frequency_hz + current_span;
    return true;
}

bool AaroniaRfSource::setSampleRate(std::uint64_t) { return false; }

bool AaroniaRfSource::setGain(double gain_db) {
    if (!std::isfinite(gain_db) || gain_db < -120 || gain_db > 40) return false;
    std::lock_guard<std::mutex> lock(mutex_);
    config_.reference_level_dbm = gain_db;
    return true;
}

bool AaroniaRfSource::setSpan(std::uint64_t span_hz) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (span_hz == 0 || span_hz >= 24'000'000'000ULL) return false;
    const auto center = config_.start_frequency_hz +
        (config_.stop_frequency_hz - config_.start_frequency_hz) / 2;
    const auto left = span_hz / 2;
    if (center <= left || center > 24'000'000'000ULL - (span_hz - left)) return false;
    config_.start_frequency_hz = center - left;
    config_.stop_frequency_hz = config_.start_frequency_hz + span_hz;
    return true;
}

bool AaroniaRfSource::setSpectrumPointCount(std::size_t point_count) {
    if (point_count < 2 || point_count > kDefaultMaxSpectrumPoints) return false;
    std::lock_guard<std::mutex> lock(mutex_);
    config_.maximum_points = point_count;
    return true;
}

bool AaroniaRfSource::configureViewport(std::uint64_t center_frequency_hz,
                                        std::uint64_t span_hz,
                                        std::size_t point_count) {
    if (center_frequency_hz == 0 || span_hz == 0 ||
        point_count < 2 || point_count > kDefaultMaxSpectrumPoints) {
        return false;
    }

    const auto left = span_hz / 2;
    if (center_frequency_hz <= left ||
        center_frequency_hz > 24'000'000'000ULL - (span_hz - left)) {
        return false;
    }

    const auto requested_start = center_frequency_hz - left;
    const auto requested_stop = requested_start + span_hz;

    std::lock_guard<std::mutex> lock(mutex_);
    const auto minimum = hardware_min_frequency_hz_ > 0
        ? hardware_min_frequency_hz_ : std::uint64_t{5'000'000ULL};
    const auto maximum = hardware_max_frequency_hz_ > minimum
        ? hardware_max_frequency_hz_ : std::uint64_t{18'000'000'000ULL};
    if (requested_start < minimum || requested_stop > maximum) return false;

    config_.start_frequency_hz = requested_start;
    config_.stop_frequency_hz = requested_stop;
    config_.maximum_points = point_count;

    stopLocked();
    stop_requested_ = false;
    restart_attempts_ = 0;
    next_restart_ = std::chrono::steady_clock::time_point{};
    status_.state = SourceState::Ready;
    status_.available = true;
    status_.message = "Aaronia worker restarting with requested viewport";
    return launchLocked();
}

void AaroniaRfSource::noteExitLocked(int wait_status) {
    if (output_fd_ >= 0) close(output_fd_);
    output_fd_ = -1;
    worker_pid_ = -1;
    if (stop_requested_) return;
    ++restart_attempts_;
    std::string reason = WIFSIGNALED(wait_status)
        ? "Aaronia worker terminated by signal " + std::to_string(WTERMSIG(wait_status))
        : "Aaronia worker exited with code " + std::to_string(WIFEXITED(wait_status) ? WEXITSTATUS(wait_status) : -1);
    // Egy konkrét viewport (szűk span / finom RBW) ismételt SDK-crash-eket
    // okozhat -- ezt mi nem tudjuk megjavítani, csak elkerülni. Néhány
    // egymást követő sikertelen indítás után visszaállunk az utolsó, valódi
    // frame-et adó konfigurációra, hogy a forrás ne fagyjon le végtelenül, és
    // gyorsan (rövid backoff-fal) próbáljuk újra azzal.
    unsigned int seconds = 0;
    if (restart_attempts_ >= kMaxConsecutiveFailuresBeforeFallback) {
        config_ = last_good_config_;
        restart_attempts_ = 0;
        seconds = 5;
        reason += " (fallback: visszaallas az utolso mukodo viewportra)";
    } else {
        seconds = std::min(30U, 5U << std::min(restart_attempts_ - 1, 3U));
    }
    next_restart_ = std::chrono::steady_clock::now() + std::chrono::seconds(seconds);
    status_.state = SourceState::Error;
    status_.available = false;
    status_.message = reason;
}

std::optional<SpectrumFrame> AaroniaRfSource::parseLineLocked(const std::string& line) {
    try {
        const Json value = Json::parse(line);
        SpectrumFrame frame;
        frame.sensor_id = value.at("sensor_id").get<std::string>();
        frame.source_type = SourceType::Aaronia;
        frame.source_device = value.at("source_device").get<std::string>();
        frame.device_model = value.at("device_model").get<std::string>();
        frame.measurement_mode = value.at("measurement_mode").get<std::string>();
        frame.session_id = value.at("session_id").get<std::string>();
        frame.timestamp = value.at("timestamp").get<std::string>();
        frame.sequence = sequence_++;
        frame.center_frequency_hz = value.at("center_frequency_hz").get<std::uint64_t>();
        frame.start_frequency_hz = value.at("start_frequency_hz").get<std::uint64_t>();
        frame.stop_frequency_hz = value.at("stop_frequency_hz").get<std::uint64_t>();
        frame.step_frequency_hz = value.at("step_frequency_hz").get<std::uint64_t>();
        frame.sample_rate_hz = value.at("sample_rate_hz").get<std::uint64_t>();
        frame.rbw_hz = value.at("rbw_hz").get<double>();
        frame.powers_dbm = value.at("powers_dbm").get<std::vector<double>>();
        frame.num_points = frame.powers_dbm.size();
        frame.flags.overflow = value.value("overflow", false);
        frame.flags.dropped = value.value("dropped", false);
        frame.flags.inaccurate = value.value("inaccurate", false);
        const auto worker_dropped = value.value("worker_dropped_frames", std::uint64_t{0});
        hardware_min_frequency_hz_ = value.at("hardware_min_frequency_hz").get<std::uint64_t>();
        hardware_max_frequency_hz_ = value.at("hardware_max_frequency_hz").get<std::uint64_t>();
        frame.metadata.attributes["worker_dropped_frames"] = std::to_string(worker_dropped);
        frame.metadata.attributes["hardware_min_frequency_hz"] = std::to_string(value.at("hardware_min_frequency_hz").get<std::uint64_t>());
        frame.metadata.attributes["hardware_max_frequency_hz"] = std::to_string(value.at("hardware_max_frequency_hz").get<std::uint64_t>());
        frame.metadata.attributes["available_rtbw_hz"] = std::to_string(value.value("available_rtbw_hz", std::uint64_t{0}));
        const auto validation = validate_spectrum_frame(frame);
        if (!validation.valid()) {
            ++status_.frames_dropped;
            status_.message = "Aaronia worker emitted an invalid frame: " + validation.errors.front();
            return std::nullopt;
        }
        status_.state = SourceState::Running;
        status_.available = true;
        status_.message = "Aaronia live spectrum streaming";
        ++status_.frames_produced;
        if (worker_dropped >= worker_dropped_frames_) {
            status_.frames_dropped += worker_dropped - worker_dropped_frames_;
        }
        worker_dropped_frames_ = worker_dropped;
        // A jelenlegi konfiguráció tényleg adott egy valódi frame-et -- ez a
        // visszaesési pont, ha egy KÉSŐBBI viewport-kérés lefagyasztja a workert.
        last_good_config_ = config_;
        restart_attempts_ = 0;
        return frame;
    } catch (const std::exception& error) {
        ++status_.frames_dropped;
        status_.message = std::string("Aaronia worker protocol error: ") + error.what();
        return std::nullopt;
    }
}

std::optional<SpectrumFrame> AaroniaRfSource::readSpectrumFrame() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (worker_pid_ > 0) {
        int wait_status = 0;
        if (waitpid(worker_pid_, &wait_status, WNOHANG) == worker_pid_) noteExitLocked(wait_status);
    }
    if (worker_pid_ <= 0 && !stop_requested_ && std::chrono::steady_clock::now() >= next_restart_) {
        launchLocked();
    }
    if (output_fd_ < 0) return std::nullopt;
    char buffer[64 * 1024];
    while (true) {
        const auto count = read(output_fd_, buffer, sizeof(buffer));
        if (count > 0) input_buffer_.append(buffer, static_cast<std::size_t>(count));
        else if (count < 0 && errno == EINTR) continue;
        else break;
    }
    std::optional<SpectrumFrame> latest;
    std::size_t newline = 0;
    while ((newline = input_buffer_.find('\n')) != std::string::npos) {
        const std::string line = input_buffer_.substr(0, newline);
        input_buffer_.erase(0, newline + 1);
        if (!line.empty()) {
            auto parsed = parseLineLocked(line);
            if (parsed) {
                // The producer intentionally keeps only the newest frame. Count
                // every valid frame replaced before publication as backpressure.
                if (latest) ++status_.frames_dropped;
                latest = std::move(parsed);
            }
        }
    }
    if (input_buffer_.size() > 8 * 1024 * 1024) {
        input_buffer_.clear();
        ++status_.frames_dropped;
    }
    return latest;
}

std::optional<IqFrame> AaroniaRfSource::readIqFrame() { return std::nullopt; }

}  // namespace rf_agent

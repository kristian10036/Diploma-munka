#include "rf_agent/soapy_rf_source.hpp"

#include <SoapySDR/Device.hpp>
#include <SoapySDR/Errors.hpp>
#include <SoapySDR/Formats.hpp>
#include <SoapySDR/Types.hpp>
#include <arpa/inet.h>
#include <nlohmann/json.hpp>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <cmath>
#include <ctime>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace rf_agent {
namespace {
using Json = nlohmann::json;

std::string timestamp_now() {
    const auto now = std::chrono::system_clock::now();
    const auto seconds = std::chrono::system_clock::to_time_t(now);
    const auto milliseconds = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()).count() % 1000;
    std::tm utc{};
    gmtime_r(&seconds, &utc);
    std::ostringstream value;
    value << std::put_time(&utc, "%Y-%m-%dT%H:%M:%S") << '.'
          << std::setfill('0') << std::setw(3) << milliseconds << 'Z';
    return value.str();
}

SoapySDR::Kwargs device_args(const SoapyRfConfig& config) {
    auto args = config.device_args.empty()
        ? SoapySDR::Kwargs{} : SoapySDR::KwargsFromString(config.device_args);
    args["driver"] = config.driver;
    return args;
}
}  // namespace

struct SoapyRfSource::Impl {
    SoapySDR::Device* device{nullptr};
    SoapySDR::Stream* stream{nullptr};
    int audio_socket{-1};
    sockaddr_in audio_destination{};
    double minimum_frequency_hz{0.0};
    double maximum_frequency_hz{0.0};
};

SoapyRfSource::SoapyRfSource(SoapyRfConfig config, SourceType source_type)
    : config_(std::move(config)), source_type_(source_type), impl_(std::make_unique<Impl>()),
      status_{source_type, SourceState::NotInitialized, config_.enabled, false,
              config_.enabled ? "SoapySDR source not initialized" : "SoapySDR source disabled", 0, 0},
      fft_(config_.fft_size, dsp::WindowType::Hann), limiter_(config_.max_fps),
      calibration_(config_.calibration_offset_db) {}

SoapyRfSource::~SoapyRfSource() { stop(); }

bool SoapyRfSource::deviceAvailable(const std::string& driver, const std::string& raw_args) {
    try {
        auto args = raw_args.empty() ? SoapySDR::Kwargs{} : SoapySDR::KwargsFromString(raw_args);
        args["driver"] = driver;
        return !SoapySDR::Device::enumerate(args).empty();
    } catch (...) { return false; }
}

bool SoapyRfSource::initialize() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!config_.enabled) return false;
    try {
        const auto found = SoapySDR::Device::enumerate(device_args(config_));
        if (found.empty()) {
            status_.state = SourceState::NotInitialized;
            status_.available = false;
            status_.message = "No " + config_.driver + " device detected";
            return false;
        }
        impl_->device = SoapySDR::Device::make(found.front());
        if (!impl_->device) throw std::runtime_error("SoapySDR device creation failed");
        const auto info = impl_->device->getHardwareInfo();
        device_model_ = info.count("product") ? info.at("product") : impl_->device->getHardwareKey();
        source_device_ = info.count("serial") ? info.at("serial") : config_.driver;
        const auto ranges = impl_->device->getFrequencyRange(SOAPY_SDR_RX, 0);
        if (!ranges.empty()) {
            impl_->minimum_frequency_hz = ranges.front().minimum();
            impl_->maximum_frequency_hz = ranges.front().maximum();
            for (const auto& range : ranges) {
                impl_->minimum_frequency_hz = std::min(impl_->minimum_frequency_hz, range.minimum());
                impl_->maximum_frequency_hz = std::max(impl_->maximum_frequency_hz, range.maximum());
            }
        }
        impl_->device->setSampleRate(SOAPY_SDR_RX, 0, static_cast<double>(config_.sample_rate_hz));
        impl_->device->setFrequency(SOAPY_SDR_RX, 0, static_cast<double>(config_.center_frequency_hz));
        if (impl_->device->hasGainMode(SOAPY_SDR_RX, 0)) impl_->device->setGainMode(SOAPY_SDR_RX, 0, false);
        impl_->device->setGain(SOAPY_SDR_RX, 0, config_.gain_db);
        impl_->stream = impl_->device->setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, {0});
        impl_->audio_socket = socket(AF_INET, SOCK_DGRAM, 0);
        impl_->audio_destination.sin_family = AF_INET;
        impl_->audio_destination.sin_port = htons(config_.audio_udp_port);
        if (inet_pton(AF_INET, config_.audio_udp_address.c_str(), &impl_->audio_destination.sin_addr) != 1) {
            throw std::runtime_error("native audio UDP address must be an IPv4 address");
        }
        status_.state = SourceState::Ready;
        status_.available = true;
        status_.message = device_model_ + " ready via SoapySDR/" + config_.driver;
        return true;
    } catch (const std::exception& error) {
        if (impl_->device) { SoapySDR::Device::unmake(impl_->device); impl_->device = nullptr; }
        status_.state = SourceState::Error;
        status_.available = false;
        status_.message = error.what();
        return false;
    }
}

bool SoapyRfSource::start() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!impl_->device || !impl_->stream) return false;
    try {
        const int result = impl_->device->activateStream(impl_->stream);
        if (result != 0) throw std::runtime_error(SoapySDR::errToStr(result));
        status_.state = SourceState::Running;
        status_.message = device_model_ + " streaming IQ";
        return true;
    } catch (const std::exception& error) { setError(error.what()); return false; }
}

void SoapyRfSource::stop() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (impl_->device && impl_->stream) {
        try { impl_->device->deactivateStream(impl_->stream); } catch (...) {}
        try { impl_->device->closeStream(impl_->stream); } catch (...) {}
        impl_->stream = nullptr;
    }
    if (impl_->device) { SoapySDR::Device::unmake(impl_->device); impl_->device = nullptr; }
    if (impl_->audio_socket >= 0) { close(impl_->audio_socket); impl_->audio_socket = -1; }
    audio_enabled_ = false;
    if (status_.state != SourceState::NotInitialized) status_.state = SourceState::Stopped;
}

SourceStatus SoapyRfSource::status() const { std::lock_guard<std::mutex> lock(mutex_); return status_; }

SourceCapabilities SoapyRfSource::capabilities() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return {true, true, true, true, true, true,
            static_cast<std::uint64_t>(std::max(0.0, impl_->minimum_frequency_hz)),
            static_cast<std::uint64_t>(std::max(0.0, impl_->maximum_frequency_hz)),
            config_.fft_size, true};
}

bool SoapyRfSource::setCenterFrequency(std::uint64_t value) {
    std::lock_guard<std::mutex> lock(mutex_);
    try { impl_->device->setFrequency(SOAPY_SDR_RX, 0, static_cast<double>(value)); config_.center_frequency_hz = value; return true; }
    catch (const std::exception& error) { setError(error.what()); return false; }
}
bool SoapyRfSource::setSampleRate(std::uint64_t value) {
    std::lock_guard<std::mutex> lock(mutex_);
    try { impl_->device->setSampleRate(SOAPY_SDR_RX, 0, static_cast<double>(value)); config_.sample_rate_hz = value; return true; }
    catch (const std::exception& error) { setError(error.what()); return false; }
}
bool SoapyRfSource::setGain(double value) {
    std::lock_guard<std::mutex> lock(mutex_);
    try { impl_->device->setGain(SOAPY_SDR_RX, 0, value); config_.gain_db = value; return true; }
    catch (const std::exception& error) { setError(error.what()); return false; }
}
bool SoapyRfSource::setSpan(std::uint64_t value) { return setSampleRate(value); }
bool SoapyRfSource::setSpectrumPointCount(std::size_t value) { return value == config_.fft_size; }

std::optional<SpectrumFrame> SoapyRfSource::readSpectrumFrame() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!impl_->device || !impl_->stream || status_.state != SourceState::Running) return std::nullopt;
    std::vector<std::complex<float>> samples(config_.fft_size);
    void* buffers[] = {samples.data()};
    int flags = 0; long long time_ns = 0;
    const int count = impl_->device->readStream(
        impl_->stream, buffers, samples.size(), flags, time_ns, 250'000);
    if (count == SOAPY_SDR_TIMEOUT) return std::nullopt;
    if (count < 0) { setError(SoapySDR::errToStr(count)); return std::nullopt; }
    if (count == 0) return std::nullopt;
    samples.resize(static_cast<std::size_t>(count));
    if (samples.size() != config_.fft_size) { ++status_.frames_dropped; return std::nullopt; }
    IqFrame iq;
    iq.sensor_id = config_.sensor_id; iq.source_type = source_type_; iq.source_device = source_device_;
    iq.session_id = config_.session_id; iq.timestamp = timestamp_now(); iq.sequence = sequence_;
    iq.center_frequency_hz = config_.center_frequency_hz; iq.sample_rate_hz = config_.sample_rate_hz;
    iq.samples = samples; iq.metadata.gain_db = config_.gain_db; latest_iq_ = iq;
    if (audio_enabled_) processAudio(samples);
    if (!limiter_.allow(std::chrono::steady_clock::now())) return std::nullopt;
    auto powers = fft_.process(samples); calibration_.process(powers);
    SpectrumFrame frame;
    frame.sensor_id = config_.sensor_id; frame.source_type = source_type_; frame.source_device = source_device_;
    frame.device_model = device_model_; frame.session_id = config_.session_id; frame.timestamp = iq.timestamp;
    frame.sequence = sequence_++; frame.center_frequency_hz = config_.center_frequency_hz;
    frame.sample_rate_hz = config_.sample_rate_hz; frame.num_points = powers.size();
    frame.step_frequency_hz = std::max<std::uint64_t>(1, config_.sample_rate_hz / config_.fft_size);
    const auto width = frame.step_frequency_hz * (frame.num_points - 1);
    frame.start_frequency_hz = frame.center_frequency_hz > width / 2 ? frame.center_frequency_hz - width / 2 : 0;
    frame.stop_frequency_hz = frame.start_frequency_hz + width;
    frame.rbw_hz = static_cast<double>(config_.sample_rate_hz) / config_.fft_size;
    frame.powers_dbm = std::move(powers); frame.metadata.gain_db = config_.gain_db;
    frame.metadata.attributes["driver"] = config_.driver;
    ++status_.frames_produced;
    return frame;
}

std::optional<IqFrame> SoapyRfSource::readIqFrame() {
    std::lock_guard<std::mutex> lock(mutex_);
    return latest_iq_;
}

std::string SoapyRfSource::startNativeAudio(const std::string& mode, int rate, double volume) {
    std::lock_guard<std::mutex> lock(mutex_);
    static const std::vector<std::string> accepted{"AM", "NFM", "WFM"};
    if (std::find(accepted.begin(), accepted.end(), mode) == accepted.end()) {
        throw std::runtime_error("native IQ audio supports AM, NFM and WFM");
    }
    if (rate >= 8000 && rate <= 192000) config_.audio_sample_rate_hz = rate;
    audio_mode_ = mode; audio_volume_ = std::clamp(volume, 0.0, 4.0);
    audio_dc_ = 0.0; audio_resample_accumulator_ = 0.0;
    audio_integrator_ = 0.0; audio_integrator_samples_ = 0;
    previous_sample_ = {1.0F, 0.0F}; audio_enabled_ = true;
    return Json{{"status", "ok"}, {"demodulator", mode}, {"channel_index", 0},
                {"native_iq", true}, {"audio_output", Json{{"enabled", true},
                {"browser_stream", true}, {"transport", "udp_l16_s16le"},
                {"device", "native-iq"}, {"sample_rate_hz", config_.audio_sample_rate_hz},
                {"volume", audio_volume_}}}}.dump();
}

std::string SoapyRfSource::stopNativeAudio() {
    std::lock_guard<std::mutex> lock(mutex_); audio_enabled_ = false;
    return Json{{"status", "ok"}, {"native_iq", true}, {"stopped", true}}.dump();
}

void SoapyRfSource::processAudio(const std::vector<std::complex<float>>& samples) {
    if (impl_->audio_socket < 0 || config_.sample_rate_hz == 0) return;
    std::vector<std::int16_t> pcm;
    pcm.reserve(samples.size() * config_.audio_sample_rate_hz / config_.sample_rate_hz + 2);
    for (const auto sample : samples) {
        float demodulated = 0.0F;
        if (audio_mode_ == "AM") {
            const double magnitude = std::abs(sample);
            audio_dc_ = 0.999 * audio_dc_ + 0.001 * magnitude;
            demodulated = static_cast<float>(magnitude - audio_dc_);
        } else {
            demodulated = std::arg(sample * std::conj(previous_sample_));
            previous_sample_ = sample;
        }
        audio_resample_accumulator_ += config_.audio_sample_rate_hz;
        audio_integrator_ += demodulated;
        ++audio_integrator_samples_;
        if (audio_resample_accumulator_ >= static_cast<double>(config_.sample_rate_hz)) {
            audio_resample_accumulator_ -= config_.sample_rate_hz;
            const double scale = audio_mode_ == "AM" ? 30'000.0 : 8'000.0;
            const double filtered = audio_integrator_samples_ > 0
                ? audio_integrator_ / static_cast<double>(audio_integrator_samples_) : 0.0;
            audio_integrator_ = 0.0;
            audio_integrator_samples_ = 0;
            const auto value = std::clamp(filtered * audio_volume_ * scale, -32768.0, 32767.0);
            pcm.push_back(static_cast<std::int16_t>(value));
        }
    }
    if (!pcm.empty()) sendto(impl_->audio_socket, pcm.data(), pcm.size() * sizeof(std::int16_t), 0,
        reinterpret_cast<const sockaddr*>(&impl_->audio_destination), sizeof(impl_->audio_destination));
}

void SoapyRfSource::setError(const std::string& message) {
    status_.state = SourceState::Error; status_.available = false; status_.message = message;
}

}  // namespace rf_agent

#include "rf_agent/auto_rf_source.hpp"

#include <stdexcept>

namespace rf_agent {

AutoRfSource::AutoRfSource(AutoRfConfig config) : config_(std::move(config)) {}
AutoRfSource::~AutoRfSource() { stop(); }

std::string AutoRfSource::desiredMode() const {
    if (config_.usrp.enabled && SoapyRfSource::deviceAvailable("uhd", config_.usrp.device_args)) return "usrp";
    if (config_.hackrf.enabled && SoapyRfSource::deviceAvailable("hackrf", config_.hackrf.device_args)) return "hackrf";
    if (config_.aaronia.enabled) return "aaronia";
    return {};
}

bool AutoRfSource::switchTo(const std::string& mode) {
    std::shared_ptr<IRfSource> candidate;
    if (mode == "usrp") candidate = std::make_shared<SoapyRfSource>(config_.usrp, SourceType::Usrp);
    else if (mode == "hackrf") candidate = std::make_shared<SoapyRfSource>(config_.hackrf, SourceType::Hackrf);
    else if (mode == "aaronia") candidate = std::make_shared<AaroniaRfSource>(config_.aaronia);
    else return false;
    if (!candidate->initialize()) return false;
    bool should_start = false;
    std::shared_ptr<IRfSource> previous;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        should_start = running_;
        previous = active_;
    }
    if (should_start && !candidate->start()) return false;
    if (previous) previous->stop();
    {
        std::lock_guard<std::mutex> lock(mutex_);
        active_ = std::move(candidate);
        active_mode_ = mode;
        next_probe_ = std::chrono::steady_clock::now() + config_.poll_interval;
    }
    return true;
}

std::shared_ptr<IRfSource> AutoRfSource::active() const {
    std::lock_guard<std::mutex> lock(mutex_); return active_;
}

bool AutoRfSource::initialize() {
    const auto desired = desiredMode();
    return !desired.empty() && switchTo(desired);
}

bool AutoRfSource::start() {
    auto source = active();
    if (!source || !source->start()) return false;
    std::lock_guard<std::mutex> lock(mutex_); running_ = true; return true;
}

void AutoRfSource::stop() {
    auto source = active();
    if (source) source->stop();
    std::lock_guard<std::mutex> lock(mutex_); running_ = false;
}

SourceStatus AutoRfSource::status() const {
    auto source = active();
    if (source) return source->status();
    return {SourceType::Unknown, SourceState::NotInitialized, true, false,
            "Automatic hardware detection found no source", 0, 0};
}
SourceCapabilities AutoRfSource::capabilities() const { auto s = active(); return s ? s->capabilities() : SourceCapabilities{}; }
bool AutoRfSource::setCenterFrequency(std::uint64_t v) { auto s = active(); return s && s->setCenterFrequency(v); }
bool AutoRfSource::setSampleRate(std::uint64_t v) { auto s = active(); return s && s->setSampleRate(v); }
bool AutoRfSource::setGain(double v) { auto s = active(); return s && s->setGain(v); }
bool AutoRfSource::setSpan(std::uint64_t v) { auto s = active(); return s && s->setSpan(v); }
bool AutoRfSource::setSpectrumPointCount(std::size_t v) { auto s = active(); return s && s->setSpectrumPointCount(v); }
bool AutoRfSource::configureViewport(std::uint64_t center, std::uint64_t span, std::size_t points) {
    auto source = active();
    if (auto aaronia = std::dynamic_pointer_cast<AaroniaRfSource>(source)) {
        return aaronia->configureViewport(center, span, points);
    }
    return source && source->setCenterFrequency(center) && source->setSpan(span) &&
        source->setSpectrumPointCount(points);
}

std::optional<SpectrumFrame> AutoRfSource::readSpectrumFrame() {
    bool should_probe = false;
    std::string current;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        should_probe = std::chrono::steady_clock::now() >= next_probe_;
        current = active_mode_;
        if (should_probe) next_probe_ = std::chrono::steady_clock::now() + config_.poll_interval;
    }
    if (should_probe) {
        const auto desired = desiredMode();
        if (!desired.empty() && desired != current) switchTo(desired);
    }
    auto source = active();
    return source ? source->readSpectrumFrame() : std::nullopt;
}
std::optional<IqFrame> AutoRfSource::readIqFrame() { auto s = active(); return s ? s->readIqFrame() : std::nullopt; }
bool AutoRfSource::supportsNativeAudio() const { auto s = active(); return s && s->supportsNativeAudio(); }
std::string AutoRfSource::startNativeAudio(const std::string& mode, int rate, double volume) {
    auto s = active(); if (!s || !s->supportsNativeAudio()) throw std::runtime_error("active source has no native IQ audio");
    return s->startNativeAudio(mode, rate, volume);
}
std::string AutoRfSource::stopNativeAudio() {
    auto s = active(); if (!s || !s->supportsNativeAudio()) throw std::runtime_error("active source has no native IQ audio");
    return s->stopNativeAudio();
}

}  // namespace rf_agent

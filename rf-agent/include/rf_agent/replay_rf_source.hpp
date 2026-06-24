#pragma once

#include "rf_agent/rf_source.hpp"

#include <chrono>
#include <cstddef>
#include <filesystem>
#include <mutex>
#include <string>
#include <vector>

namespace rf_agent {

struct ReplayRfConfig {
    std::filesystem::path recording_directory;
    std::string replay_session_id;
    bool loop{false};
    double speed{1.0};
    std::size_t max_frames{100'000};
    std::size_t max_line_bytes{8 * 1024 * 1024};
    std::size_t max_decompressed_bytes{256 * 1024 * 1024};
};

class ReplayRfSource final : public IRfSource {
public:
    explicit ReplayRfSource(ReplayRfConfig config);

    bool initialize() override;
    bool start() override;
    void stop() override;
    bool pause();
    bool resume();
    bool seek(std::size_t frame_index);
    bool setPlaybackSpeed(double speed);
    void setLoop(bool loop);

    [[nodiscard]] SourceStatus status() const override;
    [[nodiscard]] SourceCapabilities capabilities() const override;
    [[nodiscard]] std::size_t frameCount() const;
    [[nodiscard]] std::size_t currentFrameIndex() const;
    [[nodiscard]] double playbackSpeed() const;

    bool setCenterFrequency(std::uint64_t frequency_hz) override;
    bool setSampleRate(std::uint64_t sample_rate_hz) override;
    bool setGain(double gain_db) override;
    bool setSpan(std::uint64_t span_hz) override;
    bool setSpectrumPointCount(std::size_t point_count) override;
    std::optional<SpectrumFrame> readSpectrumFrame() override;
    std::optional<IqFrame> readIqFrame() override;

private:
    bool loadRecording();
    bool verifyChecksum(const std::filesystem::path& frame_path) const;
    bool parseFrames(const std::string& ndjson);
    [[nodiscard]] std::string readFrameData(const std::filesystem::path& frame_path) const;
    void setError(std::string message);

    mutable std::mutex mutex_;
    ReplayRfConfig config_;
    SourceStatus status_;
    std::vector<SpectrumFrame> frames_;
    std::size_t current_index_{0};
    std::uint64_t playback_sequence_{0};
    double frame_interval_ms_{200.0};
    std::chrono::steady_clock::time_point next_frame_at_{};
};

}  // namespace rf_agent

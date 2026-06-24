#pragma once

#include "rf_agent/aaronia_probe_runner.hpp"
#include "rf_agent/aaronia_rf_source.hpp"
#include "rf_agent/auto_rf_source.hpp"
#include "rf_agent/mock_rf_source.hpp"
#include "rf_agent/recording_writer.hpp"
#include "rf_agent/replay_rf_source.hpp"
#include "rf_agent/sdrangel_client.hpp"
#include "rf_agent/usrp_probe_runner.hpp"

#include <atomic>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <vector>

namespace rf_agent {

struct AgentConfig {
    std::string bind_address{"0.0.0.0"};
    std::uint16_t port{8765};
    std::string source_mode{"mock"};
    std::filesystem::path recordings_root{"/recordings"};
    MockRfConfig mock;
    ReplayRfConfig replay;
    AaroniaProbeConfig aaronia_probe;
    AaroniaRfConfig aaronia;
    UsrpProbeConfig usrp_probe;
    SoapyRfConfig usrp;
    SoapyRfConfig hackrf;
    AutoRfConfig automatic;
    SdrangelConfig sdrangel;

    [[nodiscard]] static AgentConfig fromEnvironment();
};

class SourceManager {
public:
    explicit SourceManager(AgentConfig config);
    ~SourceManager();
    SourceManager(const SourceManager&) = delete;
    SourceManager& operator=(const SourceManager&) = delete;

    bool initializeSelected();
    bool select(const std::string& mode, const std::optional<std::filesystem::path>& recording = std::nullopt);
    bool start();
    void stop();
    bool configure(
        const std::optional<std::uint64_t>& center_frequency_hz,
        const std::optional<std::uint64_t>& sample_rate_hz,
        const std::optional<double>& gain_db);
    bool configureViewport(std::uint64_t center_frequency_hz, std::uint64_t span_hz,
                           std::size_t maximum_points);
    bool replayPause();
    bool replayResume();
    bool replaySeek(std::size_t frame_index);
    bool replaySpeed(double speed);
    void replayLoop(bool loop);
    bool recordingStart(const RecordingStartOptions& options);
    [[nodiscard]] std::optional<std::string> recordingStop();
    [[nodiscard]] std::string recordingStatus() const;
    [[nodiscard]] std::string recordingError() const;

    [[nodiscard]] SourceStatus status() const;
    [[nodiscard]] SourceCapabilities capabilities() const;
    [[nodiscard]] std::string currentMode() const;
    [[nodiscard]] std::vector<std::filesystem::path> recordings() const;
    [[nodiscard]] std::optional<std::string> recordingMetadata(const std::string& id) const;

    [[nodiscard]] std::string runAaroniaProbe();
    [[nodiscard]] std::string aaroniaStatus() const;
    [[nodiscard]] std::string runUsrpProbe();
    [[nodiscard]] std::string usrpStatus() const;
    [[nodiscard]] std::string hackrfStatus() const;
    [[nodiscard]] std::string sdrangelStatus() const;
    [[nodiscard]] std::string sdrangelDeviceSets() const;
    [[nodiscard]] std::string sdrangelDevices() const;
    [[nodiscard]] std::string sdrangelCreateDeviceSet(const std::string& hardware_type) const;
    [[nodiscard]] std::string sdrangelTune(std::uint64_t center_frequency_hz, int device_set_index);
    [[nodiscard]] std::string sdrangelDemodStart(
        const std::string& demodulator,
        int device_set_index,
        std::int64_t offset_hz,
        int audio_sample_rate,
        int bandwidth_hz,
        double squelch_db,
        const std::string& audio_device,
        double volume);
    [[nodiscard]] std::string sdrangelDemodStop(int device_set_index, int channel_index);
    [[nodiscard]] std::string sdrangelDemodUpdate(
        const std::string& demodulator,
        int device_set_index,
        int channel_index,
        std::optional<std::int64_t> input_frequency_offset_hz,
        std::optional<int> bandwidth_hz,
        std::optional<double> squelch_db,
        std::optional<double> volume,
        std::optional<std::uint64_t> retune_device_center_hz);

    // Returns the most recent producer frame. The source is consumed by one
    // central producer thread, so recording does not depend on WebSocket
    // clients and all clients observe the same sequence stream.
    [[nodiscard]] std::optional<SpectrumFrame> readSpectrumFrame() const;

private:
    std::shared_ptr<IRfSource> createSource(
        const std::string& mode,
        const std::optional<std::filesystem::path>& recording) const;
    [[nodiscard]] std::optional<std::filesystem::path> safeRecordingPath(
        const std::filesystem::path& requested) const;
    void producerLoop();
    void stopProducer();

    AgentConfig config_;
    mutable std::mutex mutex_;
    std::string current_mode_;
    std::shared_ptr<IRfSource> source_;
    std::optional<SpectrumFrame> latest_frame_;
    SpectrumRecordingWriter recording_writer_;
    AaroniaProbeRunner aaronia_probe_;
    UsrpProbeRunner usrp_probe_;
    SdrangelClient sdrangel_;
    std::atomic_bool producer_running_{false};
    std::thread producer_thread_;
};

}  // namespace rf_agent

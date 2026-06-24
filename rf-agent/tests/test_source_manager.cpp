#include "rf_agent/agent.hpp"
#include <nlohmann/json.hpp>
#include <cassert>
#include <chrono>
#include <filesystem>
#include <iostream>
#include <thread>

int main() {
    using namespace rf_agent;
    using Json = nlohmann::json;
    const auto root = std::filesystem::temp_directory_path() / "rf-agent-manager-recording-test";
    std::error_code error;
    std::filesystem::remove_all(root, error);

    AgentConfig config;
    config.recordings_root = root;
    config.source_mode = "mock";
    config.mock.max_fps = 20.0;
    config.aaronia_probe.enabled = false;
    config.usrp_probe.enabled = false;
    config.sdrangel.enabled = false;

    SourceManager manager(config);
    assert(manager.initializeSelected());
    assert(manager.capabilities().viewport_control);
    assert(manager.configureViewport(915'000'000, 4'000'000, 4097));
    assert(manager.start());
    RecordingStartOptions options;
    options.recording_id = "producer-without-websocket";
    assert(manager.recordingStart(options));
    std::this_thread::sleep_for(std::chrono::milliseconds(350));
    const auto metadata = manager.recordingStop();
    assert(metadata.has_value());
    const auto parsed = Json::parse(*metadata);
    assert(parsed.at("frame_count").get<int>() > 0);
    assert(std::filesystem::is_regular_file(root / "producer-without-websocket" / "frames.ndjson.zst"));
    manager.stop();
    std::filesystem::remove_all(root, error);
    std::cout << "Source manager producer test: OK\n";
    return 0;
}

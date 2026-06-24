#include "rf_agent/mock_rf_source.hpp"
#include "rf_agent/recording_writer.hpp"
#include "rf_agent/replay_rf_source.hpp"
#include <nlohmann/json.hpp>
#include <cassert>
#include <filesystem>
#include <iostream>
#include <unistd.h>

int main() {
    using namespace rf_agent;
    const auto root = std::filesystem::temp_directory_path() / ("rf-agent-recording-" + std::to_string(getpid()));
    MockRfConfig mock_config; mock_config.point_count = 32;
    MockRfSource source(mock_config); assert(source.initialize()); assert(source.start());
    SpectrumRecordingWriter writer(root);
    RecordingStartOptions options; options.recording_id = "writer-test"; options.description = "writer fixture";
    assert(writer.start(options)); assert(!writer.start(options));
    for (int index = 0; index < 3; ++index) { const auto frame = source.readSpectrumFrame(); assert(frame); assert(writer.append(*frame)); }
    const auto metadata_text = writer.stop(); assert(metadata_text);
    const auto metadata = nlohmann::json::parse(*metadata_text);
    assert(metadata.at("recording_id") == "writer-test"); assert(metadata.at("frame_count") == 3);
    assert(metadata.at("compression") == "zstd");
    assert(metadata.at("status") == "completed");
    assert(metadata.at("checksum_sha256").get<std::string>().size() == 64);
    assert(std::filesystem::is_regular_file(root / "writer-test" / "metadata.json"));
    assert(std::filesystem::is_regular_file(root / "writer-test" / "frames.ndjson.zst"));
    assert(std::filesystem::is_regular_file(root / "writer-test" / "checksum.sha256"));
    assert(!std::filesystem::exists(root / ".writer-test.tmp"));
    ReplayRfConfig replay_config; replay_config.recording_directory = root / "writer-test"; replay_config.replay_session_id = "writer-replay";
    ReplayRfSource replay(replay_config); assert(replay.initialize()); assert(replay.frameCount() == 3); assert(replay.start()); assert(replay.readSpectrumFrame());
    std::filesystem::remove_all(root);
    std::cout << "rf-agent recording writer tests: OK\n";
    return 0;
}

#include "rf_agent/replay_rf_source.hpp"

#include <nlohmann/json.hpp>
#include <openssl/evp.h>
#include <zstd.h>

#include <array>
#include <chrono>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <unistd.h>
#include <vector>

namespace {

using Json = nlohmann::json;

Json frame_json(std::uint64_t sequence) {
    return Json{
        {"schema_version", 1}, {"sensor_id", "fixture-sensor"}, {"source_type", "mock"},
        {"source_device", "fixture-generator"}, {"session_id", "fixture-session"},
        {"timestamp", sequence == 10 ? "2026-06-19T12:00:00.000Z" : (sequence == 11 ? "2026-06-19T12:00:00.040Z" : "2026-06-19T12:00:00.080Z")}, {"sequence", sequence},
        {"center_frequency_hz", 101'000'000}, {"start_frequency_hz", 100'000'000},
        {"stop_frequency_hz", 102'000'000}, {"step_frequency_hz", 1'000'000},
        {"sample_rate_hz", 2'000'000}, {"rbw_hz", 1'000'000.0},
        {"num_points", 3}, {"power_unit", "dBm"},
        {"powers_dbm", {-90.0, -40.0 - static_cast<double>(sequence), -91.0}},
        {"flags", {{"overflow", false}, {"dropped", false}, {"inaccurate", false}}},
        {"metadata", {{"is_simulated", true}, {"gain_db", 0.0}, {"antenna", "SIMULATED"}}}};
}

std::string sha256(const std::vector<char>& data) {
    EVP_MD_CTX* context = EVP_MD_CTX_new();
    assert(context != nullptr);
    assert(EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1);
    assert(EVP_DigestUpdate(context, data.data(), data.size()) == 1);
    std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
    unsigned int size = 0;
    assert(EVP_DigestFinal_ex(context, digest.data(), &size) == 1);
    EVP_MD_CTX_free(context);
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for (unsigned int index = 0; index < size; ++index) {
        output << std::setw(2) << static_cast<unsigned int>(digest[index]);
    }
    return output.str();
}

std::filesystem::path create_fixture() {
    const auto directory = std::filesystem::temp_directory_path() /
                           ("rf-agent-replay-" + std::to_string(getpid()));
    std::filesystem::create_directories(directory);
    std::string ndjson;
    for (std::uint64_t sequence = 10; sequence < 13; ++sequence) {
        ndjson += frame_json(sequence).dump() + "\n";
    }
    ndjson += "{invalid-json}\n";

    const std::size_t bound = ZSTD_compressBound(ndjson.size());
    std::vector<char> compressed(bound);
    const std::size_t compressed_size = ZSTD_compress(
        compressed.data(), compressed.size(), ndjson.data(), ndjson.size(), 3);
    assert(!ZSTD_isError(compressed_size));
    compressed.resize(compressed_size);
    std::ofstream frame_output(directory / "frames.ndjson.zst", std::ios::binary);
    frame_output.write(compressed.data(), static_cast<std::streamsize>(compressed.size()));
    frame_output.close();

    std::ofstream metadata(directory / "metadata.json");
    metadata << Json{{"schema_version", 1}, {"frame_file", "frames.ndjson.zst"},
                     {"frame_interval_ms", 0.0}, {"frame_count", 4}}.dump(2);
    std::ofstream checksum(directory / "checksum.sha256");
    checksum << sha256(compressed) << "  frames.ndjson.zst\n";
    return directory;
}

}  // namespace

int main() {
    using namespace rf_agent;
    const std::filesystem::path fixture = create_fixture();

    ReplayRfConfig config;
    config.recording_directory = fixture;
    config.replay_session_id = "replay-test-session";
    ReplayRfSource timing_source(config);
    assert(timing_source.initialize());
    assert(timing_source.start());
    assert(timing_source.readSpectrumFrame().has_value());
    const auto timing_started = std::chrono::steady_clock::now();
    assert(timing_source.readSpectrumFrame().has_value());
    const auto timing_elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - timing_started);
    assert(timing_elapsed.count() >= 25);
    timing_source.stop();
    ReplayRfSource source(config);
    assert(source.initialize());
    assert(source.frameCount() == 3);
    assert(source.status().frames_dropped == 1);
    assert(source.status().state == SourceState::Ready);
    assert(source.setPlaybackSpeed(0.5));
    assert(source.setPlaybackSpeed(1.0));
    assert(source.setPlaybackSpeed(2.0));
    assert(source.setPlaybackSpeed(5.0));
    assert(!source.setPlaybackSpeed(3.0));
    assert(source.start());
    assert(source.pause());
    assert(source.status().state == SourceState::Paused);
    assert(!source.readSpectrumFrame().has_value());
    assert(source.resume());

    assert(source.seek(2));
    const auto third = source.readSpectrumFrame();
    assert(third.has_value());
    assert(third->source_type == SourceType::Replay);
    assert(third->session_id == "replay-test-session");
    assert(third->sequence == 0);
    assert(third->metadata.is_simulated);
    assert(third->metadata.attributes.at("replayed") == "true");
    assert(third->metadata.attributes.at("original_source_type") == "mock");
    assert(third->metadata.attributes.at("original_sequence") == "12");
    assert(!source.readSpectrumFrame().has_value());
    assert(source.status().state == SourceState::Stopped);

    source.setLoop(true);
    assert(source.start());
    assert(source.seek(2));
    assert(source.readSpectrumFrame().has_value());
    const auto looped = source.readSpectrumFrame();
    assert(looped.has_value());
    assert(looped->metadata.attributes.at("original_sequence") == "10");
    assert(looped->sequence == 2);
    source.stop();

    ReplayRfConfig bad_config = config;
    std::ofstream(fixture / "checksum.sha256") << std::string(64, '0') << '\n';
    ReplayRfSource bad_source(bad_config);
    assert(!bad_source.initialize());
    assert(bad_source.status().state == SourceState::Error);

    std::filesystem::remove_all(fixture);
    std::cout << "rf-agent replay source tests: OK\n";
    return 0;
}

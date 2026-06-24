#include "rf_agent/aaronia_rf_source.hpp"

#include <cassert>
#include <chrono>
#include <iostream>
#include <thread>

int main() {
    using namespace rf_agent;
    AaroniaRfConfig config;
    config.executable = TEST_WORKER_PATH;
    config.maximum_points = 2;

    AaroniaRfSource source(config);
    assert(source.initialize());
    assert(source.start());

    std::optional<SpectrumFrame> frame;
    for (int attempt = 0; attempt < 100 && !frame; ++attempt) {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        frame = source.readSpectrumFrame();
    }
    assert(frame);
    assert(frame->sequence == 2);
    assert(frame->source_type == SourceType::Aaronia);
    assert(frame->source_device == "test-device");
    assert(frame->powers_dbm.size() == 2);

    const auto status = source.status();
    assert(status.state == SourceState::Running);
    assert(status.frames_produced == 3);
    assert(status.frames_dropped == 2);
    source.stop();
    std::cout << "Aaronia RF source worker/backpressure tests: OK\n";
    return 0;
}

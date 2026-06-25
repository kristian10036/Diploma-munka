#include "rf_agent/aaronia_rf_source.hpp"

#include <cassert>
#include <chrono>
#include <iostream>
#include <string>
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

    // A valódi Aaronia SDK egy konkrét viewportra (szűk span/finom RBW)
    // ismételten elhasalhat (belső SDK kivétel -> SIGABRT); a worker test
    // child ezt a poison AARONIA_MAX_SPECTRUM_POINTS=31337 értékkel
    // szimulálja (std::abort()). A forrásnak néhány sikertelen próbálkozás
    // után az utolsó, valódi frame-et adó konfigurációra kell visszaesnie,
    // nem szabad végtelenül egy rossz viewporton ragadnia.
    {
        AaroniaRfConfig fallback_config;
        fallback_config.executable = TEST_WORKER_PATH;
        fallback_config.maximum_points = 2;

        AaroniaRfSource fallback_source(fallback_config);
        assert(fallback_source.initialize());
        assert(fallback_source.start());

        std::optional<SpectrumFrame> good_frame;
        for (int attempt = 0; attempt < 100 && !good_frame; ++attempt) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            good_frame = fallback_source.readSpectrumFrame();
        }
        assert(good_frame);
        assert(fallback_source.status().state == SourceState::Running);

        // hardware_min/max_frequency_hz a fixture válaszából 1000/2000;
        // 1500 center / 400 span (1300..1700) ezen belül van, így a
        // configureViewport saját validációján átmegy, és a "mérgezett"
        // 31337 pontszámmal újraindítja a workert.
        assert(fallback_source.configureViewport(1500, 400, 31337));

        bool recovered = false;
        bool saw_fallback_message = false;
        for (int attempt = 0; attempt < 3000 && !recovered; ++attempt) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            if (fallback_source.readSpectrumFrame()) recovered = true;
            if (fallback_source.status().message.find("fallback:") != std::string::npos) {
                saw_fallback_message = true;
            }
        }
        assert(saw_fallback_message);
        assert(recovered);
        fallback_source.stop();
        std::cout << "Aaronia RF source viewport-crash fallback test: OK\n";
    }
    return 0;
}

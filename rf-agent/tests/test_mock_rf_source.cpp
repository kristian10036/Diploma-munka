#include "rf_agent/mock_rf_source.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <iostream>
#include <limits>
#include <vector>

int main() {
    using namespace rf_agent;

    MockRfConfig invalid_config;
    invalid_config.point_count = 1;
    MockRfSource invalid_source(invalid_config);
    assert(!invalid_source.initialize());
    assert(invalid_source.status().state == SourceState::Error);

    MockRfConfig config;
    config.point_count = 512;
    config.random_seed = 12345;
    MockRfSource source(config);
    assert(!source.readSpectrumFrame().has_value());
    assert(source.initialize());
    assert(source.status().state == SourceState::Ready);
    assert(source.start());
    assert(source.status().state == SourceState::Running);

    const auto first = source.readSpectrumFrame();
    assert(first.has_value());
    assert(first->source_type == SourceType::Mock);
    assert(first->metadata.is_simulated);
    assert(first->metadata.antenna == "SIMULATED");
    assert(first->metadata.attributes.at("burst_active") == "true");
    assert(first->num_points == config.point_count);
    assert(first->powers_dbm.size() == config.point_count);
    assert(first->step_frequency_hz > 0);
    assert(first->stop_frequency_hz == first->start_frequency_hz +
           first->step_frequency_hz * (first->num_points - 1));
    assert(first->powers_dbm.size() == config.point_count);
    assert(first->sequence == 0);
    assert(validate_spectrum_frame(*first).valid());
    assert(*std::max_element(first->powers_dbm.begin(), first->powers_dbm.end()) > -36.0);

    const auto second = source.readSpectrumFrame();
    assert(second.has_value());
    assert(second->sequence == 1);
    assert(second->powers_dbm != first->powers_dbm);

    const auto third = source.readSpectrumFrame();
    const auto fourth = source.readSpectrumFrame();
    assert(third.has_value() && fourth.has_value());
    assert(fourth->metadata.attributes.at("burst_active") == "false");

    // Frames can directly feed max-hold processing.
    std::vector<double> max_hold = first->powers_dbm;
    for (std::size_t index = 0; index < max_hold.size(); ++index) {
        max_hold[index] = std::max(max_hold[index], second->powers_dbm[index]);
    }
    assert(max_hold.size() == config.point_count);

    assert(source.setGain(5.0));
    assert(!source.setGain(std::numeric_limits<double>::quiet_NaN()));
    assert(source.setSampleRate(20'000'000));
    assert(!source.setSampleRate(0));
    assert(source.setCenterFrequency(915'000'000));
    const auto tuned = source.readSpectrumFrame();
    assert(tuned.has_value());
    assert(tuned->center_frequency_hz == 915'000'000);
    assert(tuned->sample_rate_hz == 20'000'000);
    assert(tuned->metadata.gain_db == 5.0);
    assert(!source.readIqFrame().has_value());

    const SourceCapabilities capabilities = source.capabilities();
    assert(capabilities.spectrum);
    assert(!capabilities.iq);
    assert(capabilities.tuning && capabilities.sample_rate_control && capabilities.gain_control);
    assert(capabilities.viewport_control);
    assert(source.setSpan(2'000'000));
    assert(source.setSpectrumPointCount(2001));
    const auto viewport = source.readSpectrumFrame();
    assert(viewport.has_value());
    assert(viewport->num_points == 2001);
    assert(viewport->stop_frequency_hz - viewport->start_frequency_hz == 2'000'000);

    // Equal seeds and configuration produce equal power data.
    MockRfSource deterministic_a(config);
    MockRfSource deterministic_b(config);
    assert(deterministic_a.initialize() && deterministic_b.initialize());
    assert(deterministic_a.start() && deterministic_b.start());
    assert(deterministic_a.readSpectrumFrame()->powers_dbm ==
           deterministic_b.readSpectrumFrame()->powers_dbm);

    source.stop();
    assert(source.status().state == SourceState::Stopped);
    assert(!source.readSpectrumFrame().has_value());
    assert(source.status().frames_produced == 6);

    std::cout << "rf-agent mock source tests: OK\n";
    return 0;
}

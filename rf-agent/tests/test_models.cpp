#include "rf_agent/models.hpp"

#include <cassert>
#include <cmath>
#include <complex>
#include <iostream>
#include <limits>
#include <string>

namespace {

rf_agent::SpectrumFrame valid_spectrum_frame() {
    rf_agent::SpectrumFrame frame;
    frame.sensor_id = "hp-demo-01";
    frame.source_type = rf_agent::SourceType::Mock;
    frame.source_device = "mock-generator";
    frame.session_id = "550e8400-e29b-41d4-a716-446655440000";
    frame.timestamp = "2026-06-19T12:00:00.123Z";
    frame.sequence = 1;
    frame.center_frequency_hz = 2'450'000'000;
    frame.start_frequency_hz = 2'400'000'000;
    frame.stop_frequency_hz = 2'500'000'000;
    frame.step_frequency_hz = 50'000'000;
    frame.sample_rate_hz = 100'000'000;
    frame.rbw_hz = 10'000.0;
    frame.num_points = 3;
    frame.powers_dbm = {-95.0, -42.5, -91.0};
    frame.metadata.is_simulated = true;
    return frame;
}

rf_agent::IqFrame valid_iq_frame() {
    rf_agent::IqFrame frame;
    frame.sensor_id = "hp-demo-01";
    frame.source_type = rf_agent::SourceType::Replay;
    frame.source_device = "test-recording";
    frame.session_id = "550e8400-e29b-41d4-a716-446655440001";
    frame.timestamp = "2026-06-19T12:00:01+00:00";
    frame.sequence = 1;
    frame.center_frequency_hz = 100'000'000;
    frame.sample_rate_hz = 2'000'000;
    frame.samples = {{0.1F, -0.1F}, {0.2F, -0.2F}};
    return frame;
}

}  // namespace

int main() {
    using namespace rf_agent;

    auto spectrum = valid_spectrum_frame();
    assert(validate_spectrum_frame(spectrum).valid());
    assert(to_frontend_points_json(spectrum) ==
           "[{\"x\":2400.000000,\"y\":-95.00},{\"x\":2450.000000,\"y\":-42.50},"
           "{\"x\":2500.000000,\"y\":-91.00}]");

    auto mismatched = spectrum;
    mismatched.powers_dbm.pop_back();
    assert(!validate_spectrum_frame(mismatched).valid());

    auto invalid_range = spectrum;
    invalid_range.start_frequency_hz = invalid_range.stop_frequency_hz;
    assert(!validate_spectrum_frame(invalid_range).valid());

    auto invalid_number = spectrum;
    invalid_number.powers_dbm[0] = std::numeric_limits<double>::quiet_NaN();
    assert(!validate_spectrum_frame(invalid_number).valid());

    auto too_large = spectrum;
    assert(!validate_spectrum_frame(too_large, 2).valid());

    auto invalid_timestamp = spectrum;
    invalid_timestamp.timestamp = "2026-02-30T12:00:00Z";
    assert(!validate_spectrum_frame(invalid_timestamp).valid());

    FrameSequenceValidator sequences;
    assert(sequences.validate(spectrum).valid());
    assert(!sequences.validate(spectrum).valid());
    spectrum.sequence = 2;
    assert(sequences.validate(spectrum).valid());

    auto iq = valid_iq_frame();
    assert(validate_iq_frame(iq).valid());
    iq.samples[0] = {std::numeric_limits<float>::infinity(), 0.0F};
    assert(!validate_iq_frame(iq).valid());

    assert(to_string(SourceType::Mock) == "mock");
    assert(to_string(SourceType::Replay) == "replay");
    assert(to_string(SourceType::Usrp) == "usrp");
    assert(to_string(SourceType::Hackrf) == "hackrf");
    std::cout << "rf-agent model tests: OK\n";
    return 0;
}

#include <chrono>
#include <iostream>
#include <thread>

int main() {
    for (int sequence = 0; sequence < 3; ++sequence) {
        std::cout
            << R"({"schema_version":1,"sensor_id":"test-v6","source_type":"aaronia","source_device":"test-device","device_model":"SPECTRAN V6 TEST","measurement_mode":"sweepsa","session_id":"test-session","timestamp":"2026-06-21T12:00:00.000Z","sequence":)"
            << sequence
            << R"(,"center_frequency_hz":1500,"start_frequency_hz":1000,"stop_frequency_hz":2000,"step_frequency_hz":1000,"sample_rate_hz":1000,"rbw_hz":100.0,"point_count":2,"powers_dbm":[-90.0,-40.0],"overflow":false,"dropped":false,"inaccurate":false,"worker_dropped_frames":0,"hardware_min_frequency_hz":1000,"hardware_max_frequency_hz":2000,"available_rtbw_hz":245000000})"
            << '\n';
    }
    std::cout.flush();
    std::this_thread::sleep_for(std::chrono::seconds(2));
    return 0;
}

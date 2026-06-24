#include "rf_agent/usrp_probe_runner.hpp"
#include <nlohmann/json.hpp>
#include <cassert>
#include <chrono>
#include <cstdlib>
#include <iostream>

int main() {
    using Json = nlohmann::json;
    using namespace rf_agent;

    UsrpProbeConfig disabled;
    disabled.enabled = false;
    UsrpProbeRunner disabled_runner(disabled);
    auto status = Json::parse(disabled_runner.status());
    assert(status.at("probe_result") == "disabled");
    assert(status.at("data_plane") == "soapy_iq_spectrum_native_audio");

    UsrpProbeConfig config;
    config.enabled = true;
    config.executable = TEST_PROBE_PATH;
    config.timeout = std::chrono::milliseconds(100);
    UsrpProbeRunner runner(config);

    setenv("PROBE_TEST_MODE", "invalid", 1);
    auto result = Json::parse(runner.run());
    assert(result.at("probe_result") == "invalid_probe_response");
    assert(result.at("backend") == "usrp");

    setenv("PROBE_TEST_MODE", "timeout", 1);
    result = Json::parse(runner.run());
    assert(result.at("probe_result") == "probe_timeout");

    std::cout << "USRP probe runner tests: OK\n";
    return 0;
}

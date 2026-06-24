#include "rf_agent/aaronia_probe_runner.hpp"

#include <nlohmann/json.hpp>

#include <cassert>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <iostream>

int main() {
    using Json = nlohmann::json;
    using namespace rf_agent;

    AaroniaProbeConfig config;
    config.executable = TEST_PROBE_PATH;
    config.timeout = std::chrono::milliseconds(100);
    AaroniaProbeRunner runner(config);

    setenv("PROBE_TEST_MODE", "ok", 1);
    auto result = Json::parse(runner.run());
    assert(result.at("probe_result") == "sdk_not_found");
    assert(result.at("exit_code") == 2);
    assert(result.at("probe_pid").get<int>() > 0);

    setenv("PROBE_TEST_MODE", "sigill", 1);
    result = Json::parse(runner.run());
    assert(result.at("probe_result") == "illegal_instruction");
    assert(result.at("signal") == SIGILL);

    setenv("PROBE_TEST_MODE", "sigsegv", 1);
    result = Json::parse(runner.run());
    assert(result.at("probe_result") == "library_sigsegv");

    setenv("PROBE_TEST_MODE", "timeout", 1);
    result = Json::parse(runner.run());
    assert(result.at("probe_result") == "probe_timeout");

    setenv("PROBE_TEST_MODE", "invalid", 1);
    result = Json::parse(runner.run());
    assert(result.at("probe_result") == "unknown_failure");
    assert(result.at("exit_code") == 9);

    std::cout << "Aaronia probe runner tests: OK\n";
    return 0;
}

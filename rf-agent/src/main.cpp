#include "rf_agent/agent.hpp"
#include "rf_agent/http_server.hpp"

#include <atomic>
#include <csignal>
#include <exception>
#include <iostream>

namespace {

std::atomic_bool stop_requested{false};

void request_stop(int) { stop_requested.store(true); }

}  // namespace

int main() {
    std::signal(SIGINT, request_stop);
    std::signal(SIGTERM, request_stop);
    try {
        rf_agent::AgentConfig config = rf_agent::AgentConfig::fromEnvironment();
        rf_agent::SourceManager manager(config);
        if (manager.initializeSelected()) {
            if (!manager.start()) std::cerr << "Configured source could not be started\n";
        } else {
            std::cerr << "Configured source is unavailable; control API remains online\n";
        }
        rf_agent::HttpServer server(
            manager, config.bind_address, config.port, config.mock.max_fps);
        server.run(stop_requested);
        manager.stop();
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "RF agent fatal error: " << error.what() << '\n';
        return 1;
    }
}

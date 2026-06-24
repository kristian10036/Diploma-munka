#pragma once

#include "rf_agent/agent.hpp"

#include <atomic>
#include <cstdint>
#include <string>

namespace rf_agent {

class HttpServer {
public:
    HttpServer(SourceManager& manager, std::string bind_address, std::uint16_t port, double max_fps);
    void run(const std::atomic_bool& stop_requested);

private:
    SourceManager& manager_;
    std::string bind_address_;
    std::uint16_t port_;
    double max_fps_;
};

}  // namespace rf_agent

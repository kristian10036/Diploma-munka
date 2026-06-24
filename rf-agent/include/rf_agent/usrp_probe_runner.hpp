#pragma once

#include <chrono>
#include <mutex>
#include <string>

namespace rf_agent {

struct UsrpProbeConfig {
    bool enabled{false};
    std::string executable{"/usr/local/bin/usrp-probe"};
    std::string device_args;
    std::chrono::milliseconds timeout{5000};
};

class UsrpProbeRunner {
public:
    explicit UsrpProbeRunner(UsrpProbeConfig config);

    [[nodiscard]] std::string run();
    [[nodiscard]] std::string status() const;

private:
    UsrpProbeConfig config_;
    mutable std::mutex mutex_;
    std::string last_result_;
};

}  // namespace rf_agent

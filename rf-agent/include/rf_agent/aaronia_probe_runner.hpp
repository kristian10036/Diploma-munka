#pragma once

#include <chrono>
#include <mutex>
#include <string>

namespace rf_agent {

struct AaroniaProbeConfig {
    bool enabled{true};
    std::string executable{"/usr/local/bin/aaronia-probe"};
    std::chrono::milliseconds timeout{5000};
};

class AaroniaProbeRunner {
public:
    explicit AaroniaProbeRunner(AaroniaProbeConfig config);

    [[nodiscard]] std::string run();
    [[nodiscard]] std::string status() const;

private:
    AaroniaProbeConfig config_;
    mutable std::mutex mutex_;
    std::string last_result_;
};

}  // namespace rf_agent

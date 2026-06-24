#include "rf_agent/rf_source.hpp"

namespace rf_agent {

std::string to_string(SourceState state) {
    switch (state) {
        case SourceState::Disabled: return "disabled";
        case SourceState::NotInitialized: return "not_initialized";
        case SourceState::Ready: return "ready";
        case SourceState::Running: return "running";
        case SourceState::Paused: return "paused";
        case SourceState::Stopped: return "stopped";
        case SourceState::Error: return "error";
    }
    return "error";
}

}  // namespace rf_agent

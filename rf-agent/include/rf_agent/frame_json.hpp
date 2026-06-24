#pragma once

#include "rf_agent/models.hpp"
#include "rf_agent/rf_source.hpp"

#include <string>

namespace rf_agent {

[[nodiscard]] std::string spectrum_frame_json(const SpectrumFrame& frame);
[[nodiscard]] std::string source_status_json(const SourceStatus& status);
[[nodiscard]] std::string source_capabilities_json(const SourceCapabilities& capabilities);

}  // namespace rf_agent

#pragma once

#include "rf_agent/models.hpp"

#include <filesystem>
#include <memory>
#include <optional>
#include <string>

namespace rf_agent {

struct RecordingStartOptions {
    std::string recording_id;
    std::string description;
};

class SpectrumRecordingWriter {
public:
    explicit SpectrumRecordingWriter(std::filesystem::path recordings_root);
    ~SpectrumRecordingWriter();
    SpectrumRecordingWriter(const SpectrumRecordingWriter&) = delete;
    SpectrumRecordingWriter& operator=(const SpectrumRecordingWriter&) = delete;

    bool start(const RecordingStartOptions& options = {});
    bool append(const SpectrumFrame& frame);
    std::optional<std::string> stop();
    [[nodiscard]] bool active() const;
    [[nodiscard]] std::string statusJson() const;
    [[nodiscard]] const std::string& lastError() const;

private:
    struct Implementation;
    std::unique_ptr<Implementation> implementation_;
};

}  // namespace rf_agent

#include "rf_agent/frame_json.hpp"

#include <nlohmann/json.hpp>

namespace rf_agent {
namespace {

using Json = nlohmann::json;

Json metadata_json(const FrameMetadata& metadata) {
    Json value = metadata.attributes;
    value["is_simulated"] = metadata.is_simulated;
    if (metadata.gain_db) value["gain_db"] = *metadata.gain_db;
    if (metadata.antenna) value["antenna"] = *metadata.antenna;
    return value;
}

}  // namespace

std::string spectrum_frame_json(const SpectrumFrame& frame) {
    return Json{
        {"schema_version", frame.schema_version}, {"sensor_id", frame.sensor_id},
        {"source_type", to_string(frame.source_type)}, {"source_device", frame.source_device},
        {"device_model", frame.device_model}, {"measurement_mode", frame.measurement_mode},
        {"session_id", frame.session_id}, {"timestamp", frame.timestamp},
        {"sequence", frame.sequence}, {"center_frequency_hz", frame.center_frequency_hz},
        {"start_frequency_hz", frame.start_frequency_hz},
        {"stop_frequency_hz", frame.stop_frequency_hz},
        {"step_frequency_hz", frame.step_frequency_hz},
        {"sample_rate_hz", frame.sample_rate_hz}, {"rbw_hz", frame.rbw_hz},
        {"num_points", frame.num_points}, {"point_count", frame.num_points}, {"power_unit", frame.power_unit},
        {"powers_dbm", frame.powers_dbm},
        {"flags", Json{{"overflow", frame.flags.overflow}, {"dropped", frame.flags.dropped},
                       {"inaccurate", frame.flags.inaccurate}}},
        {"metadata", metadata_json(frame.metadata)}}.dump();
}

std::string source_status_json(const SourceStatus& status) {
    return Json{{"backend", to_string(status.backend)}, {"state", to_string(status.state)},
                {"enabled", status.enabled}, {"available", status.available},
                {"message", status.message}, {"frames_produced", status.frames_produced},
                {"frames_dropped", status.frames_dropped}}.dump();
}

std::string source_capabilities_json(const SourceCapabilities& capabilities) {
    return Json{{"spectrum", capabilities.spectrum}, {"iq", capabilities.iq},
                {"tuning", capabilities.tuning},
                {"sample_rate_control", capabilities.sample_rate_control},
                {"gain_control", capabilities.gain_control}, {"recording", capabilities.recording},
                {"minimum_frequency_hz", capabilities.minimum_frequency_hz},
                {"maximum_frequency_hz", capabilities.maximum_frequency_hz},
                {"maximum_spectrum_points", capabilities.maximum_spectrum_points},
                {"viewport_control", capabilities.viewport_control},
                {"viewport_modes", capabilities.viewport_control ? Json::array({"fixed", "sweep"}) : Json::array()}}.dump();
}

}  // namespace rf_agent

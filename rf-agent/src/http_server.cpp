#include "rf_agent/http_server.hpp"

#include "rf_agent/frame_json.hpp"

#include <boost/asio.hpp>
#include <boost/beast.hpp>
#include <nlohmann/json.hpp>

#include <chrono>
#include <iostream>
#include <limits>
#include <memory>
#include <optional>
#include <string>
#include <thread>

namespace rf_agent {
namespace {

namespace asio = boost::asio;
namespace beast = boost::beast;
namespace http = beast::http;
namespace websocket = beast::websocket;
using tcp = asio::ip::tcp;
using Json = nlohmann::json;

http::response<http::string_body> json_response(
    http::status status, const Json& body, unsigned version) {
    http::response<http::string_body> response{status, version};
    response.set(http::field::server, "diploma-rf-agent/0.2");
    response.set(http::field::content_type, "application/json");
    response.set(http::field::cache_control, "no-store");
    response.keep_alive(false);
    response.body() = body.dump();
    response.prepare_payload();
    return response;
}

Json status_value(SourceManager& manager) {
    return Json{{"mode", manager.currentMode()},
                {"source", Json::parse(source_status_json(manager.status()))},
                {"recording", Json::parse(manager.recordingStatus())},
                {"aaronia", Json::parse(manager.aaroniaStatus())},
                {"usrp", Json::parse(manager.usrpStatus())},
                {"hackrf", Json::parse(manager.hackrfStatus())},
                {"sdrangel", Json::parse(manager.sdrangelStatus())}};
}

http::response<http::string_body> route(
    const http::request<http::string_body>& request, SourceManager& manager) {
    const std::string target(request.target());
    const auto ok = [&](const Json& value) { return json_response(http::status::ok, value, request.version()); };
    const auto fail = [&](http::status status, const std::string& code,
                          const std::string& message, const Json& details = Json::object()) {
        return json_response(status,
                             Json{{"error", Json{{"code", code},
                                                 {"message", message},
                                                 {"details", details}}}},
                             request.version());
    };
    try {
        if (request.method() == http::verb::get && (target == "/health" || target == "/live")) {
            return ok(Json{{"status", target == "/live" ? "alive" : "ok"}, {"service", "rf-agent"},
                           {"source", Json::parse(source_status_json(manager.status()))}});
        }
        if (request.method() == http::verb::get && target == "/ready") {
            const Json source = Json::parse(source_status_json(manager.status()));
            const std::string state = source.value("state", "not_initialized");
            const bool ready = state == "ready" || state == "running" || state == "paused" || state == "stopped";
            return json_response(ready ? http::status::ok : http::status::service_unavailable,
                                 Json{{"status", ready ? "ready" : "not_ready"}, {"service", "rf-agent"}, {"source", source}},
                                 request.version());
        }
        if (request.method() == http::verb::get && target == "/status") return ok(status_value(manager));
        if (request.method() == http::verb::get && target == "/capabilities") {
            return ok(Json::parse(source_capabilities_json(manager.capabilities())));
        }
        if (request.method() == http::verb::get && target == "/sources/current") {
            return ok(status_value(manager));
        }
        if (request.method() == http::verb::get && target == "/sources") {
            const Json aaronia = Json::parse(manager.aaroniaStatus());
            const Json hackrf = Json::parse(manager.hackrfStatus());
            Json recordings = Json::array();
            for (const auto& recording : manager.recordings()) recordings.push_back(recording.string());
            return ok(Json{{"sources", Json::array({
                               Json{{"mode", "mock"}, {"available", true}},
                               Json{{"mode", "auto"}, {"available", true}},
                               Json{{"mode", "replay"}, {"available", !recordings.empty()}},
                               Json{{"mode", "aaronia"},
                                    {"available", aaronia.value("available", false)},
                                    {"status", aaronia.value("probe_result", "not_probed")}},
                               Json{{"mode", "usrp"},
                                    {"available", Json::parse(manager.usrpStatus()).value("available", false)},
                                    {"status", Json::parse(manager.usrpStatus()).value("probe_result", "disabled")}},
                               Json{{"mode", "hackrf"}, {"available", hackrf.value("available", false)},
                                    {"status", hackrf.value("probe_result", "disabled")}}})},
                           {"recordings", recordings}});
        }
        if (request.method() == http::verb::get &&
            (target == "/aaronia/probe" || target == "/aaronia/status")) {
            return ok(Json::parse(manager.aaroniaStatus()));
        }
        if (request.method() == http::verb::post && target == "/aaronia/probe") {
            return ok(Json::parse(manager.runAaroniaProbe()));
        }
        if (request.method() == http::verb::get && target == "/usrp/status") {
            return ok(Json::parse(manager.usrpStatus()));
        }
        if (request.method() == http::verb::post && target == "/usrp/probe") {
            return ok(Json::parse(manager.runUsrpProbe()));
        }
        if ((request.method() == http::verb::get || request.method() == http::verb::post) &&
            (target == "/hackrf/status" || target == "/hackrf/probe")) {
            return ok(Json::parse(manager.hackrfStatus()));
        }
        if (request.method() == http::verb::get && target == "/recordings") {
            Json values = Json::array();
            for (const auto& recording : manager.recordings()) values.push_back(recording.string());
            return ok(Json{{"recordings", values}});
        }
        if (request.method() == http::verb::get && target.rfind("/recordings/", 0) == 0 && target != "/recordings/status") {
            const std::string id = target.substr(std::string("/recordings/").size());
            const auto metadata = manager.recordingMetadata(id);
            if (!metadata) {
                return fail(http::status::not_found, "RECORDING_NOT_FOUND",
                            "Recording metadata was not found", Json{{"recording_id", id}});
            }
            return ok(Json::parse(*metadata));
        }
        if (request.method() == http::verb::post && target == "/sources/select") {
            const Json body = Json::parse(request.body());
            const std::string mode = body.at("mode").get<std::string>();
            std::optional<std::filesystem::path> recording;
            if (body.contains("recording")) recording = body.at("recording").get<std::string>();
            if (!manager.select(mode, recording)) {
                return fail(http::status::unprocessable_entity, "SOURCE_NOT_AVAILABLE",
                            "Source selection failed", Json{{"mode", mode}});
            }
            return ok(status_value(manager));
        }
        if (request.method() == http::verb::post && target == "/source/start") {
            if (!manager.start()) return fail(http::status::conflict, "SOURCE_START_FAILED", "Source could not be started");
            return ok(status_value(manager));
        }
        if (request.method() == http::verb::post && target == "/source/stop") {
            manager.stop();
            return ok(status_value(manager));
        }
        if (request.method() == http::verb::post && target == "/source/configure") {
            const Json body = Json::parse(request.body());
            std::optional<std::uint64_t> center;
            std::optional<std::uint64_t> rate;
            std::optional<double> gain;
            if (body.contains("center_frequency_hz")) center = body.at("center_frequency_hz").get<std::uint64_t>();
            if (body.contains("sample_rate_hz")) rate = body.at("sample_rate_hz").get<std::uint64_t>();
            if (body.contains("gain_db")) gain = body.at("gain_db").get<double>();
            if (!manager.configure(center, rate, gain)) {
                return fail(http::status::unprocessable_entity, "CONFIGURATION_REJECTED", "Source configuration was rejected");
            }
            return ok(status_value(manager));
        }
        if (request.method() == http::verb::post && target == "/source/viewport") {
            const Json body = Json::parse(request.body());
            const std::string request_id = body.at("request_id").get<std::string>();
            const std::string mode = body.at("mode").get<std::string>();
            const auto center = body.at("center_frequency_hz").get<std::uint64_t>();
            const auto span = body.at("span_hz").get<std::uint64_t>();
            const auto maximum_points = body.at("maximum_points").get<std::size_t>();
            if (request_id.empty() || request_id.size() > 128 || (mode != "fixed" && mode != "sweep")) {
                return fail(http::status::unprocessable_entity, "INVALID_VIEWPORT_REQUEST",
                            "request_id or mode is invalid");
            }
            const auto capabilities = manager.capabilities();
            if (!capabilities.viewport_control) {
                return fail(http::status::unprocessable_entity, "VIEWPORT_NOT_SUPPORTED",
                            "Current source does not support viewport control",
                            Json{{"request_id", request_id}, {"source", manager.currentMode()}});
            }
            const auto accepted_points = std::min(maximum_points, capabilities.maximum_spectrum_points);
            if (!manager.configureViewport(center, span, accepted_points)) {
                return fail(http::status::unprocessable_entity, "VIEWPORT_REJECTED",
                            "Viewport configuration was rejected", Json{{"request_id", request_id}});
            }
            const auto step = span / (accepted_points - 1);
            const auto start = center - span / 2;
            return ok(Json{{"schema_version", 1}, {"request_id", request_id},
                           {"status", accepted_points == maximum_points ? "accepted" : "constrained"},
                           {"mode", mode}, {"center_frequency_hz", center}, {"span_hz", span},
                           {"start_frequency_hz", start},
                           {"stop_frequency_hz", start + step * (accepted_points - 1)},
                           {"step_frequency_hz", step}, {"num_points", accepted_points},
                           {"source_type", manager.currentMode()},
                           {"hardware_execution", manager.currentMode() == "aaronia"}});
        }
        if (request.method() == http::verb::post && target == "/replay/start") {
            const Json body = Json::parse(request.body());
            const std::filesystem::path recording = body.at("recording").get<std::string>();
            if (!manager.select("replay", recording)) {
                return fail(http::status::unprocessable_entity, "REPLAY_NOT_AVAILABLE", "Replay recording was rejected");
            }
            if (body.contains("speed") && !manager.replaySpeed(body.at("speed").get<double>())) {
                return fail(http::status::unprocessable_entity, "REPLAY_SPEED_INVALID", "Unsupported replay speed");
            }
            if (body.contains("loop")) manager.replayLoop(body.at("loop").get<bool>());
            if (!manager.start()) return fail(http::status::conflict, "REPLAY_START_FAILED", "Replay could not be started");
            return ok(status_value(manager));
        }
        if (request.method() == http::verb::post && target == "/replay/pause") {
            if (!manager.replayPause()) return fail(http::status::conflict, "REPLAY_NOT_RUNNING", "Replay is not running");
            return ok(status_value(manager));
        }
        if (request.method() == http::verb::post && target == "/replay/resume") {
            if (!manager.replayResume()) return fail(http::status::conflict, "REPLAY_NOT_PAUSED", "Replay is not paused");
            return ok(status_value(manager));
        }
        if (request.method() == http::verb::post && target == "/replay/seek") {
            const Json body = Json::parse(request.body());
            if (!manager.replaySeek(body.at("frame_index").get<std::size_t>())) {
                return fail(http::status::unprocessable_entity, "REPLAY_SEEK_INVALID", "Invalid replay frame index");
            }
            return ok(status_value(manager));
        }
        if (request.method() == http::verb::post && target == "/replay/stop") {
            manager.stop();
            return ok(status_value(manager));
        }
        if (request.method() == http::verb::get && target == "/recordings/status") {
            return ok(Json::parse(manager.recordingStatus()));
        }
        if (request.method() == http::verb::post && target == "/recordings/start") {
            const Json body = request.body().empty() ? Json::object() : Json::parse(request.body());
            RecordingStartOptions options;
            options.recording_id = body.value("recording_id", "");
            options.description = body.value("description", "");
            if (!manager.recordingStart(options)) {
                return fail(http::status::conflict, "RECORDING_START_FAILED",
                            manager.recordingError());
            }
            return ok(Json::parse(manager.recordingStatus()));
        }
        if (request.method() == http::verb::post && target == "/recordings/stop") {
            const auto metadata = manager.recordingStop();
            if (!metadata) {
                return fail(http::status::conflict, "RECORDING_STOP_FAILED",
                            manager.recordingError());
            }
            return ok(Json::parse(*metadata));
        }
        if (request.method() == http::verb::get && target == "/sdrangel/status") {
            return ok(Json::parse(manager.sdrangelStatus()));
        }
        if (request.method() == http::verb::get && target == "/sdrangel/devicesets") {
            return ok(Json::parse(manager.sdrangelDeviceSets()));
        }
        if (request.method() == http::verb::get && target == "/sdrangel/devices") {
            return ok(Json::parse(manager.sdrangelDevices()));
        }
        if (request.method() == http::verb::post && target == "/sdrangel/devicesets") {
            const Json body = Json::parse(request.body());
            return ok(Json::parse(manager.sdrangelCreateDeviceSet(
                body.at("hardware_type").get<std::string>())));
        }
        if (request.method() == http::verb::post && target == "/sdrangel/tune") {
            const Json body = Json::parse(request.body());
            return ok(Json::parse(manager.sdrangelTune(
                body.at("center_frequency_hz").get<std::uint64_t>(),
                body.value("device_set_index", -1))));
        }
        if (request.method() == http::verb::post && target == "/sdrangel/demod/start") {
            const Json body = Json::parse(request.body());
            return ok(Json::parse(manager.sdrangelDemodStart(
                body.at("demodulator").get<std::string>(),
                body.value("device_set_index", -1),
                body.value("offset_hz", static_cast<std::int64_t>(0)),
                body.value("audio_sample_rate", 0),
                body.value("bandwidth_hz", 0),
                body.value("squelch_db", std::numeric_limits<double>::quiet_NaN()),
                body.value("audio_device", std::string{}),
                body.value("volume", 1.0))));
        }
        if (request.method() == http::verb::patch && target == "/sdrangel/demod/update") {
            const Json body = Json::parse(request.body());
            if (!body.contains("channel_index")) {
                return fail(http::status::bad_request, "CHANNEL_INDEX_REQUIRED",
                            "channel_index is required to update an SDRangel demodulator");
            }
            const auto opt_i64 = [&body](const char* key) -> std::optional<std::int64_t> {
                if (!body.contains(key) || body.at(key).is_null()) return std::nullopt;
                return body.at(key).get<std::int64_t>();
            };
            const auto opt_int = [&body](const char* key) -> std::optional<int> {
                if (!body.contains(key) || body.at(key).is_null()) return std::nullopt;
                return body.at(key).get<int>();
            };
            const auto opt_dbl = [&body](const char* key) -> std::optional<double> {
                if (!body.contains(key) || body.at(key).is_null()) return std::nullopt;
                return body.at(key).get<double>();
            };
            const auto opt_u64 = [&body](const char* key) -> std::optional<std::uint64_t> {
                if (!body.contains(key) || body.at(key).is_null()) return std::nullopt;
                return body.at(key).get<std::uint64_t>();
            };
            return ok(Json::parse(manager.sdrangelDemodUpdate(
                body.at("demodulator").get<std::string>(),
                body.value("device_set_index", -1),
                body.at("channel_index").get<int>(),
                opt_i64("input_frequency_offset_hz"),
                opt_int("bandwidth_hz"),
                opt_dbl("squelch_db"),
                opt_dbl("volume"),
                opt_u64("retune_device_center_hz"))));
        }
        if (request.method() == http::verb::post && target == "/sdrangel/demod/stop") {
            const Json body = Json::parse(request.body());
            if (!body.contains("channel_index")) {
                return fail(http::status::bad_request, "CHANNEL_INDEX_REQUIRED",
                            "channel_index is required to stop an SDRangel demodulator");
            }
            return ok(Json::parse(manager.sdrangelDemodStop(
                body.value("device_set_index", -1), body.at("channel_index").get<int>())));
        }
        return fail(http::status::not_found, "ENDPOINT_NOT_FOUND", "Endpoint not found");
    } catch (const Json::exception& error) {
        return fail(http::status::bad_request, "INVALID_JSON_REQUEST",
                    std::string("Invalid JSON request: ") + error.what());
    } catch (const std::exception& error) {
        return fail(http::status::internal_server_error, "INTERNAL_ERROR", error.what());
    }
}

void websocket_session(
    tcp::socket socket,
    http::request<http::string_body> request,
    SourceManager& manager,
    double max_fps) {
    try {
        websocket::stream<tcp::socket> stream(std::move(socket));
        stream.set_option(websocket::stream_base::timeout::suggested(beast::role_type::server));
        stream.accept(request);
        stream.text(true);
        const auto interval = std::chrono::duration<double>(1.0 / std::max(0.1, max_fps));
        std::optional<std::uint64_t> last_sequence;
        while (true) {
            const auto started = std::chrono::steady_clock::now();
            const auto frame = manager.readSpectrumFrame();
            if (frame && (!last_sequence || frame->sequence != *last_sequence)) {
                const std::string payload = spectrum_frame_json(*frame);
                stream.write(asio::buffer(payload));
                last_sequence = frame->sequence;
            }
            std::this_thread::sleep_until(started +
                std::chrono::duration_cast<std::chrono::steady_clock::duration>(interval));
        }
    } catch (const std::exception&) {
        // Normal disconnects and protocol errors only terminate this client.
    }
}

void status_websocket_session(
    tcp::socket socket,
    http::request<http::string_body> request,
    SourceManager& manager) {
    try {
        websocket::stream<tcp::socket> stream(std::move(socket));
        stream.set_option(websocket::stream_base::timeout::suggested(beast::role_type::server));
        stream.accept(request);
        stream.text(true);
        while (true) {
            const std::string payload = status_value(manager).dump();
            stream.write(asio::buffer(payload));
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    } catch (const std::exception&) {
        // Disconnects only terminate this status client.
    }
}

void connection_session(tcp::socket socket, SourceManager& manager, double max_fps) {
    beast::flat_buffer buffer;
    http::request_parser<http::string_body> parser;
    parser.body_limit(1024 * 1024);
    beast::error_code error;
    http::read(socket, buffer, parser, error);
    if (error) return;
    auto request = parser.release();
    if (websocket::is_upgrade(request) && request.target() == "/ws/spectrum") {
        websocket_session(std::move(socket), std::move(request), manager, max_fps);
        return;
    }
    if (websocket::is_upgrade(request) && request.target() == "/ws/status") {
        status_websocket_session(std::move(socket), std::move(request), manager);
        return;
    }
    auto response = route(request, manager);
    http::write(socket, response, error);
    socket.shutdown(tcp::socket::shutdown_send, error);
}

}  // namespace

HttpServer::HttpServer(
    SourceManager& manager, std::string bind_address, std::uint16_t port, double max_fps)
    : manager_(manager), bind_address_(std::move(bind_address)), port_(port), max_fps_(max_fps) {}

void HttpServer::run(const std::atomic_bool& stop_requested) {
    asio::io_context context(1);
    const auto address = asio::ip::make_address(bind_address_);
    tcp::acceptor acceptor(context, {address, port_});
    acceptor.non_blocking(true);
    std::cout << "RF agent listening on " << bind_address_ << ':' << port_ << '\n';
    while (!stop_requested.load()) {
        beast::error_code error;
        tcp::socket socket(context);
        acceptor.accept(socket, error);
        if (error == asio::error::would_block || error == asio::error::try_again) {
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            continue;
        }
        if (error) throw beast::system_error(error);
        std::thread(connection_session, std::move(socket), std::ref(manager_), max_fps_).detach();
    }
}

}  // namespace rf_agent

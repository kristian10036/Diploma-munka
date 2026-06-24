#include "rf_agent/sdrangel_client.hpp"
#include "rf_agent/sdrangel_demod_settings.hpp"

#include <boost/asio.hpp>
#include <boost/beast.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <cctype>
#include <cmath>
#include <map>
#include <set>
#include <stdexcept>
#include <utility>
#include <chrono>
#include <iomanip>
#include <initializer_list>
#include <sstream>
#include <thread>

namespace rf_agent {
namespace {

namespace asio = boost::asio;
namespace beast = boost::beast;
namespace http = beast::http;
using tcp = asio::ip::tcp;
using Json = nlohmann::json;

struct ParsedUrl {
    std::string host;
    std::string port;
    std::string base_path;
};

ParsedUrl parse_http_url(const std::string& value) {
    constexpr const char* prefix = "http://";
    if (value.rfind(prefix, 0) != 0) throw std::runtime_error("only http:// SDRangel URLs are supported");
    std::string remainder = value.substr(std::char_traits<char>::length(prefix));
    const auto slash = remainder.find('/');
    std::string authority = slash == std::string::npos ? remainder : remainder.substr(0, slash);
    std::string base_path = slash == std::string::npos ? "" : remainder.substr(slash);
    const auto colon = authority.rfind(':');
    std::string host = colon == std::string::npos ? authority : authority.substr(0, colon);
    std::string port = colon == std::string::npos ? "80" : authority.substr(colon + 1);
    if (host.empty() || port.empty()) throw std::runtime_error("invalid SDRangel API URL");
    if (!base_path.empty() && base_path.back() == '/') base_path.pop_back();
    return {host, port, base_path};
}

Json request_json_once(
    const SdrangelConfig& config,
    http::verb method,
    const std::string& path,
    const Json* payload = nullptr) {
    const auto parsed = parse_http_url(config.api_url);
    asio::io_context context;
    tcp::resolver resolver(context);
    beast::tcp_stream stream(context);
    http::request<http::string_body> request{method, parsed.base_path + path, 11};
    request.set(http::field::host, parsed.host);
    request.set(http::field::user_agent, "diploma-rf-agent/0.2");
    request.set(http::field::accept, "application/json");
    if (payload) {
        request.set(http::field::content_type, "application/json");
        request.body() = payload->dump();
        request.prepare_payload();
    }
    beast::flat_buffer buffer;
    http::response<http::string_body> response;
    asio::steady_timer timer(context);
    beast::error_code operation_error;
    bool completed = false;
    bool timed_out = false;
    const auto finish = [&](beast::error_code error) {
        if (completed) return;
        completed = true;
        operation_error = error;
        beast::error_code ignored;
        timer.cancel(ignored);
    };
    timer.expires_after(config.timeout);
    timer.async_wait([&](beast::error_code error) {
        if (error || completed) return;
        timed_out = true;
        resolver.cancel();
        beast::error_code ignored;
        stream.socket().cancel(ignored);
    });
    resolver.async_resolve(parsed.host, parsed.port,
        [&](beast::error_code error, tcp::resolver::results_type endpoints) {
            if (error) return finish(error);
            stream.async_connect(endpoints,
                [&](beast::error_code connect_error, const tcp::endpoint&) {
                    if (connect_error) return finish(connect_error);
                    http::async_write(stream, request,
                        [&](beast::error_code write_error, std::size_t) {
                            if (write_error) return finish(write_error);
                            http::async_read(stream, buffer, response,
                                [&](beast::error_code read_error, std::size_t) {
                                    finish(read_error);
                                });
                        });
                });
        });
    context.run();
    if (timed_out) throw std::runtime_error("SDRangel request timeout");
    if (operation_error) throw std::runtime_error("SDRangel request failed: " + operation_error.message());
    beast::error_code ignored;
    stream.socket().shutdown(tcp::socket::shutdown_both, ignored);

    Json body = Json::object();
    if (!response.body().empty()) {
        try {
            body = Json::parse(response.body());
        } catch (const Json::exception&) {
            throw std::runtime_error("SDRangel returned invalid JSON");
        }
    }
    if (response.result_int() < 200 || response.result_int() >= 300) {
        throw std::runtime_error(
            "SDRangel HTTP " + std::to_string(response.result_int()) + ": " + body.dump());
    }
    return body;
}

Json request_json(const SdrangelConfig& config, http::verb method, const std::string& path,
                  const Json* payload = nullptr) {
    std::string error;
    for (int attempt = 0; attempt < 2; ++attempt) {
        try {
            return request_json_once(config, method, path, payload);
        } catch (const std::exception& exception) {
            error = exception.what();
            if (attempt == 0) std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }
    throw std::runtime_error(error);
}

std::string utc_now() {
    const auto now = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
    std::tm value{};
    gmtime_r(&now, &value);
    std::ostringstream output;
    output << std::put_time(&value, "%Y-%m-%dT%H:%M:%SZ");
    return output.str();
}

Json base_status(const SdrangelConfig& config) {
    const bool data_plane_configured = config.data_plane_mode != "not_configured" &&
                                       !config.data_plane_endpoint.empty() &&
                                       config.iq_sample_rate_hz > 0;
    return Json{{"enabled", config.enabled},
                {"api_url", config.api_url},
                {"control_plane", config.enabled ? "configured" : "disabled"},
                {"data_plane", data_plane_configured ? "configured_not_tested" : "not_configured"},
                {"data_plane_mode", config.data_plane_mode},
                {"data_plane_endpoint", config.data_plane_endpoint.empty() ? Json(nullptr) : Json(config.data_plane_endpoint)},
                {"iq_sample_format", config.iq_sample_format},
                {"iq_sample_rate_hz", config.iq_sample_rate_hz},
                {"audio_relay", Json{{"transport", "udp_l16_s16le"},
                                      {"address", config.audio_udp_address},
                                      {"port", config.audio_udp_port},
                                      {"sample_rate_hz", config.audio_udp_sample_rate_hz}}},
                {"hardware_tested", false}};
}

// A demodulátor profil- és settings-mező segédfüggvények a megosztott
// rf_agent::* modulba (sdrangel_demod_settings) kerültek, hogy az indítás és az
// élő frissítés ugyanazt a tesztelt logikát használja. Itt csak SDRangel-
// specifikus, hálózatot igénylő rész marad.

std::string trimmed_upper(std::string value) {
    const auto first = std::find_if_not(value.begin(), value.end(), [](unsigned char character) {
        return std::isspace(character) != 0;
    });
    const auto last = std::find_if_not(value.rbegin(), value.rend(), [](unsigned char character) {
        return std::isspace(character) != 0;
    }).base();
    if (first >= last) return "";
    value = std::string(first, last);
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char character) {
        return static_cast<char>(std::toupper(character));
    });
    return value;
}

bool json_values_equal(const Json& left, const Json& right) {
    if (left.is_number() && right.is_number()) {
        return std::abs(left.get<double>() - right.get<double>()) < 0.000001;
    }
    return left == right;
}

Json configure_audio_relay(
    const SdrangelConfig& config,
    const std::string& requested_device,
    int requested_sample_rate_hz) {
    const Json audio = request_json(config, http::verb::get, "/audio");
    const Json outputs = audio.value("outputDevices", Json::array());
    if (!outputs.is_array() || outputs.empty()) {
        throw std::runtime_error("SDRangel has no audio output device available for UDP relay");
    }

    const std::string requested_normalized = trimmed_upper(requested_device);
    const bool wants_default = requested_normalized.empty() ||
        requested_normalized == "DEFAULT" ||
        requested_normalized == "SYSTEM DEFAULT" ||
        requested_normalized == "SYSTEM DEFAULT DEVICE";

    const Json* selected = nullptr;
    if (wants_default) {
        for (const auto& output : outputs) {
            if (output.value("index", 0) == -1) {
                selected = &output;
                break;
            }
        }
        if (selected == nullptr) {
            for (const auto& output : outputs) {
                if (output.value("isSystemDefault", 0) == 1) {
                    selected = &output;
                    break;
                }
            }
        }
    } else {
        for (const auto& output : outputs) {
            if (trimmed_upper(output.value("name", "")) == requested_normalized) {
                selected = &output;
                break;
            }
        }
    }
    if (selected == nullptr && wants_default) selected = &outputs.front();
    if (selected == nullptr) {
        throw std::runtime_error("requested SDRangel audio output device is not available");
    }

    const int sample_rate_hz = config.audio_udp_sample_rate_hz > 0
        ? config.audio_udp_sample_rate_hz
        : (requested_sample_rate_hz > 0 ? requested_sample_rate_hz : 48000);
    Json patch{
        {"index", selected->value("index", -1)},
        {"sampleRate", sample_rate_hz},
        {"copyToUDP", 1},
        {"udpUsesRTP", 0},
        {"udpChannelMode", 2},       // mixed mono
        {"udpChannelCodec", 0},      // L16 / native S16LE
        {"udpDecimationFactor", 1},
        {"udpAddress", config.audio_udp_address},
        {"udpPort", config.audio_udp_port},
    };

    bool requires_patch = false;
    for (const auto& item : patch.items()) {
        if (item.key() == "index") continue;
        if (!selected->contains(item.key()) ||
            !json_values_equal(selected->at(item.key()), item.value())) {
            requires_patch = true;
            break;
        }
    }
    const Json remote = requires_patch
        ? request_json(config, http::verb::patch, "/audio/output/parameters", &patch)
        : *selected;

    return Json{{"enabled", true},
                {"browser_stream", true},
                {"device", selected->value("name", "System default device")},
                {"device_index", selected->value("index", -1)},
                {"sample_rate_hz", sample_rate_hz},
                {"codec", "L16/S16LE"},
                {"channels", 1},
                {"channel_mode", "mixed"},
                {"udp_address", config.audio_udp_address},
                {"udp_port", config.audio_udp_port},
                {"rtp", false},
                {"remote", remote}};
}

}  // namespace

SdrangelClient::SdrangelClient(SdrangelConfig config) : config_(std::move(config)) {}

std::string SdrangelClient::status() const {
    Json result = base_status(config_);
    result["available"] = false;
    result["status"] = config_.enabled ? "unreachable" : "disabled";
    if (!config_.enabled) return result.dump();
    try {
        result["remote"] = request_json(config_, http::verb::get, "");
        result["available"] = true;
        result["status"] = "ready";
        result["control_plane"] = "ready";
        {
            std::lock_guard<std::mutex> lock(status_mutex_);
            last_success_at_ = utc_now();
            result["last_successful_connection"] = last_success_at_;
        }
    } catch (const std::exception& error) {
        result["diagnostic"] = error.what();
        std::lock_guard<std::mutex> lock(status_mutex_);
        result["last_successful_connection"] = last_success_at_.empty() ? Json(nullptr) : Json(last_success_at_);
    }
    return result.dump();
}

std::string SdrangelClient::deviceSets() const {
    if (!config_.enabled) throw std::runtime_error("SDRangel integration is disabled");
    return request_json(config_, http::verb::get, "/devicesets").dump();
}

std::string SdrangelClient::devices() const {
    if (!config_.enabled) throw std::runtime_error("SDRangel integration is disabled");
    return request_json(config_, http::verb::get, "/devices").dump();
}

std::string SdrangelClient::createDeviceSet(const std::string& hardware_type) const {
    if (!config_.enabled) throw std::runtime_error("SDRangel integration is disabled");
    static const std::set<std::string> allowed{
        "TestSource", "LocalInput", "RemoteInput", "RemoteTCPInput", "FileInput", "AaroniaRTSA"
    };
    if (!allowed.count(hardware_type)) throw std::runtime_error("unsupported SDRangel hardware type");

    const Json available = request_json(config_, http::verb::get, "/devices");
    bool found = false;
    for (const auto& device : available.value("devices", Json::array())) {
        if (device.value("hwType", "") == hardware_type && device.value("direction", -1) == 0) {
            found = true;
            break;
        }
    }
    if (!found) throw std::runtime_error("requested SDRangel Rx device is not available");

    const int before = request_json(config_, http::verb::get, "/devicesets").value("devicesetcount", 0);
    const Json created = request_json(config_, http::verb::post, "/deviceset");
    int index = -1;
    for (int attempt = 0; attempt < 20; ++attempt) {
        const int count = request_json(config_, http::verb::get, "/devicesets").value("devicesetcount", 0);
        if (count > before) { index = count - 1; break; }
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    if (index < 0) throw std::runtime_error("SDRangel DeviceSet creation did not complete");
    const Json select{{"hwType", hardware_type}};
    const Json selected = request_json(
        config_, http::verb::put,
        "/deviceset/" + std::to_string(index) + "/device", &select);
    return Json{{"status", "ok"}, {"device_set_index", index}, {"hardware_type", hardware_type},
                {"create", created}, {"device", selected}}.dump();
}

std::string SdrangelClient::tune(std::uint64_t center_frequency_hz, int device_set_index) const {
    if (!config_.enabled) throw std::runtime_error("SDRangel integration is disabled");
    if (center_frequency_hz == 0) throw std::runtime_error("center_frequency_hz must be positive");
    if (device_set_index < 0) device_set_index = config_.default_device_set_index;
    const std::string path = "/deviceset/" + std::to_string(device_set_index) + "/device/settings";
    const Json current = request_json(config_, http::verb::get, path);
    std::string settings_key = config_.device_settings_key;
    if (settings_key.empty()) {
        for (const auto& item : current.items()) {
            if (item.value().is_object() && item.key().size() >= 8 &&
                item.key().compare(item.key().size() - 8, 8, "Settings") == 0) {
                settings_key = item.key();
                break;
            }
        }
    }
    if (settings_key.empty()) throw std::runtime_error("SDRangel device settings schema is unavailable");
    Json payload{{settings_key, Json{{"centerFrequency", center_frequency_hz}}}};
    if (current.contains("deviceHwType")) payload["deviceHwType"] = current.at("deviceHwType");
    if (current.contains("direction")) payload["direction"] = current.at("direction");
    Json remote = request_json(config_, http::verb::patch, path, &payload);
    return Json{{"status", "ok"}, {"center_frequency_hz", center_frequency_hz},
                {"device_set_index", device_set_index}, {"remote", remote}}.dump();
}

std::string SdrangelClient::startDemodulator(
    const std::string& demodulator,
    int device_set_index,
    std::int64_t offset_hz,
    int audio_sample_rate,
    int bandwidth_hz,
    double squelch_db,
    const std::string& audio_device,
    double volume) const {
    if (!config_.enabled) throw std::runtime_error("SDRangel integration is disabled");
    if (device_set_index < 0) device_set_index = config_.default_device_set_index;
    if (audio_sample_rate < 0) throw std::runtime_error("audio_sample_rate must not be negative");
    if (bandwidth_hz < 0) throw std::runtime_error("bandwidth_hz must not be negative");
    if (!std::isfinite(volume) || volume < 0.0 || volume > 10.0) {
        throw std::runtime_error("volume must be between 0 and 10");
    }

    const std::string normalized = normalized_demodulator(demodulator);
    const DemodulatorProfile profile = demodulator_profile(normalized);
    const Json before = request_json(config_, http::verb::get, "/devicesets");
    const auto sets = before.value("deviceSets", Json::array());
    if (device_set_index >= static_cast<int>(sets.size())) {
        throw std::runtime_error("SDRangel DeviceSet does not exist");
    }
    const Json audio_relay = configure_audio_relay(
        config_, audio_device, audio_sample_rate);
    const int effective_audio_sample_rate = audio_relay.value(
        "sample_rate_hz", audio_sample_rate > 0 ? audio_sample_rate : 48000);
    const int channel_count = sets.at(device_set_index).value("channelcount", 0);
    Json create_payload{{"channelType", profile.channel_type}, {"direction", 0}};
    Json created = request_json(
        config_, http::verb::post,
        "/deviceset/" + std::to_string(device_set_index) + "/channel", &create_payload);

    int channel_index = created.value("channelIndex", created.value("index", -1));
    for (int attempt = 0; channel_index < 0 && attempt < 20; ++attempt) {
        const auto current_sets = request_json(config_, http::verb::get, "/devicesets")
                                      .value("deviceSets", Json::array());
        if (device_set_index < static_cast<int>(current_sets.size()) &&
            current_sets.at(device_set_index).value("channelcount", 0) > channel_count) {
            channel_index = channel_count;
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    if (channel_index < 0) throw std::runtime_error("SDRangel channel creation did not complete");

    const std::string settings_path = "/deviceset/" + std::to_string(device_set_index) +
        "/channel/" + std::to_string(channel_index) + "/settings";
    Json applied = Json::object();
    std::string actual_settings_key;
    try {
        const Json current_response = request_json(config_, http::verb::get, settings_path);
        actual_settings_key = channel_settings_key(current_response, profile.settings_key);
        const Json& current = current_response.at(actual_settings_key);

        // Az indítás ugyanazt a megosztott, tesztelt settings-építőt használja,
        // mint az élő frissítés (updateDemodulator). Indításkor az audio-routing
        // is beállításra kerül (include_audio_routing = true).
        DemodulatorSettingsParams params;
        params.input_frequency_offset_hz = offset_hz;
        if (bandwidth_hz > 0) params.bandwidth_hz = bandwidth_hz;
        if (std::isfinite(squelch_db)) params.squelch_db = squelch_db;
        params.volume = volume;
        params.include_audio_routing = true;
        if (!audio_device.empty()) params.audio_device = audio_device;
        if (effective_audio_sample_rate > 0) params.audio_sample_rate = effective_audio_sample_rate;

        auto [settings, settings_applied] = buildDemodulatorChannelSettings(normalized, current, params);
        applied = settings_applied;

        if (!settings.empty()) {
            Json patch_payload{{actual_settings_key, settings}};
            if (current_response.contains("channelType")) {
                patch_payload["channelType"] = current_response.at("channelType");
            } else {
                patch_payload["channelType"] = profile.channel_type;
            }
            if (current_response.contains("direction")) {
                patch_payload["direction"] = current_response.at("direction");
            } else {
                patch_payload["direction"] = 0;
            }
            request_json(config_, http::verb::patch, settings_path, &patch_payload);
        }
    } catch (...) {
        try {
            request_json(
                config_, http::verb::delete_,
                "/deviceset/" + std::to_string(device_set_index) + "/channel/" +
                    std::to_string(channel_index));
        } catch (...) {
        }
        throw;
    }

    const std::string run_path = "/deviceset/" + std::to_string(device_set_index) + "/device/run";
    std::string device_state = request_json(config_, http::verb::get, run_path).value("state", "");
    if (device_state != "running") {
        try {
            request_json(config_, http::verb::post, run_path);
            for (int attempt = 0; attempt < 20; ++attempt) {
                device_state = request_json(config_, http::verb::get, run_path).value("state", "");
                if (device_state == "running") break;
                std::this_thread::sleep_for(std::chrono::milliseconds(50));
            }
        } catch (...) {
            try {
                request_json(
                    config_, http::verb::delete_,
                    "/deviceset/" + std::to_string(device_set_index) + "/channel/" +
                        std::to_string(channel_index));
            } catch (...) {
            }
            throw;
        }
    }
    if (device_state != "running") {
        try {
            request_json(
                config_, http::verb::delete_,
                "/deviceset/" + std::to_string(device_set_index) + "/channel/" +
                    std::to_string(channel_index));
        } catch (...) {
        }
        throw std::runtime_error("SDRangel device did not enter running state");
    }

    Json audio_output = audio_relay;
    audio_output.update(Json{{"enabled", profile.audio_output},
                             {"volume", volume},
                             {"muted", false},
                             {"sample_rate_hz_requested", audio_sample_rate > 0
                                 ? Json(audio_sample_rate) : Json(nullptr)}});

    return Json{{"status", "ok"},
                {"demodulator", normalized},
                {"channel_type", profile.channel_type},
                {"settings_key", actual_settings_key},
                {"device_set_index", device_set_index},
                {"channel_index", channel_index},
                {"device_state", device_state},
                {"bandwidth_hz_requested", bandwidth_hz > 0 ? Json(bandwidth_hz) : Json(nullptr)},
                {"squelch_db_requested", std::isfinite(squelch_db) ? Json(squelch_db) : Json(nullptr)},
                {"audio_output", audio_output},
                {"applied_settings", applied},
                {"remote", created}}.dump();
}

std::string SdrangelClient::updateDemodulator(
    const std::string& demodulator,
    int device_set_index,
    int channel_index,
    std::optional<std::int64_t> input_frequency_offset_hz,
    std::optional<int> bandwidth_hz,
    std::optional<double> squelch_db,
    std::optional<double> volume,
    std::optional<std::uint64_t> retune_device_center_hz) const {
    if (!config_.enabled) throw std::runtime_error("SDRangel integration is disabled");
    if (device_set_index < 0) device_set_index = config_.default_device_set_index;
    if (channel_index < 0) throw std::runtime_error("channel_index is required");

    const std::string normalized = normalized_demodulator(demodulator);
    const DemodulatorProfile profile = demodulator_profile(normalized);

    // Opcionális DeviceSet retune: ha a kiválasztott frekvencia kívül esik az
    // aktuális IQ capture tartományon, a hívó kéri a központi frekvencia
    // áthangolását, és a channel offset 0-ra áll. Egyébként csak az
    // inputFrequencyOffset módosul — nem hangoljuk újra a teljes eszközt minden
    // apró passband-mozdulatnál.
    Json retune_remote = nullptr;
    if (retune_device_center_hz.has_value()) {
        retune_remote = Json::parse(tune(*retune_device_center_hz, device_set_index));
        input_frequency_offset_hz = static_cast<std::int64_t>(0);
    }

    const std::string settings_path = "/deviceset/" + std::to_string(device_set_index) +
        "/channel/" + std::to_string(channel_index) + "/settings";
    const Json current_response = request_json(config_, http::verb::get, settings_path);
    const std::string actual_settings_key = channel_settings_key(current_response, profile.settings_key);
    const Json& current = current_response.at(actual_settings_key);

    DemodulatorSettingsParams params;
    params.input_frequency_offset_hz = input_frequency_offset_hz;
    if (bandwidth_hz.has_value() && *bandwidth_hz > 0) params.bandwidth_hz = *bandwidth_hz;
    params.squelch_db = squelch_db;
    params.volume = volume;
    params.include_audio_routing = false;  // élő frissítés nem konfigurálja újra a hangkimenetet

    auto [settings, applied] = buildDemodulatorChannelSettings(normalized, current, params);

    // A meglévő csatorna settings végpontját PATCH-eljük; NEM hozunk létre és
    // NEM törlünk csatornát.
    Json remote = nullptr;
    if (!settings.empty()) {
        Json patch_payload{{actual_settings_key, settings}};
        if (current_response.contains("channelType")) {
            patch_payload["channelType"] = current_response.at("channelType");
        } else {
            patch_payload["channelType"] = profile.channel_type;
        }
        if (current_response.contains("direction")) {
            patch_payload["direction"] = current_response.at("direction");
        } else {
            patch_payload["direction"] = 0;
        }
        remote = request_json(config_, http::verb::patch, settings_path, &patch_payload);
    }

    return Json{{"status", "ok"},
                {"demodulator", normalized},
                {"device_set_index", device_set_index},
                {"channel_index", channel_index},
                {"settings_key", actual_settings_key},
                {"applied_settings", applied},
                {"input_frequency_offset_hz",
                 input_frequency_offset_hz.has_value() ? Json(*input_frequency_offset_hz) : Json(nullptr)},
                {"bandwidth_hz", bandwidth_hz.has_value() ? Json(*bandwidth_hz) : Json(nullptr)},
                {"retuned", retune_device_center_hz.has_value()},
                {"retune_remote", retune_remote},
                {"remote", remote}}.dump();
}

std::string SdrangelClient::stopDemodulator(int device_set_index, int channel_index) const {
    if (!config_.enabled) throw std::runtime_error("SDRangel integration is disabled");
    if (device_set_index < 0) device_set_index = config_.default_device_set_index;
    if (channel_index < 0) throw std::runtime_error("channel_index is required");
    Json remote = request_json(
        config_, http::verb::delete_,
        "/deviceset/" + std::to_string(device_set_index) + "/channel/" +
            std::to_string(channel_index));
    return Json{{"status", "ok"}, {"device_set_index", device_set_index},
                {"channel_index", channel_index}, {"remote", remote}}.dump();
}

}  // namespace rf_agent

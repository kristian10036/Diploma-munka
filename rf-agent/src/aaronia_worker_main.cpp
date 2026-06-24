#include <nlohmann/json.hpp>

#include <dlfcn.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cctype>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <thread>
#include <stdexcept>
#include <utility>
#include <vector>

namespace {
using Json = nlohmann::json;
using Result = std::uint32_t;
constexpr Result kOk = 0;
constexpr Result kEmpty = 1;
constexpr std::uint64_t kOverflow = 0x100;
constexpr std::uint64_t kDropped = 0x200;
constexpr std::uint64_t kInaccurate = 0x400;

struct Handle { void* d; };
struct Device { void* d; };
struct Config { void* d; };
enum class ConfigType : std::int32_t { Other, Group, Blob, Number, Bool, Enum, String };
struct ConfigInfo {
    std::int64_t cbsize;
    wchar_t name[80];
    wchar_t title[120];
    ConfigType type;
    double min_value, max_value, step_value;
    wchar_t unit[10];
    wchar_t options[1000];
    std::uint64_t disabled_options;
};
struct DeviceInfo {
    std::int64_t cbsize;
    wchar_t serial_number[120];
    bool ready;
    bool boost;
    bool superspeed;
    bool active;
};
struct Packet {
    std::int64_t cbsize;
    std::uint64_t stream_id;
    std::uint64_t flags;
    double start_time;
    double end_time;
    double start_frequency;
    double step_frequency;
    double span_frequency;
    double rbw_frequency;
    std::int64_t num;
    std::int64_t total;
    std::int64_t size;
    std::int64_t stride;
    float* fp32;
    std::int64_t interleave;
};

using Init = Result (*)(std::uint32_t, const wchar_t*);
using Shutdown = Result (*)();
using Open = Result (*)(Handle*);
using Close = Result (*)(Handle*);
using Rescan = Result (*)(Handle*, int);
using Enumerate = Result (*)(Handle*, const wchar_t*, std::int32_t, DeviceInfo*);
using OpenDevice = Result (*)(Handle*, Device*, const wchar_t*, const wchar_t*);
using CloseDevice = Result (*)(Handle*, Device*);
using ConnectDevice = Result (*)(Device*);
using DisconnectDevice = Result (*)(Device*);
using StartDevice = Result (*)(Device*);
using StopDevice = Result (*)(Device*);
using ConfigRoot = Result (*)(Device*, Config*);
using ConfigHealth = Result (*)(Device*, Config*);
using ConfigFirst = Result (*)(Device*, Config*, Config*);
using ConfigNext = Result (*)(Device*, Config*, Config*);
using ConfigFind = Result (*)(Device*, Config*, Config*, const wchar_t*);
using ConfigGetInfo = Result (*)(Device*, Config*, ConfigInfo*);
using ConfigGetString = Result (*)(Device*, Config*, wchar_t*, std::int64_t*);
using ConfigSetString = Result (*)(Device*, Config*, const wchar_t*);
using ConfigSetFloat = Result (*)(Device*, Config*, double);
using GetPacket = Result (*)(Device*, std::int32_t, std::int32_t, Packet*);
using ConsumePackets = Result (*)(Device*, std::int32_t, std::int32_t);

std::atomic_bool stop_requested{false};
void stop_handler(int) { stop_requested.store(true); }

std::string env(const char* name, const char* fallback) {
    const char* value = std::getenv(name);
    return value && *value ? value : fallback;
}
double env_double(const char* name, double fallback) {
    try { return std::stod(env(name, "")); } catch (...) { return fallback; }
}
std::uint64_t env_u64(const char* name, std::uint64_t fallback) {
    try { return std::stoull(env(name, "")); } catch (...) { return fallback; }
}
std::wstring widen(const std::string& value) { return {value.begin(), value.end()}; }
std::string narrow(const wchar_t* value) {
    std::string result;
    while (value && *value) { result.push_back(*value <= 0x7f ? static_cast<char>(*value) : '?'); ++value; }
    return result;
}

std::string lower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

std::string config_string(Device* device, Config* item, ConfigGetString get_string) {
    std::int64_t size = 0;
    if (get_string(device, item, nullptr, &size) != kOk || size <= 0 || size > 4096) return {};
    std::vector<wchar_t> value(static_cast<std::size_t>(size));
    if (get_string(device, item, value.data(), &size) != kOk) return {};
    return narrow(value.data());
}

struct DeviceMetadata {
    std::string model;
    std::uint64_t available_rtbw_hz{0};
};

std::uint64_t maximum_frequency_option_hz(const std::string& text) {
    std::uint64_t result = 0;
    std::string token;
    for (std::size_t index = 0; index <= text.size(); ++index) {
        const char c = index < text.size() ? text[index] : ';';
        if (c == ';' || c == ',') {
            try {
                const std::string normalized = lower(token);
                const double value = std::stod(normalized);
                const double multiplier = normalized.find("ghz") != std::string::npos ? 1e9 :
                    normalized.find("mhz") != std::string::npos ? 1e6 :
                    normalized.find("khz") != std::string::npos ? 1e3 : 1.0;
                result = std::max(result, static_cast<std::uint64_t>(std::llround(value * multiplier)));
            } catch (...) {}
            token.clear();
        } else token.push_back(c);
    }
    return result;
}

void inspect_config_tree(Device* device, Config group, ConfigFirst first, ConfigNext next,
                         ConfigGetInfo get_info, ConfigGetString get_string,
                         DeviceMetadata& metadata, int depth = 0) {
    if (depth > 12) return;
    Config item{};
    if (first(device, &group, &item) != kOk) return;
    do {
        ConfigInfo info{}; info.cbsize = sizeof(info);
        if (get_info(device, &item, &info) == kOk) {
            const std::string name = narrow(info.name);
            const std::string title = narrow(info.title);
            const std::string key = lower(name + " " + title);
            const std::string value = config_string(device, &item, get_string);
            if (metadata.model.empty() &&
                (key.find("model") != std::string::npos || key.find("product") != std::string::npos) &&
                !value.empty()) metadata.model = value;
            if (key.find("rtbw") != std::string::npos || key.find("receiverclock") != std::string::npos ||
                key.find("real time bandwidth") != std::string::npos) {
                metadata.available_rtbw_hz = std::max(metadata.available_rtbw_hz,
                    maximum_frequency_option_hz(narrow(info.options) + ";" + value));
            }
            if (info.type == ConfigType::Group) {
                inspect_config_tree(device, item, first, next, get_info, get_string, metadata, depth + 1);
            }
        }
    } while (next(device, &group, &item) == kOk);
}
std::string iso_now() {
    const auto now = std::chrono::system_clock::now();
    const auto time = std::chrono::system_clock::to_time_t(now);
    std::tm value{};
    gmtime_r(&time, &value);
    std::ostringstream output;
    output << std::put_time(&value, "%Y-%m-%dT%H:%M:%S") << '.' << std::setfill('0')
           << std::setw(3) << (std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()).count() % 1000)
           << 'Z';
    return output.str();
}

template <typename T>
T symbol(void* library, const char* name) {
    auto value = reinterpret_cast<T>(dlsym(library, name));
    if (!value) throw std::runtime_error(std::string("missing SDK symbol: ") + name);
    return value;
}

void require(Result result, const char* operation) {
    if ((result & 0x80000000U) != 0) {
        std::ostringstream message;
        message << operation << " failed: 0x" << std::hex << result;
        throw std::runtime_error(message.str());
    }
}

void set_string(Device* device, Config* root, ConfigFind find, ConfigSetString set,
                const wchar_t* path, const wchar_t* value) {
    Config item{};
    require(find(device, root, &item, path), "AARTSAAPI_ConfigFind");
    require(set(device, &item, value), "AARTSAAPI_ConfigSetString");
}
void set_float(Device* device, Config* root, ConfigFind find, ConfigSetFloat set,
               const wchar_t* path, double value) {
    Config item{};
    require(find(device, root, &item, path), "AARTSAAPI_ConfigFind");
    require(set(device, &item, value), "AARTSAAPI_ConfigSetFloat");
}

std::vector<double> downsample(const float* input, std::size_t size, std::size_t maximum,
                               std::size_t& factor) {
    factor = std::max<std::size_t>(1, (size + maximum - 1) / maximum);
    const std::size_t output_size = (size + factor - 1) / factor;
    std::vector<double> output;
    output.reserve(output_size);
    for (std::size_t start = 0; start < size; start += factor) {
        double peak = -std::numeric_limits<double>::infinity();
        for (std::size_t index = start; index < std::min(size, start + factor); ++index) {
            if (std::isfinite(input[index])) peak = std::max(peak, static_cast<double>(input[index]));
        }
        output.push_back(std::isfinite(peak) ? peak : -200.0);
    }
    return output;
}
}

int main() {
    std::signal(SIGTERM, stop_handler);
    std::signal(SIGINT, stop_handler);
    void* library = nullptr;
    Handle handle{};
    Device device{};
    bool initialized = false, opened = false, device_open = false, connected = false, started = false;
    try {
        const std::string library_path = env("AARONIA_RTSA_LIBRARY_PATH", "/opt/aaronia-rtsa-suite/Aaronia-RTSA-Suite-PRO/libAaroniaRTSAAPI.so");
        const std::string xml_path = env("AARONIA_XML_PATH", "/opt/aaronia-rtsa-suite/Aaronia-RTSA-Suite-PRO");
        const std::string sensor_id = env("AARONIA_SENSOR_ID", "aaronia-v6-01");
        const std::string session_id = env("AARONIA_SESSION_ID", "aaronia-live");
        const auto requested_start_hz =
            env_u64("AARONIA_START_FREQUENCY_HZ", 75'000'000ULL);
        const auto requested_stop_hz =
            env_u64("AARONIA_STOP_FREQUENCY_HZ", 6'000'000'000ULL);
        const std::string receiver_clock = env("AARONIA_RECEIVER_CLOCK", "245MHz");
        const double rbw_hz = env_double("AARONIA_RBW_HZ", 100'000.0);
        const double reference_dbm = env_double("AARONIA_REFERENCE_LEVEL_DBM", -20.0);
        const auto max_points = std::clamp<std::uint64_t>(env_u64("AARONIA_MAX_SPECTRUM_POINTS", 16'384), 2, 65'536);
        const double max_fps = std::clamp(env_double("AARONIA_MAX_FPS", 10.0), 0.1, 100.0);
        if (requested_start_hz == 0 || requested_start_hz >= requested_stop_hz) {
            throw std::runtime_error("invalid Aaronia start/stop configuration");
        }
        if (receiver_clock.empty()) throw std::runtime_error("invalid Aaronia receiver clock");
        if (rbw_hz <= 0) throw std::runtime_error("invalid RBW configuration");

        library = dlopen(library_path.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!library) {
            const char* error = dlerror();
            throw std::runtime_error(error ? error : "dlopen failed");
        }
        const auto init = symbol<Init>(library, "AARTSAAPI_Init_With_Path");
        const auto shutdown = symbol<Shutdown>(library, "AARTSAAPI_Shutdown");
        const auto api_open = symbol<Open>(library, "AARTSAAPI_Open");
        const auto api_close = symbol<Close>(library, "AARTSAAPI_Close");
        const auto rescan = symbol<Rescan>(library, "AARTSAAPI_RescanDevices");
        const auto enumerate = symbol<Enumerate>(library, "AARTSAAPI_EnumDevice");
        const auto open_device = symbol<OpenDevice>(library, "AARTSAAPI_OpenDevice");
        const auto close_device = symbol<CloseDevice>(library, "AARTSAAPI_CloseDevice");
        const auto connect_device = symbol<ConnectDevice>(library, "AARTSAAPI_ConnectDevice");
        const auto disconnect_device = symbol<DisconnectDevice>(library, "AARTSAAPI_DisconnectDevice");
        const auto start_device = symbol<StartDevice>(library, "AARTSAAPI_StartDevice");
        const auto stop_device = symbol<StopDevice>(library, "AARTSAAPI_StopDevice");
        const auto config_root = symbol<ConfigRoot>(library, "AARTSAAPI_ConfigRoot");
        const auto config_find = symbol<ConfigFind>(library, "AARTSAAPI_ConfigFind");
        const auto config_get_info = symbol<ConfigGetInfo>(library, "AARTSAAPI_ConfigGetInfo");
        const auto config_get_string = symbol<ConfigGetString>(library, "AARTSAAPI_ConfigGetString");
        const auto config_set_string = symbol<ConfigSetString>(library, "AARTSAAPI_ConfigSetString");
        const auto config_set_float = symbol<ConfigSetFloat>(library, "AARTSAAPI_ConfigSetFloat");
        const auto get_packet = symbol<GetPacket>(library, "AARTSAAPI_GetPacket");
        const auto consume_packets = symbol<ConsumePackets>(library, "AARTSAAPI_ConsumePackets");

        require(init(1, widen(xml_path).c_str()), "AARTSAAPI_Init_With_Path"); initialized = true;
        require(api_open(&handle), "AARTSAAPI_Open"); opened = true;
        require(rescan(&handle, 5000), "AARTSAAPI_RescanDevices");
        DeviceInfo info{}; info.cbsize = sizeof(info);
        require(enumerate(&handle, L"spectranv6", 0, &info), "AARTSAAPI_EnumDevice");
        require(open_device(&handle, &device, L"spectranv6/sweepsa", info.serial_number), "AARTSAAPI_OpenDevice"); device_open = true;
        Config root{}; require(config_root(&device, &root), "AARTSAAPI_ConfigRoot");
        DeviceMetadata device_metadata;
        set_string(&device, &root, config_find, config_set_string, L"device/receiverchannel", L"Rx1");
        Config receiver_clock_item{};
        if (config_find(&device, &root, &receiver_clock_item, L"device/receiverclock") == kOk) {
            ConfigInfo clock_info{}; clock_info.cbsize = sizeof(clock_info);
            if (config_get_info(&device, &receiver_clock_item, &clock_info) == kOk) {
                device_metadata.available_rtbw_hz = maximum_frequency_option_hz(narrow(clock_info.options));
            }
            const Result clock_result =
                config_set_string(&device, &receiver_clock_item, widen(receiver_clock).c_str());
            require(clock_result, "AARTSAAPI_ConfigSetString(receiverclock)");
        }
        Config start_item{}, stop_item{};
        require(config_find(&device, &root, &start_item, L"main/startfreq"), "AARTSAAPI_ConfigFind(startfreq)");
        require(config_find(&device, &root, &stop_item, L"main/stopfreq"), "AARTSAAPI_ConfigFind(stopfreq)");
        ConfigInfo start_info{}; start_info.cbsize = sizeof(start_info);
        ConfigInfo stop_info{}; stop_info.cbsize = sizeof(stop_info);
        require(config_get_info(&device, &start_item, &start_info), "AARTSAAPI_ConfigGetInfo(startfreq)");
        require(config_get_info(&device, &stop_item, &stop_info), "AARTSAAPI_ConfigGetInfo(stopfreq)");
        const auto hardware_min_hz =
            static_cast<std::uint64_t>(std::ceil(start_info.min_value));
        const auto hardware_max_hz =
            static_cast<std::uint64_t>(std::floor(stop_info.max_value));
        if (hardware_min_hz == 0 || hardware_min_hz >= hardware_max_hz) {
            throw std::runtime_error("SDK returned an invalid or DC-inclusive hardware sweep range");
        }

        const auto start_hz = std::clamp(requested_start_hz, hardware_min_hz, hardware_max_hz - 1);
        const auto stop_hz = std::clamp(requested_stop_hz, start_hz + 1, hardware_max_hz);
        if (start_hz >= stop_hz) throw std::runtime_error("requested sweep is outside the hardware range");

        require(config_set_float(&device, &start_item, static_cast<double>(start_hz)), "AARTSAAPI_ConfigSetFloat(startfreq)");
        require(config_set_float(&device, &stop_item, static_cast<double>(stop_hz)), "AARTSAAPI_ConfigSetFloat(stopfreq)");
        Config rbw_item{};
        require(config_find(&device, &root, &rbw_item, L"main/rbwfreq"), "AARTSAAPI_ConfigFind(rbwfreq)");
        ConfigInfo rbw_info{}; rbw_info.cbsize = sizeof(rbw_info);
        require(config_get_info(&device, &rbw_item, &rbw_info), "AARTSAAPI_ConfigGetInfo(rbwfreq)");
        // The previous implementation divided the whole hardware range by
        // AARONIA_OVERVIEW_TARGET_POINTS (512 in the existing .env), which
        // forced a ~10 MHz RBW and attempted an 18 GHz sweep at startup.
        // Use the actual transport point budget instead. This keeps the first
        // startup close to Aaronia's official SweepSpectrum sample and avoids
        // the SDK abort observed during AARTSAAPI_StartDevice.
        const double overview_rbw = std::clamp(
            std::max(rbw_hz, static_cast<double>(stop_hz - start_hz) /
                static_cast<double>(max_points)),
            rbw_info.min_value, rbw_info.max_value);
        require(config_set_float(&device, &rbw_item, overview_rbw), "AARTSAAPI_ConfigSetFloat(rbwfreq)");
        set_float(&device, &root, config_find, config_set_float, L"main/reflevel", reference_dbm);
        if (device_metadata.model.empty()) {
            std::ostringstream model;
            model << "SPECTRAN V6 " << (static_cast<double>(stop_hz) / 1e9) << " GHz";
            if (device_metadata.available_rtbw_hz > 0) {
                model << " / " << (static_cast<double>(device_metadata.available_rtbw_hz) / 1e6)
                      << " MHz RTBW";
            }
            device_metadata.model = model.str();
        }
        require(connect_device(&device), "AARTSAAPI_ConnectDevice"); connected = true;
        std::cerr << "aaronia_worker_config model=\"" << device_metadata.model
                  << "\" hardware_min_hz=" << hardware_min_hz
                  << " hardware_max_hz=" << hardware_max_hz
                  << " start_hz=" << start_hz << " stop_hz=" << stop_hz
                  << " receiver_clock=" << receiver_clock
                  << " rbw_hz=" << overview_rbw
                  << " available_rtbw_hz=" << device_metadata.available_rtbw_hz << '\n';
        require(start_device(&device), "AARTSAAPI_StartDevice"); started = true;

        std::uint64_t sequence = 0, hardware_dropped = 0;
        auto next_emit = std::chrono::steady_clock::now();
        const auto interval = std::chrono::duration<double>(1.0 / max_fps);
        while (!stop_requested.load()) {
            Packet packet{}; packet.cbsize = sizeof(packet);
            const Result result = get_packet(&device, 0, 0, &packet);
            if (result == kEmpty) { std::this_thread::sleep_for(std::chrono::milliseconds(5)); continue; }
            require(result, "AARTSAAPI_GetPacket");
            if (!packet.fp32 || packet.size < 2 || packet.num < 1 || packet.step_frequency <= 0) {
                consume_packets(&device, 0, 1);
                continue;
            }
            for (std::int64_t sample = 0; sample < packet.num; ++sample) {
                const auto now = std::chrono::steady_clock::now();
                // Rate limiting happens before a SpectrumFrame exists, so it is
                // not a dropped frame. SDK drop flags remain measurable below.
                if (now < next_emit) continue;
                next_emit = now + std::chrono::duration_cast<std::chrono::steady_clock::duration>(interval);
                std::size_t factor = 1;
                auto powers = downsample(packet.fp32 + sample * packet.stride,
                                         static_cast<std::size_t>(packet.size),
                                         static_cast<std::size_t>(max_points), factor);
                const auto start = static_cast<std::uint64_t>(std::llround(packet.start_frequency));
                const auto step = std::max<std::uint64_t>(1, static_cast<std::uint64_t>(std::llround(packet.step_frequency * factor)));
                const auto stop = start + step * (powers.size() - 1);
                const bool packet_dropped = (packet.flags & kDropped) != 0;
                if (packet_dropped) ++hardware_dropped;
                Json frame{{"schema_version", 1}, {"sensor_id", sensor_id}, {"source_type", "aaronia"},
                           {"source_device", narrow(info.serial_number)}, {"session_id", session_id},
                           {"device_model", device_metadata.model}, {"measurement_mode", "sweepsa"},
                           {"timestamp", iso_now()}, {"sequence", sequence++},
                           {"center_frequency_hz", start + (stop - start) / 2},
                           {"start_frequency_hz", start}, {"stop_frequency_hz", stop},
                           {"step_frequency_hz", step}, {"sample_rate_hz", std::max<std::uint64_t>(1, stop - start)},
                           {"rbw_hz", packet.rbw_frequency > 0 ? packet.rbw_frequency : rbw_hz},
                           {"point_count", powers.size()}, {"powers_dbm", std::move(powers)},
                           {"overflow", (packet.flags & kOverflow) != 0},
                           {"dropped", packet_dropped},
                           {"inaccurate", (packet.flags & kInaccurate) != 0},
                           {"worker_dropped_frames", hardware_dropped},
                           {"hardware_min_frequency_hz", hardware_min_hz},
                           {"hardware_max_frequency_hz", hardware_max_hz},
                           {"available_rtbw_hz", device_metadata.available_rtbw_hz}};
                std::cout << frame.dump() << '\n' << std::flush;
            }
            consume_packets(&device, 0, 1);
        }
        if (started) stop_device(&device);
        if (connected) disconnect_device(&device);
        if (device_open) close_device(&handle, &device);
        if (opened) api_close(&handle);
        if (initialized) shutdown();
        dlclose(library);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "aaronia_worker_error: " << error.what() << '\n';
        // The process boundary is the crash/reconnect isolation. Normal SDK
        // cleanup is attempted on the success path; the OS reclaims resources
        // after failed initialization.
        std::cerr.flush();
        _Exit(2);
    }
}

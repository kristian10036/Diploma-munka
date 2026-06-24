#include <nlohmann/json.hpp>

#include <cpuid.h>
#include <dlfcn.h>

#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <string>

namespace {

using Json = nlohmann::json;
using Result = std::uint32_t;
using InitWithPath = Result (*)(std::uint32_t, const wchar_t*);
using Shutdown = Result (*)();
struct ApiHandle { void* data; };
struct DeviceInfo {
    std::int64_t cbsize;
    wchar_t serial_number[120];
    bool ready;
    bool boost;
    bool superspeed;
    bool active;
};
using Open = Result (*)(ApiHandle*);
using Close = Result (*)(ApiHandle*);
using RescanDevices = Result (*)(ApiHandle*, int);
using EnumDevice = Result (*)(ApiHandle*, const wchar_t*, std::int32_t, DeviceInfo*);

constexpr Result kOk = 0;
constexpr std::uint32_t kMemoryMedium = 1;

std::string environment(const char* name, const char* fallback) {
    const char* value = std::getenv(name);
    return value && *value ? value : fallback;
}

std::wstring widen_ascii(const std::string& value) {
    return std::wstring(value.begin(), value.end());
}

std::string narrow_ascii(const wchar_t* value) {
    std::string result;
    while (value && *value) {
        result.push_back(*value <= 0x7f ? static_cast<char>(*value) : '?');
        ++value;
    }
    return result;
}

Json cpu_features() {
    unsigned int eax = 0, ebx = 0, ecx = 0, edx = 0;
    bool avx = false;
    bool avx2 = false;
    if (__get_cpuid(1, &eax, &ebx, &ecx, &edx)) avx = (ecx & bit_AVX) != 0;
    if (__get_cpuid_count(7, 0, &eax, &ebx, &ecx, &edx)) avx2 = (ebx & bit_AVX2) != 0;
    return Json{{"avx", avx}, {"avx2", avx2}};
}

int emit(Json result, int exit_code) {
    result["backend"] = "aaronia";
    result["cpu_features"] = cpu_features();
    std::cout << result.dump() << '\n';
    return exit_code;
}

}  // namespace

int main() {
    const std::filesystem::path library = environment(
        "AARONIA_RTSA_LIBRARY_PATH",
        "/opt/aaronia-rtsa-suite/Aaronia-RTSA-Suite-PRO/libAaroniaRTSAAPI.so");
    const std::string xml_path = environment(
        "AARONIA_XML_PATH", "/opt/aaronia-rtsa-suite/Aaronia-RTSA-Suite-PRO");

    Json base{{"probe_attempted", true}, {"library_path", library.string()},
              {"xml_path", xml_path}};
    if (!std::filesystem::is_regular_file(library)) {
        base["probe_result"] = "library_not_found";
        base["available"] = false;
        return emit(std::move(base), 2);
    }
    if (!cpu_features().value("avx2", false)) {
        base["probe_result"] = "incompatible_cpu";
        base["available"] = false;
        base["diagnostic"] = "Aaronia RTSA API requires AVX2 on this installation";
        return emit(std::move(base), 6);
    }

    void* handle = dlopen(library.c_str(), RTLD_NOW | RTLD_LOCAL);
    if (!handle) {
        const char* load_error = dlerror();
        const std::string diagnostic = load_error ? load_error : "dlopen failed without diagnostic";
        base["probe_result"] = diagnostic.find("wrong ELF class") != std::string::npos ||
                diagnostic.find("Exec format") != std::string::npos
            ? "incompatible_architecture" : "dependency_missing";
        base["available"] = false;
        base["diagnostic"] = diagnostic;
        return emit(std::move(base), 3);
    }

    dlerror();
    auto init = reinterpret_cast<InitWithPath>(dlsym(handle, "AARTSAAPI_Init_With_Path"));
    auto shutdown = reinterpret_cast<Shutdown>(dlsym(handle, "AARTSAAPI_Shutdown"));
    auto open = reinterpret_cast<Open>(dlsym(handle, "AARTSAAPI_Open"));
    auto close = reinterpret_cast<Close>(dlsym(handle, "AARTSAAPI_Close"));
    auto rescan = reinterpret_cast<RescanDevices>(dlsym(handle, "AARTSAAPI_RescanDevices"));
    auto enumerate = reinterpret_cast<EnumDevice>(dlsym(handle, "AARTSAAPI_EnumDevice"));
    const char* symbol_error = dlerror();
    if (symbol_error || !init || !shutdown || !open || !close || !rescan || !enumerate) {
        base["probe_result"] = "dependency_missing";
        base["available"] = false;
        base["diagnostic"] = symbol_error ? symbol_error : "required symbol is null";
        dlclose(handle);
        return emit(std::move(base), 4);
    }

    const Result init_result = init(kMemoryMedium, widen_ascii(xml_path).c_str());
    base["sdk_init_result"] = init_result;
    if (init_result != kOk) {
        base["probe_result"] = "initialization_failed";
        base["available"] = false;
        dlclose(handle);
        return emit(std::move(base), 5);
    }

    ApiHandle api_handle{};
    const Result open_result = open(&api_handle);
    base["sdk_open_result"] = open_result;
    bool device_found = false;
    if (open_result == kOk) {
        const Result rescan_result = rescan(&api_handle, 5000);
        base["device_rescan_result"] = rescan_result;
        if (rescan_result == kOk) {
            DeviceInfo info{};
            info.cbsize = sizeof(info);
            const Result enumerate_result = enumerate(&api_handle, L"spectranv6", 0, &info);
            base["device_enumeration_result"] = enumerate_result;
            if (enumerate_result == kOk) {
                device_found = true;
                base["device"] = Json{{"serial_number", narrow_ascii(info.serial_number)},
                                      {"ready", info.ready}, {"boost", info.boost},
                                      {"superspeed", info.superspeed}, {"active", info.active}};
            }
        }
        base["sdk_close_result"] = close(&api_handle);
    }
    const Result shutdown_result = shutdown();
    base["sdk_shutdown_result"] = shutdown_result;
    base["probe_result"] = device_found ? "running" : "device_not_connected";
    base["library_status"] = "running";
    base["device_status"] = device_found ? "running" : "device_not_connected";
    base["diagnostic"] = device_found
        ? "SPECTRAN V6 discovered; spectrum streaming remains a separate capability"
        : "SDK initialized but no SPECTRAN V6 was enumerated";
    base["available"] = true;
    dlclose(handle);
    return emit(std::move(base), 0);
}

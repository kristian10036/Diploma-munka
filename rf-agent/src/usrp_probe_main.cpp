#include <nlohmann/json.hpp>
#include <uhd/device.hpp>
#include <uhd/version.hpp>

#include <cstdlib>
#include <exception>
#include <iostream>
#include <string>

int main() {
    using Json = nlohmann::json;
    const char* raw_args = std::getenv("USRP_DEVICE_ARGS");
    const std::string args = raw_args ? raw_args : "";
    try {
        const auto devices = uhd::device::find(uhd::device_addr_t(args));
        Json items = Json::array();
        for (const auto& device : devices) {
            Json value = Json::object();
            for (const auto& key : device.keys()) value[key] = device[key];
            items.push_back(std::move(value));
        }
        const bool available = !devices.empty();
        std::cout << Json{{"backend", "usrp"},
                          {"probe_attempted", true},
                          {"probe_result", available ? "device_found" : "no_devices"},
                          {"available", available},
                          {"device_args", args},
                          {"uhd_version", uhd::get_version_string()},
                          {"devices", items},
                          {"data_plane", "soapy_iq_spectrum_native_audio"}}.dump() << '\n';
        return available ? 0 : 2;
    } catch (const std::exception& error) {
        std::cout << Json{{"backend", "usrp"},
                          {"probe_attempted", true},
                          {"probe_result", "uhd_error"},
                          {"available", false},
                          {"device_args", args},
                          {"diagnostic", error.what()},
                          {"data_plane", "soapy_iq_spectrum_native_audio"}}.dump() << '\n';
        return 3;
    }
}

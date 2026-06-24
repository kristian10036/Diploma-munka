#include "rf_agent/sdrangel_client.hpp"
#include <nlohmann/json.hpp>
#include <cassert>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <arpa/inet.h>
#include <chrono>
#include <sys/socket.h>
#include <thread>
#include <unistd.h>

std::thread test_server(int port, std::string body, int requests = 1, int delay_ms = 0) {
    const int server = socket(AF_INET, SOCK_STREAM, 0);
    int reuse = 1;
    setsockopt(server, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = htons(static_cast<std::uint16_t>(port));
    assert(bind(server, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == 0);
    assert(listen(server, requests) == 0);
    return std::thread([server, body = std::move(body), requests, delay_ms]() {
        for (int index = 0; index < requests; ++index) {
            const int client = accept(server, nullptr, nullptr);
            char buffer[2048];
            recv(client, buffer, sizeof(buffer), 0);
            if (delay_ms) std::this_thread::sleep_for(std::chrono::milliseconds(delay_ms));
            const std::string response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " +
                std::to_string(body.size()) + "\r\nConnection: close\r\n\r\n" + body;
            send(client, response.data(), response.size(), MSG_NOSIGNAL);
            close(client);
        }
        close(server);
    });
}

int main() {
    using Json = nlohmann::json;
    using namespace rf_agent;

    SdrangelConfig disabled;
    disabled.enabled = false;
    SdrangelClient client(disabled);
    const auto status = Json::parse(client.status());
    assert(status.at("status") == "disabled");
    assert(status.at("control_plane") == "disabled");
    assert(status.at("data_plane") == "not_configured");

    bool rejected = false;
    try {
        client.tune(100000000, 0);
    } catch (const std::runtime_error&) {
        rejected = true;
    }
    assert(rejected);

    // updateDemodulator: letiltott integrációnál hibát ad, és a channel_index
    // kötelező. (A mezőkiválasztás részletes ellenőrzése a hálózatmentes
    // sdrangel_demod_settings_test-ben történik.)
    bool update_disabled_rejected = false;
    try {
        client.updateDemodulator("NFM", 0, 0, std::nullopt, 12500, std::nullopt, std::nullopt, std::nullopt);
    } catch (const std::runtime_error&) {
        update_disabled_rejected = true;
    }
    assert(update_disabled_rejected);

    {
        SdrangelConfig enabled_cfg;
        enabled_cfg.enabled = true;
        enabled_cfg.api_url = "http://127.0.0.1:1/sdrangel";  // nem hívjuk, csak validáció
        SdrangelClient enabled_client(enabled_cfg);
        bool missing_channel_rejected = false;
        try {
            enabled_client.updateDemodulator(
                "NFM", 0, -1, std::nullopt, 12500, std::nullopt, std::nullopt, std::nullopt);
        } catch (const std::runtime_error&) {
            missing_channel_rejected = true;
        }
        assert(missing_channel_rejected);
    }

    SdrangelConfig configured;
    configured.enabled = true;
    configured.api_url = "invalid://localhost";
    SdrangelClient invalid(configured);
    const auto invalid_status = Json::parse(invalid.status());
    assert(invalid_status.at("status") == "unreachable");
    assert(invalid_status.contains("diagnostic"));

    auto online_server = test_server(18091, R"({"version":"test"})");
    configured.api_url = "http://127.0.0.1:18091/sdrangel";
    SdrangelClient online(configured);
    const auto online_status = Json::parse(online.status());
    online_server.join();
    assert(online_status.at("status") == "ready");
    assert(online_status.at("last_successful_connection").is_string());

    auto invalid_json_server = test_server(18092, "not-json", 2);
    configured.api_url = "http://127.0.0.1:18092/sdrangel";
    SdrangelClient invalid_json(configured);
    const auto invalid_json_status = Json::parse(invalid_json.status());
    invalid_json_server.join();
    assert(invalid_json_status.at("status") == "unreachable");
    assert(invalid_json_status.at("diagnostic") == "SDRangel returned invalid JSON");

    auto timeout_server = test_server(18093, R"({"version":"late"})", 2, 250);
    configured.api_url = "http://127.0.0.1:18093/sdrangel";
    configured.timeout = std::chrono::milliseconds(50);
    SdrangelClient timeout(configured);
    const auto timeout_status = Json::parse(timeout.status());
    timeout_server.join();
    assert(timeout_status.at("status") == "unreachable");

    std::cout << "SDRangel client tests: OK\n";
    return 0;
}

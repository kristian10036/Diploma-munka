#include <chrono>
#include <csignal>
#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>

int main() {
    const char* raw = std::getenv("PROBE_TEST_MODE");
    const std::string mode = raw ? raw : "ok";
    if (mode == "sigill") std::raise(SIGILL);
    if (mode == "sigsegv") std::raise(SIGSEGV);
    if (mode == "timeout") std::this_thread::sleep_for(std::chrono::seconds(2));
    if (mode == "invalid") {
        std::cout << "not-json\n";
        return 9;
    }
    std::cout << R"({"backend":"aaronia","probe_attempted":true,"probe_result":"sdk_not_found","available":false})" << '\n';
    return 2;
}

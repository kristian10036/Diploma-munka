#include "rf_agent/usrp_probe_runner.hpp"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstring>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>
#include <utility>

namespace rf_agent {
namespace {

using Json = nlohmann::json;
constexpr std::size_t kMaxCapturedBytes = 64 * 1024;

void append_available(int descriptor, std::string& output) {
    std::array<char, 4096> buffer{};
    while (output.size() < kMaxCapturedBytes) {
        const auto count = read(descriptor, buffer.data(),
                                std::min(buffer.size(), kMaxCapturedBytes - output.size()));
        if (count > 0) {
            output.append(buffer.data(), static_cast<std::size_t>(count));
            continue;
        }
        if (count < 0 && errno == EINTR) continue;
        break;
    }
}

Json failure(const std::string& result, const std::string& message) {
    return Json{{"backend", "usrp"}, {"probe_attempted", true}, {"available", false},
                {"probe_result", result}, {"diagnostic", message},
                {"data_plane", "soapy_iq_spectrum_native_audio"}};
}

std::string signal_result(int signal) {
    if (signal == SIGILL) return "probe_sigill";
    if (signal == SIGSEGV) return "probe_sigsegv";
    return "probe_signal_failure";
}

}  // namespace

UsrpProbeRunner::UsrpProbeRunner(UsrpProbeConfig config)
    : config_(std::move(config)),
      last_result_(Json{{"backend", "usrp"}, {"enabled", config_.enabled},
                        {"probe_attempted", false}, {"available", false},
                        {"probe_result", config_.enabled ? "not_probed" : "disabled"},
                        {"data_plane", "soapy_iq_spectrum_native_audio"}}.dump()) {}

std::string UsrpProbeRunner::run() {
    if (!config_.enabled) return status();

    int stdout_pipe[2]{};
    int stderr_pipe[2]{};
    if (pipe(stdout_pipe) != 0 || pipe(stderr_pipe) != 0) {
        const auto result = failure("probe_launch_failed", std::strerror(errno)).dump();
        std::lock_guard<std::mutex> lock(mutex_);
        return last_result_ = result;
    }

    const pid_t child = fork();
    if (child < 0) {
        close(stdout_pipe[0]); close(stdout_pipe[1]);
        close(stderr_pipe[0]); close(stderr_pipe[1]);
        const auto result = failure("probe_launch_failed", std::strerror(errno)).dump();
        std::lock_guard<std::mutex> lock(mutex_);
        return last_result_ = result;
    }
    if (child == 0) {
        dup2(stdout_pipe[1], STDOUT_FILENO);
        dup2(stderr_pipe[1], STDERR_FILENO);
        close(stdout_pipe[0]); close(stdout_pipe[1]);
        close(stderr_pipe[0]); close(stderr_pipe[1]);
        if (!config_.device_args.empty()) setenv("USRP_DEVICE_ARGS", config_.device_args.c_str(), 1);
        execl(config_.executable.c_str(), config_.executable.c_str(), nullptr);
        _exit(127);
    }

    close(stdout_pipe[1]);
    close(stderr_pipe[1]);
    fcntl(stdout_pipe[0], F_SETFL, fcntl(stdout_pipe[0], F_GETFL) | O_NONBLOCK);
    fcntl(stderr_pipe[0], F_SETFL, fcntl(stderr_pipe[0], F_GETFL) | O_NONBLOCK);

    std::string standard_output;
    std::string standard_error;
    int wait_status = 0;
    bool timed_out = false;
    const auto deadline = std::chrono::steady_clock::now() + config_.timeout;
    while (waitpid(child, &wait_status, WNOHANG) == 0) {
        append_available(stdout_pipe[0], standard_output);
        append_available(stderr_pipe[0], standard_error);
        if (std::chrono::steady_clock::now() >= deadline) {
            timed_out = true;
            kill(child, SIGKILL);
            waitpid(child, &wait_status, 0);
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    append_available(stdout_pipe[0], standard_output);
    append_available(stderr_pipe[0], standard_error);
    close(stdout_pipe[0]);
    close(stderr_pipe[0]);

    Json result;
    if (timed_out) {
        result = failure("probe_timeout", "USRP probe exceeded its timeout");
    } else if (WIFSIGNALED(wait_status)) {
        const int signal = WTERMSIG(wait_status);
        result = failure(signal_result(signal), "USRP probe terminated by signal");
        result["signal"] = signal;
    } else {
        try {
            result = Json::parse(standard_output);
        } catch (const Json::exception&) {
            result = failure(
                WIFEXITED(wait_status) && WEXITSTATUS(wait_status) == 127
                    ? "probe_executable_not_found" : "invalid_probe_response",
                "USRP probe returned invalid JSON");
            if (!standard_output.empty()) result["stdout"] = standard_output;
        }
        result["exit_code"] = WIFEXITED(wait_status) ? WEXITSTATUS(wait_status) : -1;
    }
    result["backend"] = "usrp";
    result["data_plane"] = "soapy_iq_spectrum_native_audio";
    if (!standard_error.empty()) result["stderr"] = standard_error;
    result["probe_pid"] = child;

    std::lock_guard<std::mutex> lock(mutex_);
    last_result_ = result.dump();
    return last_result_;
}

std::string UsrpProbeRunner::status() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return last_result_;
}

}  // namespace rf_agent

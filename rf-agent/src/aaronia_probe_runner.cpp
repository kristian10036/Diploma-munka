#include "rf_agent/aaronia_probe_runner.hpp"

#include <nlohmann/json.hpp>

#include <cerrno>
#include <csignal>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include <array>
#include <algorithm>
#include <chrono>
#include <cstring>
#include <thread>
#include <utility>

namespace rf_agent {
namespace {

using Json = nlohmann::json;
constexpr std::size_t kMaxCapturedBytes = 8 * 1024;

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

std::string signal_result(int signal) {
    if (signal == SIGILL) return "illegal_instruction";
    if (signal == SIGSEGV) return "library_sigsegv";
    if (signal == SIGABRT) return "initialization_failed";
    return "unknown_failure";
}

Json base_failure(const std::string& result, const std::string& message) {
    return Json{{"backend", "aaronia"}, {"probe_attempted", true}, {"available", false},
                {"probe_result", result}, {"diagnostic", message}};
}

}  // namespace

AaroniaProbeRunner::AaroniaProbeRunner(AaroniaProbeConfig config)
    : config_(std::move(config)),
      last_result_(Json{{"backend", "aaronia"}, {"enabled", config_.enabled},
                        {"probe_attempted", false}, {"available", false},
                        {"probe_result", config_.enabled ? "not_probed" : "disabled"}}.dump()) {}

std::string AaroniaProbeRunner::run() {
    if (!config_.enabled) return status();

    int stdout_pipe[2]{};
    int stderr_pipe[2]{};
    if (pipe(stdout_pipe) != 0 || pipe(stderr_pipe) != 0) {
        const auto result = base_failure("unknown_failure", std::strerror(errno)).dump();
        std::lock_guard<std::mutex> lock(mutex_);
        return last_result_ = result;
    }

    const pid_t child = fork();
    if (child < 0) {
        close(stdout_pipe[0]); close(stdout_pipe[1]);
        close(stderr_pipe[0]); close(stderr_pipe[1]);
        const auto result = base_failure("unknown_failure", std::strerror(errno)).dump();
        std::lock_guard<std::mutex> lock(mutex_);
        return last_result_ = result;
    }
    if (child == 0) {
        dup2(stdout_pipe[1], STDOUT_FILENO);
        dup2(stderr_pipe[1], STDERR_FILENO);
        close(stdout_pipe[0]); close(stdout_pipe[1]);
        close(stderr_pipe[0]); close(stderr_pipe[1]);
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
        result = base_failure("probe_timeout", "Aaronia probe exceeded its timeout");
    } else if (WIFSIGNALED(wait_status)) {
        const int signal = WTERMSIG(wait_status);
        result = base_failure(signal_result(signal), "Aaronia probe terminated by signal");
        result["signal"] = signal;
    } else {
        try {
            result = Json::parse(standard_output);
        } catch (const Json::exception&) {
            result = base_failure("unknown_failure", "Aaronia probe returned invalid JSON");
            if (!standard_output.empty()) result["stdout"] = standard_output;
        }
        result["exit_code"] = WIFEXITED(wait_status) ? WEXITSTATUS(wait_status) : -1;
    }
    if (!standard_error.empty() && !result.value("available", false)) result["stderr"] = standard_error;
    result["probe_pid"] = child;

    std::lock_guard<std::mutex> lock(mutex_);
    last_result_ = result.dump();
    return last_result_;
}

std::string AaroniaProbeRunner::status() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return last_result_;
}

}  // namespace rf_agent

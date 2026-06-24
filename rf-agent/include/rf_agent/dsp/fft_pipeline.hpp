#pragma once

#include <chrono>
#include <complex>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <vector>

namespace rf_agent::dsp {

enum class WindowType { Hann, BlackmanHarris, Rectangular };

class WindowFunction {
public:
    [[nodiscard]] static std::vector<double> coefficients(WindowType type, std::size_t size);
};

class DcBlocker {
public:
    static void process(std::vector<std::complex<float>>& samples);
};

class FftProcessor {
public:
    FftProcessor(std::size_t fft_size, WindowType window);
    [[nodiscard]] std::vector<double> process(const std::vector<std::complex<float>>& samples) const;
    [[nodiscard]] std::size_t size() const noexcept { return fft_size_; }

private:
    std::size_t fft_size_;
    std::vector<double> window_;
    double coherent_gain_;
};

class SpectrumAverager {
public:
    explicit SpectrumAverager(std::size_t depth);
    [[nodiscard]] std::vector<double> process(const std::vector<double>& spectrum);
    void reset();

private:
    std::size_t depth_;
    std::vector<std::vector<double>> history_;
};

class MaxHoldProcessor {
public:
    [[nodiscard]] std::vector<double> process(const std::vector<double>& spectrum);
    void reset();

private:
    std::vector<double> maximum_;
};

struct Peak {
    std::size_t bin;
    double power_dbfs;
};

class PeakDetector {
public:
    explicit PeakDetector(double threshold_db);
    [[nodiscard]] std::vector<Peak> detect(const std::vector<double>& spectrum) const;

private:
    double threshold_db_;
};

class FrameRateLimiter {
public:
    explicit FrameRateLimiter(double max_fps);
    [[nodiscard]] bool allow(std::chrono::steady_clock::time_point now);
    [[nodiscard]] std::uint64_t droppedFrames() const noexcept { return dropped_frames_; }

private:
    std::chrono::duration<double> interval_;
    std::optional<std::chrono::steady_clock::time_point> next_allowed_;
    std::uint64_t dropped_frames_{0};
};

class CalibrationProcessor {
public:
    explicit CalibrationProcessor(double offset_db) : offset_db_(offset_db) {}
    void process(std::vector<double>& spectrum) const;

private:
    double offset_db_;
};

}  // namespace rf_agent::dsp

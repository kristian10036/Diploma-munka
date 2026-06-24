#include "rf_agent/dsp/fft_pipeline.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>

namespace rf_agent::dsp {
namespace {

constexpr double kPi = 3.14159265358979323846;

bool power_of_two(std::size_t value) { return value > 1 && (value & (value - 1)) == 0; }

void fft(std::vector<std::complex<double>>& values) {
    const std::size_t size = values.size();
    for (std::size_t i = 1, j = 0; i < size; ++i) {
        std::size_t bit = size >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) std::swap(values[i], values[j]);
    }
    for (std::size_t length = 2; length <= size; length <<= 1) {
        const std::complex<double> root = std::polar(1.0, -2.0 * kPi / length);
        for (std::size_t offset = 0; offset < size; offset += length) {
            std::complex<double> factor{1.0, 0.0};
            for (std::size_t index = 0; index < length / 2; ++index) {
                const auto even = values[offset + index];
                const auto odd = values[offset + index + length / 2] * factor;
                values[offset + index] = even + odd;
                values[offset + index + length / 2] = even - odd;
                factor *= root;
            }
        }
    }
}

void require_finite(const std::vector<double>& values) {
    if (std::any_of(values.begin(), values.end(), [](double value) { return !std::isfinite(value); })) {
        throw std::invalid_argument("spectrum contains NaN or Infinity");
    }
}

}  // namespace

std::vector<double> WindowFunction::coefficients(WindowType type, std::size_t size) {
    if (size < 2) throw std::invalid_argument("window size must be at least two");
    std::vector<double> result(size, 1.0);
    for (std::size_t index = 0; index < size; ++index) {
        const double phase = 2.0 * kPi * index / static_cast<double>(size - 1);
        if (type == WindowType::Hann) result[index] = 0.5 - 0.5 * std::cos(phase);
        if (type == WindowType::BlackmanHarris) {
            result[index] = 0.35875 - 0.48829 * std::cos(phase) +
                            0.14128 * std::cos(2.0 * phase) - 0.01168 * std::cos(3.0 * phase);
        }
    }
    return result;
}

void DcBlocker::process(std::vector<std::complex<float>>& samples) {
    if (samples.empty()) return;
    std::complex<double> mean{0.0, 0.0};
    for (const auto sample : samples) {
        if (!std::isfinite(sample.real()) || !std::isfinite(sample.imag())) {
            throw std::invalid_argument("IQ samples contain NaN or Infinity");
        }
        mean += std::complex<double>{sample.real(), sample.imag()};
    }
    mean /= static_cast<double>(samples.size());
    for (auto& sample : samples) sample -= std::complex<float>{static_cast<float>(mean.real()),
                                                               static_cast<float>(mean.imag())};
}

FftProcessor::FftProcessor(std::size_t fft_size, WindowType window)
    : fft_size_(fft_size), window_(WindowFunction::coefficients(window, fft_size)),
      coherent_gain_(std::accumulate(window_.begin(), window_.end(), 0.0) / fft_size) {
    if (!power_of_two(fft_size_)) throw std::invalid_argument("FFT size must be a power of two");
}

std::vector<double> FftProcessor::process(
    const std::vector<std::complex<float>>& samples) const {
    if (samples.size() != fft_size_) throw std::invalid_argument("IQ sample count must equal FFT size");
    auto centered = samples;
    DcBlocker::process(centered);
    std::vector<std::complex<double>> bins(fft_size_);
    for (std::size_t index = 0; index < fft_size_; ++index) {
        bins[index] = std::complex<double>{centered[index].real(), centered[index].imag()} *
                      window_[index];
    }
    fft(bins);
    std::rotate(bins.begin(), bins.begin() + fft_size_ / 2, bins.end());
    std::vector<double> dbfs(fft_size_);
    const double scale = static_cast<double>(fft_size_) * coherent_gain_;
    for (std::size_t index = 0; index < fft_size_; ++index) {
        dbfs[index] = 20.0 * std::log10(std::max(std::abs(bins[index]) / scale, 1e-12));
    }
    return dbfs;
}

SpectrumAverager::SpectrumAverager(std::size_t depth) : depth_(depth) {
    if (depth_ == 0) throw std::invalid_argument("averaging depth must be positive");
}

std::vector<double> SpectrumAverager::process(const std::vector<double>& spectrum) {
    if (spectrum.empty()) throw std::invalid_argument("spectrum must not be empty");
    require_finite(spectrum);
    if (!history_.empty() && history_.front().size() != spectrum.size()) reset();
    history_.push_back(spectrum);
    if (history_.size() > depth_) history_.erase(history_.begin());
    std::vector<double> result(spectrum.size(), 0.0);
    for (const auto& frame : history_) {
        for (std::size_t index = 0; index < frame.size(); ++index) result[index] += frame[index];
    }
    for (auto& value : result) value /= history_.size();
    return result;
}

void SpectrumAverager::reset() { history_.clear(); }

std::vector<double> MaxHoldProcessor::process(const std::vector<double>& spectrum) {
    require_finite(spectrum);
    if (maximum_.size() != spectrum.size()) maximum_ = spectrum;
    else for (std::size_t i = 0; i < spectrum.size(); ++i) maximum_[i] = std::max(maximum_[i], spectrum[i]);
    return maximum_;
}

void MaxHoldProcessor::reset() { maximum_.clear(); }

PeakDetector::PeakDetector(double threshold_db) : threshold_db_(threshold_db) {
    if (!std::isfinite(threshold_db_) || threshold_db_ < 0.0) {
        throw std::invalid_argument("peak threshold must be finite and non-negative");
    }
}

std::vector<Peak> PeakDetector::detect(const std::vector<double>& spectrum) const {
    if (spectrum.size() < 3) return {};
    require_finite(spectrum);
    auto sorted = spectrum;
    std::nth_element(sorted.begin(), sorted.begin() + sorted.size() / 2, sorted.end());
    const double floor = sorted[sorted.size() / 2];
    std::vector<Peak> peaks;
    for (std::size_t index = 1; index + 1 < spectrum.size(); ++index) {
        if (spectrum[index] >= floor + threshold_db_ && spectrum[index] > spectrum[index - 1] &&
            spectrum[index] >= spectrum[index + 1]) peaks.push_back({index, spectrum[index]});
    }
    return peaks;
}

FrameRateLimiter::FrameRateLimiter(double max_fps) : interval_(1.0 / max_fps) {
    if (!std::isfinite(max_fps) || max_fps <= 0.0) throw std::invalid_argument("max FPS must be positive");
}

bool FrameRateLimiter::allow(std::chrono::steady_clock::time_point now) {
    if (!next_allowed_ || now >= *next_allowed_) {
        next_allowed_ = now + std::chrono::duration_cast<std::chrono::steady_clock::duration>(interval_);
        return true;
    }
    ++dropped_frames_;
    return false;
}

void CalibrationProcessor::process(std::vector<double>& spectrum) const {
    if (!std::isfinite(offset_db_)) throw std::invalid_argument("calibration offset must be finite");
    require_finite(spectrum);
    for (auto& value : spectrum) value += offset_db_;
}

}  // namespace rf_agent::dsp

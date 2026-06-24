#include "rf_agent/dsp/fft_pipeline.hpp"

#include <cassert>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <complex>
#include <iostream>
#include <limits>
#include <random>
#include <stdexcept>
#include <vector>

namespace {

constexpr double kPi = 3.14159265358979323846;

std::vector<std::complex<float>> tone(std::size_t size, int bin, double amplitude = 1.0) {
    std::vector<std::complex<float>> samples(size);
    for (std::size_t index = 0; index < size; ++index) {
        const double phase = 2.0 * kPi * bin * index / static_cast<double>(size);
        samples[index] = static_cast<float>(amplitude) *
                         std::complex<float>{static_cast<float>(std::cos(phase)),
                                             static_cast<float>(std::sin(phase))};
    }
    return samples;
}

std::size_t maximum_bin(const std::vector<double>& values) {
    return static_cast<std::size_t>(std::max_element(values.begin(), values.end()) - values.begin());
}

}  // namespace

int main() {
    using namespace rf_agent::dsp;
    constexpr std::size_t size = 1024;

    const auto hann = WindowFunction::coefficients(WindowType::Hann, size);
    assert(std::abs(hann.front()) < 1e-12 && std::abs(hann.back()) < 1e-12);
    assert(hann[size / 2] > 0.99);
    const auto blackman = WindowFunction::coefficients(WindowType::BlackmanHarris, size);
    assert(blackman.front() < 0.001);

    FftProcessor processor(size, WindowType::Hann);
    auto spectrum = processor.process(tone(size, 73, 0.5));
    assert(maximum_bin(spectrum) == size / 2 + 73);
    assert(std::abs(spectrum[maximum_bin(spectrum)] + 6.0206) < 0.1);

    auto two_tones = tone(size, 40, 0.8);
    const auto second = tone(size, -91, 0.4);
    for (std::size_t index = 0; index < size; ++index) two_tones[index] += second[index];
    spectrum = processor.process(two_tones);
    PeakDetector detector(20.0);
    const auto peaks = detector.detect(spectrum);
    bool first_found = false, second_found = false;
    for (const auto& peak : peaks) {
        first_found |= peak.bin == size / 2 + 40;
        second_found |= peak.bin == size / 2 - 91;
    }
    assert(first_found && second_found);

    std::vector<std::complex<float>> dc(size, {0.75F, -0.25F});
    spectrum = processor.process(dc);
    assert(*std::max_element(spectrum.begin(), spectrum.end()) <= -239.0);

    std::mt19937 random(42);
    std::normal_distribution<float> noise(0.0F, 0.02F);
    std::vector<std::complex<float>> noise_samples(size);
    for (auto& sample : noise_samples) sample = {noise(random), noise(random)};
    spectrum = processor.process(noise_samples);
    assert(std::all_of(spectrum.begin(), spectrum.end(), [](double value) { return std::isfinite(value); }));

    SpectrumAverager averager(2);
    assert(averager.process({-10.0, -20.0}) == std::vector<double>({-10.0, -20.0}));
    assert(averager.process({-20.0, -10.0}) == std::vector<double>({-15.0, -15.0}));
    MaxHoldProcessor max_hold;
    (void)max_hold.process({-10.0, -30.0});
    assert(max_hold.process({-20.0, -15.0}) == std::vector<double>({-10.0, -15.0}));
    CalibrationProcessor calibration(3.5);
    std::vector<double> calibrated{-10.0};
    calibration.process(calibrated);
    assert(calibrated[0] == -6.5);

    FrameRateLimiter limiter(5.0);
    const auto now = std::chrono::steady_clock::now();
    assert(limiter.allow(now));
    assert(!limiter.allow(now + std::chrono::milliseconds(100)));
    assert(limiter.allow(now + std::chrono::milliseconds(200)));
    assert(limiter.droppedFrames() == 1);

    auto invalid = tone(size, 10);
    invalid[0] = {std::numeric_limits<float>::quiet_NaN(), 0.0F};
    bool rejected = false;
    try { (void)processor.process(invalid); } catch (const std::invalid_argument&) { rejected = true; }
    assert(rejected);

    std::cout << "FFT pipeline tests: OK\n";
    return 0;
}

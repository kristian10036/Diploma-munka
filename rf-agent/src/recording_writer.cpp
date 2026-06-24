#include "rf_agent/recording_writer.hpp"
#include "rf_agent/frame_json.hpp"
#include <nlohmann/json.hpp>
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <zstd.h>
#include <array>
#include <chrono>
#include <cctype>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <system_error>
#include <vector>

namespace rf_agent {
namespace {
using Json = nlohmann::json;
std::string utc_now() {
    const auto now = std::chrono::system_clock::now();
    const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;
    const std::time_t time = std::chrono::system_clock::to_time_t(now); std::tm value{}; gmtime_r(&time, &value);
    std::ostringstream out; out << std::put_time(&value, "%Y-%m-%dT%H:%M:%S") << '.'
        << std::setfill('0') << std::setw(3) << ms.count() << 'Z'; return out.str();
}
std::string generated_id() {
    std::array<unsigned char, 16> bytes{}; if (RAND_bytes(bytes.data(), bytes.size()) != 1) return {};
    bytes[6] = static_cast<unsigned char>((bytes[6] & 0x0fU) | 0x40U);
    bytes[8] = static_cast<unsigned char>((bytes[8] & 0x3fU) | 0x80U);
    std::ostringstream out; out << std::hex << std::setfill('0');
    for (std::size_t i = 0; i < bytes.size(); ++i) { if (i == 4 || i == 6 || i == 8 || i == 10) out << '-'; out << std::setw(2) << static_cast<unsigned int>(bytes[i]); }
    return out.str();
}
bool safe_id(const std::string& value) {
    if (value.empty() || value.size() > 128 || value.front() == '.') return false;
    for (unsigned char c : value) {
        if (!std::isalnum(c) && c != '-' && c != '_') return false;
    }
    return true;
}
std::string sha256_file(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary); if (!input) return {};
    EVP_MD_CTX* context = EVP_MD_CTX_new(); if (!context) return {};
    std::array<unsigned char, EVP_MAX_MD_SIZE> digest{}; unsigned int digest_size = 0;
    std::array<char, 64 * 1024> buffer{}; bool ok = EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1;
    while (ok && input) { input.read(buffer.data(), static_cast<std::streamsize>(buffer.size())); if (input.gcount() > 0) ok = EVP_DigestUpdate(context, buffer.data(), static_cast<std::size_t>(input.gcount())) == 1; }
    ok = ok && EVP_DigestFinal_ex(context, digest.data(), &digest_size) == 1; EVP_MD_CTX_free(context); if (!ok) return {};
    std::ostringstream out; out << std::hex << std::setfill('0'); for (unsigned int i = 0; i < digest_size; ++i) out << std::setw(2) << static_cast<unsigned int>(digest[i]); return out.str();
}
bool atomic_write(const std::filesystem::path& path, const std::string& content) {
    const std::filesystem::path temporary = path.string() + ".tmp"; std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    if (!output) return false;
    output << content;
    output.close();
    if (!output) return false;
    std::error_code error; std::filesystem::rename(temporary, path, error); return !error;
}
}  // namespace

struct SpectrumRecordingWriter::Implementation {
    explicit Implementation(std::filesystem::path value) : root(std::move(value)) {}
    std::filesystem::path root, staging, final_directory; std::ofstream output; ZSTD_CStream* stream{nullptr};
    std::string recording_id, description, started_at, ended_at, sensor_id, source_type, source_device, session_id;
    std::string first_timestamp, last_timestamp, checksum_sha256, error; std::uint64_t start_frequency_hz{0}, stop_frequency_hz{0};
    std::size_t num_points{0}, frame_count{0}; bool is_active{false};
    void reset_stream() { if (stream) ZSTD_freeCStream(stream); stream = nullptr; if (output.is_open()) output.close(); }
    bool write_chunk(const std::string& data, ZSTD_EndDirective directive) {
        ZSTD_inBuffer input{data.data(), data.size(), 0}; std::vector<char> buffer(ZSTD_CStreamOutSize()); std::size_t remaining = 1;
        do { ZSTD_outBuffer destination{buffer.data(), buffer.size(), 0}; remaining = ZSTD_compressStream2(stream, &destination, &input, directive);
            if (ZSTD_isError(remaining)) { error = ZSTD_getErrorName(remaining); return false; }
            output.write(buffer.data(), static_cast<std::streamsize>(destination.pos)); if (!output) { error = "Cannot write recording frame data"; return false; }
        } while (input.pos < input.size || (directive == ZSTD_e_end && remaining != 0)); return true;
    }
    Json metadata() const {
        Json value{{"schema_version",1},{"recording_id",recording_id},{"session_id",session_id},{"sensor_id",sensor_id},{"source_type",source_type},{"source_device",source_device},
            {"started_at",started_at},{"ended_at",ended_at},{"first_frame_timestamp",first_timestamp},{"last_frame_timestamp",last_timestamp},{"frame_count",frame_count},
            {"start_frequency_hz",start_frequency_hz},{"stop_frequency_hz",stop_frequency_hz},{"num_points",num_points},{"frame_file","frames.ndjson.zst"},{"compression","zstd"},{"checksum_algorithm","sha256"},
            {"checksum_sha256",checksum_sha256},{"status",ended_at.empty() ? "recording" : "completed"}};
        if (!description.empty()) value["description"] = description;
        return value;
    }
};

SpectrumRecordingWriter::SpectrumRecordingWriter(std::filesystem::path root) : implementation_(std::make_unique<Implementation>(std::move(root))) {}
SpectrumRecordingWriter::~SpectrumRecordingWriter() { if (implementation_) implementation_->reset_stream(); }
bool SpectrumRecordingWriter::start(const RecordingStartOptions& options) {
    auto& s = *implementation_; if (s.is_active) { s.error = "A recording is already active"; return false; }
    s.recording_id = options.recording_id.empty() ? generated_id() : options.recording_id; if (!safe_id(s.recording_id)) { s.error = "Invalid recording_id"; return false; }
    s.description = options.description; s.staging = s.root / ("." + s.recording_id + ".tmp"); s.final_directory = s.root / s.recording_id; std::error_code error;
    std::filesystem::create_directories(s.root, error);
    if (error || std::filesystem::exists(s.staging) || std::filesystem::exists(s.final_directory) || !std::filesystem::create_directory(s.staging, error)) { s.error = "Recording directory cannot be created"; return false; }
    s.output.open(s.staging / "frames.ndjson.zst", std::ios::binary | std::ios::trunc); s.stream = ZSTD_createCStream();
    if (!s.output || !s.stream || ZSTD_isError(ZSTD_initCStream(s.stream, 3))) { s.error = "Zstandard writer cannot be initialized"; s.reset_stream(); std::filesystem::remove_all(s.staging, error); return false; }
    s.started_at=utc_now(); s.ended_at.clear(); s.sensor_id.clear(); s.source_type.clear(); s.source_device.clear(); s.session_id.clear(); s.first_timestamp.clear(); s.last_timestamp.clear(); s.checksum_sha256.clear();
    s.frame_count=0; s.start_frequency_hz=0; s.stop_frequency_hz=0; s.num_points=0; s.error.clear(); s.is_active=true; return true;
}
bool SpectrumRecordingWriter::append(const SpectrumFrame& frame) {
    auto& s=*implementation_; if (!s.is_active) return false; if (!validate_spectrum_frame(frame).valid()) { s.error="Invalid SpectrumFrame rejected by recording writer"; return false; }
    if (!s.write_chunk(spectrum_frame_json(frame)+"\n", ZSTD_e_continue)) return false;
    if (s.frame_count==0) { s.sensor_id=frame.sensor_id; s.source_type=to_string(frame.source_type); s.source_device=frame.source_device; s.session_id=frame.session_id; s.first_timestamp=frame.timestamp; s.start_frequency_hz=frame.start_frequency_hz; s.stop_frequency_hz=frame.stop_frequency_hz; s.num_points=frame.num_points; }
    s.last_timestamp=frame.timestamp; ++s.frame_count; return true;
}
std::optional<std::string> SpectrumRecordingWriter::stop() {
    auto& s=*implementation_; if (!s.is_active) { s.error="No recording is active"; return std::nullopt; } s.is_active=false;
    if (s.frame_count==0) { s.error="Recording contains no frames"; s.reset_stream(); std::error_code e; std::filesystem::remove_all(s.staging,e); return std::nullopt; }
    if (!s.write_chunk({}, ZSTD_e_end)) { s.reset_stream(); return std::nullopt; } s.reset_stream(); s.ended_at=utc_now(); const auto frame_path=s.staging/"frames.ndjson.zst"; const std::string checksum=sha256_file(frame_path); s.checksum_sha256 = checksum;
    if (checksum.empty() || !atomic_write(s.staging/"checksum.sha256",checksum+"  frames.ndjson.zst\n") || !atomic_write(s.staging/"metadata.json",s.metadata().dump(2)+"\n")) { s.error="Recording metadata or checksum cannot be finalized"; return std::nullopt; }
    std::error_code error; std::filesystem::rename(s.staging,s.final_directory,error); if (error) { s.error="Recording directory cannot be published atomically"; return std::nullopt; } s.error.clear(); return s.metadata().dump();
}
bool SpectrumRecordingWriter::active() const { return implementation_->is_active; }
std::string SpectrumRecordingWriter::statusJson() const { const auto& s=*implementation_; return Json{{"active",s.is_active},{"recording_id",s.recording_id},{"frame_count",s.frame_count},{"started_at",s.started_at},{"last_error",s.error}}.dump(); }
const std::string& SpectrumRecordingWriter::lastError() const { return implementation_->error; }
}  // namespace rf_agent

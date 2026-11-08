#include "download.h"
#include "util.h"
#include <archive.h>
#include <archive_entry.h>
#include <curl/curl.h>
#include <openssl/evp.h>
#include <nlohmann/json.hpp>
#include <array>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <thread>
#include <unistd.h>

namespace fs = std::filesystem;
namespace downloads {
void Job::check() const { if (cancelled) throw std::runtime_error("Cancelled"); }
void Job::report(const std::string& phase, uint64_t done, uint64_t total) const {
    check();
    if (progress) progress(phase, done, total);
}
namespace {
struct Transfer {
    Job& job;
    explicit Transfer(Job& j) : job(j) {}
    std::string text;
    FILE* file = nullptr;
    uint64_t limit = 32ULL * 1024 * 1024;
    uint64_t received = 0;
    bool too_large = false;
    uint64_t offset = 0;
    long status = 0;
    std::string etag, modified, range, failure;
    bool prepared = false;
    unsigned retry_after = 0;
    uint64_t content_length = 0;
    std::string destination;
    std::function<void()> checkpoint;
    std::string validator;
    bool restart = false;
    uint64_t range_total = 0;
};
bool prepare_body(Transfer& t) {
    if (t.prepared || !t.file) return true;
    if (t.status == 206) {
        unsigned long long first = 0, last = 0, total = 0;
        if (sscanf(t.range.c_str(), "bytes %llu-%llu/%llu", &first, &last, &total) != 3 ||
            first != t.offset || last < first || total <= last ||
            (t.content_length && t.content_length != last - first + 1)) {
            t.failure = "Server returned an invalid download range"; return false;
        }
        const auto response_validator = !t.etag.empty() && !t.etag.starts_with("W/") ? t.etag : t.modified;
        if (!response_validator.empty() && !t.validator.empty() && response_validator != t.validator) {
            t.restart = true; return false;
        }
        t.range_total = total;
    } else if (t.status == 200) {
        // A server may ignore Range, or If-Range may detect a replaced asset.
        // Discard the old prefix before accepting the full replacement body.
        if (t.offset && (ftruncate(fileno(t.file), 0) || fseek(t.file, 0, SEEK_SET))) {
            t.failure = "Cannot restart the partial download"; return false;
        }
        t.offset = 0;
    } else { t.failure = "Unexpected download response"; return false; }
    t.received = t.offset;
    try { require_space(t.destination, t.content_length); }
    catch (const std::exception& error) { t.failure = error.what(); return false; }
    t.prepared = true;
    try { if (t.checkpoint) t.checkpoint(); }
    catch (const std::exception& error) { t.failure = error.what(); return false; }
    return true;
}
size_t header(char* data, size_t size, size_t count, void* ptr) {
    auto& t = *static_cast<Transfer*>(ptr);
    const size_t bytes = size * count;
    try {
        std::string line(data, bytes);
        if (line.starts_with("HTTP/")) {
            const auto space = line.find(' ');
            t.status = space == std::string::npos ? 0 : std::stol(line.substr(space + 1));
            t.etag.clear(); t.modified.clear(); t.range.clear(); t.retry_after = 0; t.content_length = 0;
        } else {
            const auto colon = line.find(':');
            if (colon != std::string::npos) {
                const auto key = util::lower(line.substr(0, colon)), value = util::trim(line.substr(colon + 1));
                if (key == "etag") t.etag = value;
                if (key == "last-modified") t.modified = value;
                if (key == "content-range") t.range = value;
                if (key == "content-length") t.content_length = std::stoull(value);
                if (key == "retry-after" && !value.empty() && value.find_first_not_of("0123456789") == std::string::npos)
                    t.retry_after = static_cast<unsigned>(std::min(30UL, std::stoul(value)));
            }
        }
    } catch (...) { return 0; }
    return bytes;
}
size_t receive(char* data, size_t size, size_t count, void* ptr) {
    auto& t = *static_cast<Transfer*>(ptr);
    const size_t bytes = size * count;
    if (t.job.cancelled) return 0;
    if (t.status >= 300 && t.status < 400) return bytes; // redirect body is not an archive
    if (!prepare_body(t)) return 0;
    if (bytes > t.limit - t.received) { t.too_large = true; return 0; }
    t.received += bytes;
    if (t.file) return fwrite(data, 1, bytes, t.file);
    try { t.text.append(data, bytes); } catch (...) { return 0; }
    return bytes;
}
int progress(void* ptr, curl_off_t total, curl_off_t done, curl_off_t, curl_off_t) {
    auto& t = *static_cast<Transfer*>(ptr);
    try { t.job.report(t.file ? (t.offset ? "Resuming download" : "Downloading") : "Loading releases",
        t.offset + (done > 0 ? done : 0), total > 0 ? t.offset + total : 0); }
    catch (...) { return 1; }
    return 0;
}
struct RequestError : std::runtime_error {
    bool retryable; unsigned delay;
    RequestError(const std::string& message, bool retry, unsigned seconds)
        : std::runtime_error(message), retryable(retry), delay(seconds) {}
};
void retry_wait(Job& job, unsigned seconds, int attempt) {
    job.report("Connection interrupted; retry " + std::to_string(attempt) + " of 3");
    for (unsigned n = 0; n < seconds * 20; ++n) {
        job.check(); std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
}
void request(const std::string& url, Transfer& t, const std::string& validator = {}) {
    if (!url.starts_with("https://")) throw std::runtime_error("Downloads require an HTTPS URL");
    static const int initialized = [] { return curl_global_init(CURL_GLOBAL_DEFAULT); }();
    if (initialized != CURLE_OK) throw std::runtime_error("Cannot initialize HTTPS support");
    std::unique_ptr<CURL, decltype(&curl_easy_cleanup)> curl(curl_easy_init(), curl_easy_cleanup);
    if (!curl) throw std::runtime_error("Cannot create HTTPS request");
    std::array<char, CURL_ERROR_SIZE> error{};
    curl_easy_setopt(curl.get(), CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl.get(), CURLOPT_USERAGENT, "XetalProton/1.0");
    curl_easy_setopt(curl.get(), CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl.get(), CURLOPT_MAXREDIRS, 8L);
    curl_easy_setopt(curl.get(), CURLOPT_PROTOCOLS_STR, "https");
    curl_easy_setopt(curl.get(), CURLOPT_REDIR_PROTOCOLS_STR, "https");
    curl_easy_setopt(curl.get(), CURLOPT_FAILONERROR, 1L);
    curl_easy_setopt(curl.get(), CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(curl.get(), CURLOPT_CONNECTTIMEOUT, 20L);
    curl_easy_setopt(curl.get(), CURLOPT_LOW_SPEED_LIMIT, 128L);
    curl_easy_setopt(curl.get(), CURLOPT_LOW_SPEED_TIME, 60L);
    if (!t.file) curl_easy_setopt(curl.get(), CURLOPT_TIMEOUT, 45L);
    curl_easy_setopt(curl.get(), CURLOPT_WRITEFUNCTION, receive);
    curl_easy_setopt(curl.get(), CURLOPT_WRITEDATA, &t);
    curl_easy_setopt(curl.get(), CURLOPT_XFERINFOFUNCTION, progress);
    curl_easy_setopt(curl.get(), CURLOPT_XFERINFODATA, &t);
    curl_easy_setopt(curl.get(), CURLOPT_NOPROGRESS, 0L);
    curl_easy_setopt(curl.get(), CURLOPT_ERRORBUFFER, error.data());
    curl_easy_setopt(curl.get(), CURLOPT_HEADERFUNCTION, header);
    curl_easy_setopt(curl.get(), CURLOPT_HEADERDATA, &t);
    if (!t.job.ca_bundle.empty()) curl_easy_setopt(curl.get(), CURLOPT_CAINFO, t.job.ca_bundle.c_str());
    const auto range = std::to_string(t.offset) + "-";
    if (t.offset) curl_easy_setopt(curl.get(), CURLOPT_RANGE, range.c_str());
    const auto if_range = "If-Range: " + validator;
    std::unique_ptr<curl_slist, decltype(&curl_slist_free_all)> headers(
        t.offset && !validator.empty() ? curl_slist_append(nullptr, if_range.c_str()) : nullptr, curl_slist_free_all);
    if (headers) curl_easy_setopt(curl.get(), CURLOPT_HTTPHEADER, headers.get());
    t.job.check();
    const auto result = curl_easy_perform(curl.get());
    t.job.check();
    long status = 0;
    curl_easy_getinfo(curl.get(), CURLINFO_RESPONSE_CODE, &status);
    if (!t.failure.empty()) throw std::runtime_error(t.failure);
    if (t.restart) throw RequestError("The download changed upstream; restarting", true, 0);
    if (t.too_large) throw std::runtime_error("Download exceeds the expected size limit");
    if (result != CURLE_OK) {
        const bool retry = status == 408 || status == 429 || status == 500 || status == 502 || status == 503 || status == 504 ||
            result == CURLE_COULDNT_RESOLVE_HOST || result == CURLE_COULDNT_CONNECT || result == CURLE_OPERATION_TIMEDOUT ||
            result == CURLE_RECV_ERROR || result == CURLE_SEND_ERROR || result == CURLE_PARTIAL_FILE ||
            result == CURLE_HTTP2 || result == CURLE_HTTP2_STREAM || result == CURLE_GOT_NOTHING;
        const auto message = status == 403 || status == 429 ?
            "Upstream API rate limit or access restriction. Try again later." :
            "Download failed: " + std::string(error[0] ? error.data() : curl_easy_strerror(result));
        throw RequestError(message, retry, t.retry_after);
    }
}
std::string hex(const unsigned char* bytes, unsigned int size) {
    std::string out;
    for (unsigned int i = 0; i < size; ++i) { out += "0123456789abcdef"[bytes[i] >> 4]; out += "0123456789abcdef"[bytes[i] & 15]; }
    return out;
}
const EVP_MD* algorithm_for(const std::string& algorithm) {
    if (algorithm == "sha256") return EVP_sha256();
    if (algorithm == "sha512") return EVP_sha512();
    throw std::runtime_error("Unsupported checksum algorithm: " + algorithm);
}
fs::path safe_relative(const fs::path& path) {
    if (path.empty() || path.is_absolute()) throw std::runtime_error("Archive contains an absolute or empty path");
    auto normalized = path.lexically_normal();
    for (const auto& component : normalized)
        if (component == "..") throw std::runtime_error("Archive contains a path outside its installation");
    return normalized;
}
void require_archive(int result, struct archive* a) {
    if (result < ARCHIVE_OK) throw std::runtime_error(std::string("Archive error: ") + (archive_error_string(a) ? archive_error_string(a) : "invalid data"));
}
}

std::string get(const std::string& url, Job& job) {
    for (int attempt = 1;; ++attempt) {
        Transfer transfer{job};
        try { request(url, transfer); return transfer.text; }
        catch (const RequestError& error) {
            if (!error.retryable || attempt == 3) throw;
            retry_wait(job, std::max(unsigned(attempt), error.delay), attempt + 1);
        }
    }
}
void require_space(const std::string& path, uint64_t bytes) {
    constexpr uint64_t reserve = 64ULL * 1024 * 1024;
    std::error_code ec;
    auto target = fs::absolute(path);
    while (!fs::exists(target, ec) && target.has_parent_path() && target != target.parent_path()) target = target.parent_path();
    const auto space = fs::space(target, ec);
    if (ec) throw std::runtime_error("Cannot check free disk space: " + ec.message());
    if (space.available < reserve || bytes > space.available - reserve)
        throw std::runtime_error("Not enough disk space: need " + util::human_size(bytes) + " plus 64 MiB reserve; " +
            util::human_size(space.available) + " available in " + target.string());
}
void fetch(const std::string& url, const std::string& destination, uint64_t expected_size, Job& job) {
    using json = nlohmann::json;
    job.check();
    const auto metadata_path = destination + ".json";
    json metadata = json::object();
    std::string text;
    try { if (util::read_file(metadata_path, text)) metadata = json::parse(text); } catch (...) {}
    bool reusable = metadata.is_object() && metadata.value("url", std::string()) == url &&
        metadata.value("size", uint64_t(0)) == expected_size && fs::is_regular_file(destination);
    uint64_t offset = reusable ? fs::file_size(destination) : 0;
    if (expected_size && offset > expected_size) reusable = false;
    if (reusable && metadata.value("complete", false) && (!expected_size || offset == expected_size)) {
        job.report("Using saved download", offset, offset); return;
    }
    // Never join different revisions of a mutable URL without a validator.
    std::string validator = reusable ? metadata.value("validator", std::string()) : "";
    if (validator.empty()) reusable = false;
    const auto close_file = [](FILE* file) { fclose(file); };
    std::unique_ptr<FILE, decltype(close_file)> file(fopen(destination.c_str(), reusable ? "r+b" : "w+b"), close_file);
    if (!file) throw std::runtime_error("Cannot write download: " + destination);
    for (int attempt = 1;; ++attempt) {
        job.check();
        if (fseek(file.get(), 0, SEEK_END)) throw std::runtime_error("Cannot seek partial download");
        offset = ftell(file.get());
        require_space(destination, expected_size > offset ? expected_size - offset : 0);
        Transfer transfer{job};
        transfer.file = file.get(); transfer.offset = offset; transfer.destination = destination; transfer.validator = validator;
        transfer.limit = expected_size ? expected_size : 8ULL * 1024 * 1024 * 1024;
        auto save = [&](bool complete) {
            // Only successful response headers can replace the cached validator.
            if (transfer.prepared) validator = !transfer.etag.empty() && !transfer.etag.starts_with("W/") ? transfer.etag : transfer.modified;
            if (fflush(file.get()) || ferror(file.get())) throw std::runtime_error("Cannot save download (check free disk space)");
            if (!util::write_file(metadata_path, json{{"url", url}, {"size", expected_size}, {"validator", validator}, {"complete", complete}}.dump()))
                throw std::runtime_error("Cannot save download recovery information");
        };
        // Commit the response validator before writing the body so recovery
        // also works after the app/process is terminated unexpectedly.
        transfer.checkpoint = [&] { save(false); };
        try {
            request(url, transfer, validator);
            if ((expected_size && static_cast<uint64_t>(ftell(file.get())) != expected_size) ||
                (transfer.range_total && static_cast<uint64_t>(ftell(file.get())) != transfer.range_total))
                throw RequestError("Download is incomplete", true, 0);
            save(true); return;
        } catch (const RequestError& error) {
            save(false);
            // An out-of-range partial may belong to an asset that changed size.
            const bool restart = transfer.status == 416 || transfer.restart;
            if ((!error.retryable && !restart) || attempt == 3) throw;
            if (restart || validator.empty()) {
                if (ftruncate(fileno(file.get()), 0) || fseek(file.get(), 0, SEEK_SET)) throw std::runtime_error("Cannot restart download");
                validator.clear();
            }
            retry_wait(job, std::max(unsigned(attempt), error.delay), attempt + 1);
        } catch (...) { save(false); throw; }
    }
}
std::string hash_file(const std::string& path, const std::string& algorithm, Job& job) {
    std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> ctx(EVP_MD_CTX_new(), EVP_MD_CTX_free);
    if (!ctx || EVP_DigestInit_ex(ctx.get(), algorithm_for(algorithm), nullptr) != 1) throw std::runtime_error("Cannot initialize checksum");
    std::ifstream file(path, std::ios::binary);
    if (!file) throw std::runtime_error("Cannot read downloaded archive");
    const auto total = fs::file_size(path);
    uint64_t done = 0;
    std::array<char, 65536> buffer{};
    while (file.read(buffer.data(), buffer.size()) || file.gcount()) {
        const auto count = file.gcount();
        if (EVP_DigestUpdate(ctx.get(), buffer.data(), count) != 1) throw std::runtime_error("Cannot calculate checksum");
        done += count;
        job.report("Verifying checksum", done, total);
    }
    if (!file.eof()) throw std::runtime_error("Cannot read complete archive for checksum");
    unsigned char digest[EVP_MAX_MD_SIZE]; unsigned int size = 0;
    if (EVP_DigestFinal_ex(ctx.get(), digest, &size) != 1) throw std::runtime_error("Cannot finalize checksum");
    return hex(digest, size);
}
std::string sha256(const std::string& text) {
    unsigned char digest[EVP_MAX_MD_SIZE]; unsigned int size = 0;
    if (EVP_Digest(text.data(), text.size(), digest, &size, EVP_sha256(), nullptr) != 1) throw std::runtime_error("Cannot calculate identifier");
    return hex(digest, size);
}
void verify(const std::string& path, const std::string& digest, Job& job) {
    const auto sep = digest.find(':');
    if (sep == std::string::npos) throw std::runtime_error("Invalid upstream checksum");
    const auto expected = util::lower(digest.substr(sep + 1));
    if (hash_file(path, digest.substr(0, sep), job) != expected) throw std::runtime_error("Checksum mismatch; the download was not installed");
}
bool is_archive(const std::string& name) {
    for (auto suffix : {".tar.gz", ".tar.xz", ".tar.zst", ".tar.bz2", ".tgz", ".tar", ".zip"})
        if (util::ends_with_ci(name, suffix)) return true;
    return false;
}
void extract(const std::string& source, const std::string& destination, Job& job) {
    if (fs::exists(destination)) throw std::runtime_error("Extraction requires a fresh staging folder");
    // Read declared sizes before writing. Compressed size is a poor estimate for
    // Proton archives, and the archive itself still occupies disk during extraction.
    {
        std::unique_ptr<struct archive, decltype(&archive_read_free)> scan(archive_read_new(), archive_read_free);
        archive_read_support_filter_all(scan.get());
        archive_read_support_format_tar(scan.get());
        archive_read_support_format_zip(scan.get());
        require_archive(archive_read_open_filename(scan.get(), source.c_str(), 65536), scan.get());
        struct archive_entry* entry = nullptr;
        uint64_t needed = 0, entries = 0;
        for (;;) {
            job.report("Checking extraction space", archive_filter_bytes(scan.get(), -1), fs::file_size(source));
            const int result = archive_read_next_header(scan.get(), &entry);
            if (result == ARCHIVE_EOF) break;
            require_archive(result, scan.get());
            const auto size = archive_entry_size(entry);
            if (++entries > 300000 || size < 0 || static_cast<uint64_t>(size) > 16ULL * 1024 * 1024 * 1024 - needed)
                throw std::runtime_error("Archive exceeds the extraction limit");
            needed += size;
            require_archive(archive_read_data_skip(scan.get()), scan.get());
        }
        require_space(destination, needed + entries * 4096);
    }
    fs::create_directories(destination);
    const auto root = fs::canonical(destination);
    std::unique_ptr<struct archive, decltype(&archive_read_free)> reader(archive_read_new(), archive_read_free);
    std::unique_ptr<struct archive, decltype(&archive_write_free)> writer(archive_write_disk_new(), archive_write_free);
    archive_read_support_filter_all(reader.get());
    archive_read_support_format_tar(reader.get());
    archive_read_support_format_zip(reader.get());
    archive_write_disk_set_options(writer.get(), ARCHIVE_EXTRACT_TIME | ARCHIVE_EXTRACT_PERM | ARCHIVE_EXTRACT_SECURE_SYMLINKS | ARCHIVE_EXTRACT_SECURE_NODOTDOT);
    require_archive(archive_read_open_filename(reader.get(), source.c_str(), 65536), reader.get());
    struct archive_entry* entry = nullptr;
    uint64_t expanded = 0, entries = 0;
    for (;;) {
        job.report("Extracting", archive_filter_bytes(reader.get(), -1), fs::file_size(source));
        const int result = archive_read_next_header(reader.get(), &entry);
        if (result == ARCHIVE_EOF) break;
        require_archive(result, reader.get());
        if (++entries > 300000) throw std::runtime_error("Archive contains too many entries");
        const auto relative = safe_relative(archive_entry_pathname(entry));
        const auto type = archive_entry_filetype(entry);
        if (type != AE_IFREG && type != AE_IFDIR && type != AE_IFLNK && !(type == 0 && archive_entry_hardlink(entry))) throw std::runtime_error("Archive contains an unsupported file type");
        const auto declared = archive_entry_size(entry);
        if (declared < 0 || static_cast<uint64_t>(declared) > 16ULL * 1024 * 1024 * 1024 - expanded) throw std::runtime_error("Archive exceeds the extraction limit");
        require_space(destination, declared);
        if (const char* target = archive_entry_symlink(entry)) {
            if (fs::path(target).is_absolute()) throw std::runtime_error("Archive contains an absolute symlink");
            safe_relative(relative.parent_path() / target);
        }
        if (const char* target = archive_entry_hardlink(entry)) {
            const auto link = (root / safe_relative(target)).string();
            archive_entry_set_hardlink(entry, link.c_str());
        }
        const auto path = (root / relative).string();
        archive_entry_set_pathname(entry, path.c_str());
        archive_entry_set_perm(entry, archive_entry_perm(entry) & 0777);
        require_archive(archive_write_header(writer.get(), entry), writer.get());
        const void* buffer = nullptr; size_t size = 0; la_int64_t offset = 0;
        for (;;) {
            job.check();
            const int data_result = archive_read_data_block(reader.get(), &buffer, &size, &offset);
            if (data_result == ARCHIVE_EOF) break;
            require_archive(data_result, reader.get());
            expanded += size;
            if (expanded > 16ULL * 1024 * 1024 * 1024 || offset < 0 || static_cast<uint64_t>(offset) + size > 16ULL * 1024 * 1024 * 1024) throw std::runtime_error("Archive exceeds the extraction limit");
            require_archive(archive_write_data_block(writer.get(), buffer, size, offset), writer.get());
        }
        require_archive(archive_write_finish_entry(writer.get()), writer.get());
    }
    require_archive(archive_write_close(writer.get()), writer.get());
}
}

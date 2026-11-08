#pragma once
#include <atomic>
#include <cstdint>
#include <functional>
#include <string>

namespace downloads {
using Progress = std::function<void(const std::string&, uint64_t, uint64_t)>;
struct Job {
    std::atomic<bool> cancelled{false};
    Progress progress;
    // Optional additional trust configuration (also used by the local HTTPS tests).
    std::string ca_bundle;
    void check() const;
    void report(const std::string& phase, uint64_t done = 0, uint64_t total = 0) const;
};
std::string get(const std::string& url, Job& job);
void fetch(const std::string& url, const std::string& destination, uint64_t expected_size, Job& job);
// Includes a reserve for filesystem metadata and other writers.
void require_space(const std::string& path, uint64_t bytes);
std::string hash_file(const std::string& path, const std::string& algorithm, Job& job);
std::string sha256(const std::string& text);
void verify(const std::string& path, const std::string& digest, Job& job);
// Destination must be a fresh staging directory. Rejects paths and links escaping it.
void extract(const std::string& archive, const std::string& destination, Job& job);
bool is_archive(const std::string& name);
}

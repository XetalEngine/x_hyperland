#pragma once
#include "download.h"
#include <cstdint>
#include <string>
#include <vector>

namespace toolstore {
enum class Kind { Proton, Launcher, Companion };
struct Provider {
    std::string id, name, description, endpoint, website;
    Kind kind = Kind::Proton;
    bool actions = false;
    bool source_archive = false;
};
struct Release {
    std::string provider, version, name, asset, url, page_url, digest, checksum_url, checksum_algorithm;
    uint64_t size = 0;
    bool prerelease = false;
    std::string incompatibility;
    std::string published_at;
};
struct ReleasePage {
    std::vector<Release> releases;
    bool has_more = false;
    std::string notice;
};
struct Installation {
    std::string id, provider, name, version, directory, entrypoint, installed_at;
    Kind kind = Kind::Proton;
    std::string asset, published_at;
    bool prerelease = false;
};
struct Update { Installation current; Release release; };
struct UpdateReport { std::vector<Update> updates; std::string notice; };
const std::vector<Provider>& providers();
const Provider& provider(const std::string& id);
// Parsing is separate from transport to permit offline catalog regression tests.
ReleasePage parse_releases(const Provider& provider, const std::string& response, int page_size = 30);
ReleasePage releases(const Provider& provider, int page, downloads::Job& job);
std::string installation_id(const Release& release);
std::vector<Installation> installed();
std::string umu_launcher();
Installation install_archive(const Release& release, const std::string& archive, downloads::Job& job);
Installation install(const Release& release, downloads::Job& job);
std::vector<Update> find_updates(const std::vector<Installation>& installed, const std::vector<Release>& releases);
UpdateReport check_updates(downloads::Job& job);
void remove(const Installation& installation, const std::vector<std::string>& protected_paths);
}

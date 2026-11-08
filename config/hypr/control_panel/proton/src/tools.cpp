#include "tools.h"
#include "util.h"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <regex>
#include <set>
#include <stdexcept>
#include <sys/file.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/utsname.h>

namespace fs = std::filesystem;
using json = nlohmann::json;
namespace toolstore {
const std::vector<Provider>& providers() {
    static const std::vector<Provider> list = {
        {"ge", "Proton-GE", "Community Proton builds with game fixes and media support.", "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases", "https://github.com/GloriousEggroll/proton-ge-custom"},
        {"cachyos", "Proton-CachyOS", "CachyOS builds; choose a variant supported by your CPU.", "https://api.github.com/repos/CachyOS/proton-cachyos/releases", "https://github.com/CachyOS/proton-cachyos"},
        {"dw", "DW-Proton", "Dawn Winery's Proton builds and game fixes.", "https://api.github.com/repos/dawn-winery/dwproton-mirror/releases", "https://github.com/dawn-winery/dwproton-mirror"},
        {"rtsp", "Proton-RTSP", "Proton with RTSP and media playback patches for VRChat.", "https://api.github.com/repos/SpookySkeletons/proton-rtsp/releases", "https://github.com/SpookySkeletons/proton-rtsp"},
        {"tkg", "Proton-Tkg", "Wine-tkg builds. Upstream CI downloads expire; older expired builds cannot be downloaded.", "https://api.github.com/repos/Frogging-Family/wine-tkg-git/actions/workflows/proton-valvexbe-sniper.yml/runs", "https://github.com/Frogging-Family/wine-tkg-git", Kind::Proton, true},
        {"em", "Proton-EM", "Experimental builds with FSR and Wine Wayland work.", "https://api.github.com/repos/BananaWorks07/Proton/releases", "https://github.com/BananaWorks07/Proton"},
        {"wineland", "Proton-Wineland", "Wayland-focused builds, including WoW64 variants.", "https://api.github.com/repos/nanomatters/proton-cachyos/releases", "https://github.com/nanomatters/proton-cachyos"},
        {"umu-proton", "UMU-Proton", "Valve-based Proton packaged for use outside Steam.", "https://api.github.com/repos/Open-Wine-Components/umu-proton/releases", "https://github.com/Open-Wine-Components/umu-proton"},
        {"umu-launcher", "UMU launcher", "Launches Proton without Steam and downloads its required runtime automatically.", "https://api.github.com/repos/Open-Wine-Components/umu-launcher/releases", "https://github.com/Open-Wine-Components/umu-launcher", Kind::Launcher},
        {"luxtorpeda", "Luxtorpeda", "Linux-native game engines. Can be downloaded here, but does not run Windows .exe files.", "https://codeberg.org/api/v1/repos/luxtorpeda/luxtorpeda/releases", "https://codeberg.org/luxtorpeda/luxtorpeda", Kind::Companion},
        {"steamtinkerlaunch", "Steam Tinker Launch", "Requires Steam. Available for download only; not a standalone Proton runner.", "https://api.github.com/repos/sonic2kk/steamtinkerlaunch/releases", "https://github.com/sonic2kk/steamtinkerlaunch", Kind::Companion, false, true},
        {"boxtron", "Boxtron", "DOSBox integration for Steam; download only, not a Windows .exe runner.", "https://api.github.com/repos/dreamer/boxtron/releases", "https://github.com/dreamer/boxtron", Kind::Companion},
        {"roberta", "Roberta", "ScummVM integration for Steam; download only, not a Windows .exe runner.", "https://api.github.com/repos/dreamer/roberta/releases", "https://github.com/dreamer/roberta", Kind::Companion},
    };
    return list;
}
const Provider& provider(const std::string& id) {
    for (const auto& p : providers()) if (p.id == id) return p;
    throw std::runtime_error("Unknown tool provider: " + id);
}
namespace {
std::string str(const json& j, const char* key, const std::string& fallback = {}) {
    auto it = j.find(key); return it != j.end() && it->is_string() ? it->get<std::string>() : fallback;
}
std::string stem(std::string name) {
    for (auto suffix : {".tar.gz", ".tar.xz", ".tar.zst", ".tar.bz2", ".tgz", ".zip", ".tar"})
        if (util::ends_with_ci(name, suffix)) return name.substr(0, name.size() - std::string(suffix).size());
    return name;
}
std::string compatibility(const std::string& asset) {
    struct utsname host{}; uname(&host);
    const std::string arch = host.machine;
    const auto name = util::lower(asset);
    const bool arm = name.find("aarch64") != std::string::npos || name.find("arm64") != std::string::npos;
    if (arm && arch != "aarch64") return "Requires an ARM64 system";
    if (!arm && arch != "x86_64") return "Requires an x86-64 system";
    if (name.find("native") != std::string::npos) return "Host-specific build; choose a Steam Linux Runtime (SLR) build for UMU";
#if defined(__x86_64__)
    if (name.find("x86_64_v4") != std::string::npos || name.find("x86-64-v4") != std::string::npos) {
        if (!(__builtin_cpu_supports("avx512f") && __builtin_cpu_supports("avx512bw") && __builtin_cpu_supports("avx512cd") && __builtin_cpu_supports("avx512dq") && __builtin_cpu_supports("avx512vl"))) return "Requires an x86-64-v4 CPU";
    }
    if (name.find("x86_64_v3") != std::string::npos || name.find("x86-64-v3") != std::string::npos || name.find("x86_64_v4") != std::string::npos) {
        if (!(__builtin_cpu_supports("avx2") && __builtin_cpu_supports("bmi") && __builtin_cpu_supports("bmi2") && __builtin_cpu_supports("fma") && __builtin_cpu_supports("f16c") && __builtin_cpu_supports("lzcnt") && __builtin_cpu_supports("movbe") && __builtin_cpu_supports("xsave"))) return "Requires an x86-64-v3 CPU";
    }
#endif
    return {};
}
struct StoreLock {
    int fd = -1;
    explicit StoreLock(const std::string& path = util::tools_dir() + "/.lock") {
        fs::create_directories(util::tools_dir());
        fs::create_directories(fs::path(path).parent_path());
        fd = open(path.c_str(), O_CREAT | O_RDWR | O_CLOEXEC, 0600);
        if (fd < 0) throw std::runtime_error("Cannot open the tool store lock");
        if (flock(fd, LOCK_EX | LOCK_NB) != 0) { close(fd); fd = -1; throw std::runtime_error("Another XetalProton instance is changing installed tools"); }
    }
    ~StoreLock() { if (fd >= 0) { flock(fd, LOCK_UN); close(fd); } }
};
struct TemporaryDirectory {
    fs::path path;
    explicit TemporaryDirectory(const std::string& root) {
        fs::create_directories(root);
        std::string pattern = root + "/.staging-XXXXXX";
        if (!mkdtemp(pattern.data())) throw std::runtime_error("Cannot create a temporary installation folder");
        path = pattern;
    }
    ~TemporaryDirectory() { std::error_code ec; fs::remove_all(path, ec); }
};
fs::path find_entry(const fs::path& root, const std::string& name) {
    std::vector<fs::path> matches;
    for (auto it = fs::recursive_directory_iterator(root); it != fs::recursive_directory_iterator(); ++it) {
        if (it.depth() >= 4) it.disable_recursion_pending();
        if (it->is_symlink()) { it.disable_recursion_pending(); continue; }
        if (it->is_regular_file() && it->path().filename() == name) matches.push_back(it->path());
    }
    if (matches.size() > 1) throw std::runtime_error("Archive contains multiple launchers; cannot choose safely");
    return matches.empty() ? fs::path() : matches.front();
}
Installation read_installation(const fs::path& directory) {
    if (fs::is_symlink(directory)) throw std::runtime_error("Linked tool folders are not managed installations");
    std::string text;
    if (!util::read_file((directory / ".xetalproton-tool.json").string(), text)) throw std::runtime_error("Missing installation metadata");
    const auto j = json::parse(text);
    Installation i;
    i.id = directory.filename().string(); i.directory = directory.string();
    i.provider = str(j, "provider"); i.name = str(j, "name"); i.version = str(j, "version");
    i.installed_at = str(j, "installed_at"); i.kind = provider(i.provider).kind;
    i.asset = str(j, "asset"); i.published_at = str(j, "published_at"); i.prerelease = j.value("prerelease", false);
    const fs::path entry = str(j, "entrypoint");
    if (!entry.empty()) {
        if (entry.is_absolute()) throw std::runtime_error("Invalid installation entrypoint");
        for (const auto& part : entry) if (part == "..") throw std::runtime_error("Invalid installation entrypoint");
        i.entrypoint = (directory / entry).string();
        if (!util::file_exists(i.entrypoint)) throw std::runtime_error("Installation is incomplete");
    } else if (i.kind != Kind::Companion) throw std::runtime_error("Installation has no launcher");
    return i;
}
std::string checksum_for(const Release& r, downloads::Job& job) {
    if (!r.digest.empty()) return r.digest;
    if (r.checksum_url.empty()) return {};
    const auto text = downloads::get(r.checksum_url, job);
    std::istringstream lines(text); std::string line;
    while (std::getline(lines, line)) {
        std::istringstream parts(line); std::string hash, name;
        parts >> hash;
        std::getline(parts, name); name = util::trim(name);
        if (!name.empty() && name.front() == '*') name.erase(0, 1);
        const size_t length = r.checksum_algorithm == "sha512" ? 128 : 64;
        if (hash.size() == length && hash.find_first_not_of("0123456789abcdefABCDEF") == std::string::npos && (name.empty() || name == r.asset || name == "./" + r.asset)) return r.checksum_algorithm + ":" + hash;
    }
    throw std::runtime_error("Upstream checksum does not match the selected archive");
}
}

ReleasePage parse_releases(const Provider& p, const std::string& response, int page_size) {
    const auto data = json::parse(response);
    const json& entries = p.actions ? data.at("workflow_runs") : data;
    if (!entries.is_array()) throw std::runtime_error("Upstream did not return a release list");
    ReleasePage page;
    page.has_more = entries.size() >= static_cast<size_t>(page_size);
    for (const auto& entry : entries) {
        if (entry.value("draft", false)) continue;
        if (p.actions) {
            if (str(entry, "conclusion") != "success") continue;
            const auto id = std::to_string(entry.at("id").get<uint64_t>());
            Release r;
            r.provider = p.id; r.version = id;
            r.published_at = str(entry, "created_at");
            r.name = "Proton-Tkg " + str(entry, "created_at").substr(0, 10) + " (" + str(entry, "head_sha").substr(0, 7) + ")";
            r.asset = "proton-tkg-build.zip";
            r.url = "https://nightly.link/Frogging-Family/wine-tkg-git/actions/runs/" + id + "/proton-tkg-build.zip";
            r.page_url = str(entry, "html_url", p.website);
            r.incompatibility = compatibility(r.asset);
            page.releases.push_back(r);
            continue;
        }
        const auto version = str(entry, "tag_name");
        if (version.empty()) continue;
        auto assets = entry.value("assets", json::array());
        if (!assets.is_array()) continue;
        if (p.source_archive && !str(entry, "tarball_url").empty()) assets.push_back({{"name", p.id + "-" + version + ".tar.gz"}, {"browser_download_url", entry["tarball_url"]}, {"size", 0}});
        for (const auto& asset : assets) {
            const auto name = str(asset, "name");
            if (!downloads::is_archive(name)) continue;
            const auto lower = util::lower(name);
            if (lower.find("debug") != std::string::npos || lower.find("symbols") != std::string::npos || lower.find("source") != std::string::npos) continue;
            if (p.kind == Kind::Launcher && name.find("zipapp") == std::string::npos) continue;
            Release r;
            r.provider = p.id; r.version = version; r.name = str(entry, "name", version); r.asset = name;
            r.published_at = str(entry, "published_at", str(entry, "created_at"));
            r.url = str(asset, "browser_download_url"); r.page_url = str(entry, "html_url", p.website);
            if (r.url.empty()) continue;
            r.size = asset.value("size", uint64_t(0)); r.prerelease = entry.value("prerelease", false);
            const auto digest = str(asset, "digest");
            if (digest.starts_with("sha256:") || digest.starts_with("sha512:")) r.digest = digest;
            if (p.kind == Kind::Proton) r.incompatibility = compatibility(name);
            for (const auto& sum : assets) {
                for (auto algorithm : {"sha512", "sha256"}) {
                    for (auto base : {name, stem(name)}) {
                        const auto checksum_name = str(sum, "name");
                        if (checksum_name == base + "." + algorithm || checksum_name == base + "." + algorithm + "sum") {
                            r.checksum_url = str(sum, "browser_download_url"); r.checksum_algorithm = algorithm;
                        }
                    }
                }
            }
            page.releases.push_back(r);
        }
    }
    return page;
}
ReleasePage releases(const Provider& p, int page, downloads::Job& job) {
    if (page < 1) throw std::runtime_error("Invalid release page");
    const auto url = p.endpoint + (p.actions ? "?status=success&" : "?") + "per_page=30&limit=30&page=" + std::to_string(page);
    const auto cache = util::data_dir() + "/catalog-cache/" + p.id + "-" + std::to_string(page) + ".json";
    try {
        const auto data = downloads::get(url, job);
        auto result = parse_releases(p, data);
        util::write_file(cache, data);
        return result;
    } catch (const std::exception& error) {
        job.check();
        std::string cached;
        if (!util::read_file(cache, cached)) throw;
        auto result = parse_releases(p, cached);
        result.notice = std::string("Showing cached releases. ") + error.what();
        return result;
    }
}
std::string installation_id(const Release& r) {
    return r.provider + "-" + util::sanitize_filename(stem(r.asset)).substr(0, 90) + "-" + downloads::sha256(r.provider + "/" + r.version + "/" + r.asset).substr(0, 10);
}
std::vector<Installation> installed() {
    std::vector<Installation> result;
    for (const auto& dir : util::list_dir(util::tools_dir(), true)) {
        if (util::basename(dir).starts_with('.')) continue;
        try { result.push_back(read_installation(dir)); } catch (...) { /* Interrupted or external folders are not managed. */ }
    }
    std::sort(result.begin(), result.end(), [](const auto& a, const auto& b) { return a.installed_at > b.installed_at; });
    return result;
}
std::string umu_launcher() {
    for (const auto& i : installed()) if (i.kind == Kind::Launcher) return i.entrypoint;
    return {};
}
Installation install_archive(const Release& release, const std::string& archive, downloads::Job& job) {
    const auto& p = provider(release.provider);
    if (!release.incompatibility.empty()) throw std::runtime_error(release.incompatibility);
    StoreLock lock;
    const auto target = fs::path(util::tools_dir()) / installation_id(release);
    if (fs::exists(target)) throw std::runtime_error("This release is already installed");
    TemporaryDirectory stage(util::tools_dir());
    auto contents = stage.path / "contents";
    if (!release.digest.empty()) downloads::verify(archive, release.digest, job);
    downloads::extract(archive, contents.string(), job);
    const std::string wanted = p.kind == Kind::Launcher ? "umu-run" : "proton";
    fs::path entry;
    if (p.kind != Kind::Companion) {
        entry = find_entry(contents, wanted);
        if (entry.empty() && p.actions) {
            std::vector<fs::path> archives;
            for (const auto& file : fs::recursive_directory_iterator(contents))
                if (!file.is_symlink() && file.is_regular_file() && downloads::is_archive(file.path().string())) archives.push_back(file.path());
            if (archives.size() != 1) throw std::runtime_error("Expected one Proton archive inside the CI download");
            const auto nested = stage.path / "nested";
            downloads::extract(archives.front().string(), nested.string(), job);
            fs::remove_all(contents);
            fs::rename(nested, contents);
            entry = find_entry(contents, wanted);
        }
        if (entry.empty()) throw std::runtime_error("The download does not contain a " + wanted + " launcher");
        fs::permissions(entry, fs::perms::owner_exec | fs::perms::group_exec | fs::perms::others_exec, fs::perm_options::add);
    }
    const auto relative = entry.empty() ? std::string() : entry.lexically_relative(contents).string();
    json metadata = {{"provider", p.id}, {"name", release.name}, {"version", release.version}, {"asset", release.asset}, {"url", release.url}, {"entrypoint", relative}, {"installed_at", util::timestamp("%Y-%m-%dT%H:%M:%S")}, {"published_at", release.published_at}, {"prerelease", release.prerelease}};
    if (!util::write_file((contents / ".xetalproton-tool.json").string(), metadata.dump(2))) throw std::runtime_error("Cannot save installation metadata");
    job.report("Finishing installation");
    fs::rename(contents, target);
    return read_installation(target);
}
Installation install(const Release& release, downloads::Job& job) {
    if (!release.incompatibility.empty()) throw std::runtime_error(release.incompatibility);
    if (provider(release.provider).kind == Kind::Proton && umu_launcher().empty()) {
        job.report("Preparing UMU launcher");
        const auto page = releases(provider("umu-launcher"), 1, job);
        auto found = std::find_if(page.releases.begin(), page.releases.end(), [](const auto& r) { return !r.prerelease; });
        if (found == page.releases.end()) throw std::runtime_error("UMU's standalone launcher is unavailable upstream");
        install(*found, job);
    }
    auto checked = release;
    checked.digest = checksum_for(release, job);
    const auto cache = util::data_dir() + "/downloads/" + downloads::sha256(release.url + checked.digest);
    StoreLock download_lock(cache + "/.lock");
    const auto path = cache + "/download.archive";
    downloads::fetch(release.url, path, release.size, job);
    if (!checked.digest.empty()) {
        try { downloads::verify(path, checked.digest, job); }
        catch (...) {
            if (!job.cancelled) { fs::remove(path); fs::remove(path + ".json"); }
            throw;
        }
    }
    // install_archive also verifies archives supplied directly by callers.
    auto verified = checked; verified.digest.clear();
    const auto result = install_archive(verified, path, job);
    fs::remove(path); fs::remove(path + ".json");
    return result;
}
namespace {
std::string variant(const std::string& asset) {
    // Preserve architecture, CPU level, WoW64, HDR, SLR/native, etc. Strip only
    // version numbers, never arbitrary suffixes or architecture digits.
    auto name = util::lower(stem(asset));
    const std::string arch = name.find("aarch64") != std::string::npos || name.find("arm64") != std::string::npos ? "arm64" : "x86_64";
    const std::string level = name.find("x86_64_v4") != std::string::npos || name.find("x86-64-v4") != std::string::npos ? "v4" :
        name.find("x86_64_v3") != std::string::npos || name.find("x86-64-v3") != std::string::npos ? "v3" : "baseline";
    const bool wow64 = name.find("wow64") != std::string::npos;
    const std::vector<std::string> tokens = {"x86_64_v3", "x86_64_v4", "x86-64-v3", "x86-64-v4", "x86_64", "x86-64", "aarch64", "arm64", "wow64"};
    for (const auto& token : tokens) {
        size_t pos = 0;
        while ((pos = name.find(token, pos)) != std::string::npos) name.erase(pos, token.size());
    }
    name = std::regex_replace(name, std::regex("[0-9]+([._-][0-9]+)*"), "#");
    name = std::regex_replace(name, std::regex("[-_.]+"), "-");
    while (!name.empty() && name.back() == '-') name.pop_back();
    return name + "|" + arch + "|" + level + (wow64 ? "|wow64" : "");
}
}
std::vector<Update> find_updates(const std::vector<Installation>& local, const std::vector<Release>& catalog) {
    std::vector<Update> result;
    std::set<std::string> offered;
    for (const auto& item : local) {
        if (item.asset.empty()) continue;
        std::string published = item.published_at;
        bool prerelease = item.prerelease;
        for (const auto& r : catalog) if (r.provider == item.provider && r.version == item.version && r.asset == item.asset) {
            published = r.published_at; prerelease = r.prerelease; break;
        }
        // Older installations have no publication date. Their installation
        // time is a conservative lower bound for a future release notification.
        if (published.empty()) published = item.installed_at;
        if (published.empty()) continue;
        const Release* newest = nullptr;
        for (const auto& r : catalog) {
            if (r.provider != item.provider || r.version == item.version || r.published_at <= published ||
                !r.incompatibility.empty() || (r.prerelease && !prerelease) || variant(r.asset) != variant(item.asset)) continue;
            if (!newest || r.published_at > newest->published_at) newest = &r;
        }
        if (!newest) continue;
        const auto id = installation_id(*newest);
        if (std::any_of(local.begin(), local.end(), [&](const auto& i) { return i.id == id; }) || !offered.insert(id).second) continue;
        result.push_back({item, *newest});
    }
    return result;
}
UpdateReport check_updates(downloads::Job& job) {
    UpdateReport result;
    const auto local = installed();
    std::set<std::string> checked;
    std::vector<Release> catalog;
    for (const auto& item : local) {
        if (!checked.insert(item.provider).second) continue;
        try {
            job.report("Checking " + provider(item.provider).name);
            const auto page = releases(provider(item.provider), 1, job);
            if (!page.notice.empty()) throw std::runtime_error(page.notice);
            catalog.insert(catalog.end(), page.releases.begin(), page.releases.end());
        } catch (const std::exception& error) {
            job.check();
            result.notice += provider(item.provider).name + ": " + error.what() + "\n";
        }
    }
    result.updates = find_updates(local, catalog);
    return result;
}
void remove(const Installation& i, const std::vector<std::string>& protected_paths) {
    StoreLock lock;
    const auto root = fs::canonical(util::tools_dir());
    const auto path = fs::path(i.directory);
    if (fs::is_symlink(path) || fs::canonical(path).parent_path() != root) throw std::runtime_error("Only XetalProton-owned installations can be removed");
    const auto current = read_installation(path);
    if (current.id != i.id || current.provider != i.provider) throw std::runtime_error("Installation changed; refresh the installed list");
    for (const auto& used : protected_paths) {
        auto relative = fs::weakly_canonical(used).lexically_relative(fs::canonical(path));
        if (!relative.empty() && *relative.begin() != "..") throw std::runtime_error("This version is assigned to a prefix or shortcut. Choose another version first.");
    }
    // Rename first: scanning can never observe a half-removed installation.
    TemporaryDirectory trash(util::tools_dir());
    fs::rename(path, trash.path / "removed");
}
}

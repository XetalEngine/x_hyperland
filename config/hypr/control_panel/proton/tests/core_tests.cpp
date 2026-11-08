#include "config.h"
#include "download.h"
#include "dependencies.h"
#include "launcher.h"
#include "steam.h"
#include "tools.h"
#include "util.h"
#include <archive.h>
#include <archive_entry.h>
#include <nlohmann/json.hpp>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <limits>
#include <unistd.h>
#include <sys/wait.h>

namespace fs = std::filesystem;
using json = nlohmann::json;
void check(bool value, const std::string& message) { if (!value) throw std::runtime_error(message); }
template<class F> void rejects(F operation, const std::string& message) {
    bool failed = false;
    try { operation(); } catch (const std::exception&) { failed = true; }
    check(failed, message);
}
struct Entry { std::string path, data, link; int type = AE_IFREG; int mode = 0755; };
void archive_file(const fs::path& path, const std::vector<Entry>& entries, bool zip = false) {
    auto* out = archive_write_new();
    if (zip) archive_write_set_format_zip(out); else archive_write_set_format_pax_restricted(out);
    check(archive_write_open_filename(out, path.c_str()) == ARCHIVE_OK, "open test archive");
    for (const auto& file : entries) {
        auto* e = archive_entry_new();
        archive_entry_set_pathname(e, file.path.c_str());
        archive_entry_set_filetype(e, file.type);
        archive_entry_set_perm(e, file.mode);
        if (file.type == AE_IFLNK) archive_entry_set_symlink(e, file.link.c_str());
        else if (!file.link.empty()) archive_entry_set_hardlink(e, file.link.c_str());
        archive_entry_set_size(e, file.type == AE_IFREG && file.link.empty() ? file.data.size() : 0);
        check(archive_write_header(out, e) == ARCHIVE_OK, "write test header");
        if (file.type == AE_IFREG && file.link.empty()) check(archive_write_data(out, file.data.data(), file.data.size()) == static_cast<la_ssize_t>(file.data.size()), "write test data");
        archive_entry_free(e);
    }
    archive_write_close(out); archive_write_free(out);
}
toolstore::Release release(std::string provider, std::string version) {
    toolstore::Release r;
    r.provider = provider; r.name = version; r.version = version; r.asset = version + ".tar";
    r.url = "https://example.com/" + r.asset;
    return r;
}
void offline_tests(const fs::path& root) {
    downloads::Job job;
    check(util::data_dir() == (root / "data").string(), "portable data root");
    auto config = load_config();
    check(!config.discover_steam, "Steam discovery must be off by default");
    check(config.prefixes_root == util::data_dir() + "/prefixes", "app-owned prefixes");
    config.prefixes.push_back({"Existing", "/some/existing/prefix"});
    config.prefix_proton["/some/existing/prefix"] = "/existing/Proton";
    check(save_config(config), "save config");
    auto restored = load_config();
    check(restored.prefixes[0].path == "/some/existing/prefix" && restored.prefix_proton == config.prefix_proton, "preserve existing prefix and tool paths");

    json catalog = json::array({
        {{"tag_name", "GE-42"}, {"name", "GE 42"}, {"prerelease", true}, {"assets", json::array({
            {{"name", "GE-42-x86_64.tar.gz"}, {"size", 123}, {"browser_download_url", "https://example.com/x86"}, {"digest", nullptr}},
            {{"name", "GE-42-x86_64.sha512sum"}, {"browser_download_url", "https://example.com/checksum"}},
            {{"name", "GE-42-aarch64.tar.gz"}, {"size", 123}, {"browser_download_url", "https://example.com/arm"}},
            {{"name", "GE-42-debug.tar.gz"}, {"size", 456}, {"browser_download_url", "https://example.com/debug"}}
        })}},
        {{"tag_name", "GE-41"}, {"assets", json::array()}}
    });
    const auto page = toolstore::parse_releases(toolstore::provider("ge"), catalog.dump(), 2);
    check(page.has_more && page.releases.size() == 2, "pagination and binary asset filtering");
    check(page.releases[0].checksum_algorithm == "sha512" && page.releases[0].prerelease, "checksum matching and prereleases");
    check(page.releases[0].incompatibility.empty() != page.releases[1].incompatibility.empty(), "architecture filtering");
    const auto stl = toolstore::parse_releases(toolstore::provider("steamtinkerlaunch"), R"([{"tag_name":"v1","tarball_url":"https://example.com/source","assets":[]}])");
    check(stl.releases.size() == 1, "source-only companion release");
    const auto ci = toolstore::parse_releases(toolstore::provider("tkg"), R"({"workflow_runs":[{"id":123,"conclusion":"success","head_sha":"abcdef12","created_at":"2026-09-01"},{"id":124,"conclusion":"failure"}]})");
    check(ci.releases.size() == 1 && ci.releases[0].url.find("/123/") != std::string::npos, "CI release URL");
    rejects([&] { toolstore::parse_releases(toolstore::provider("ge"), "{}"); }, "malformed metadata rejected");
    check(toolstore::installation_id(page.releases[0]) != toolstore::installation_id(page.releases[1]), "architecture variants have distinct install IDs");
    auto previous = release("ge", "GE-Proton9-9");
    previous.asset = "GE-Proton9-9-x86_64.tar.gz"; previous.published_at = "2025-01-01T00:00:00Z";
    toolstore::Installation old;
    old.id = toolstore::installation_id(previous); old.provider = "ge"; old.version = previous.version;
    old.asset = previous.asset; old.published_at = previous.published_at;
    auto next = release("ge", "GE-Proton9-10");
    next.asset = "GE-Proton9-10-x86_64.tar.gz"; next.published_at = "2025-02-01T00:00:00Z";
    auto arm = next; arm.asset = "GE-Proton9-10-aarch64.tar.gz";
    auto v3 = next; v3.asset = "GE-Proton9-10-x86_64_v3.tar.gz";
    auto beta = next; beta.version = "GE-Proton10-1"; beta.asset = "GE-Proton10-1-x86_64.tar.gz"; beta.prerelease = true; beta.published_at = "2025-03-01T00:00:00Z";
    auto updates = toolstore::find_updates({old}, {previous, arm, v3, next, beta});
    check(updates.size() == 1 && updates[0].release.version == next.version, "updates respect architecture and stable channel, not lexical version order");
    check(toolstore::find_updates({old}, {previous, arm, v3, beta}).empty(), "other variants are not updates");
    auto legacy_arch = old; legacy_arch.asset = "GE-Proton9-9.tar.gz";
    check(toolstore::find_updates({legacy_arch}, {next}).size() == 1, "implicit legacy x86-64 builds match explicit x86-64 builds");
    auto wow64 = next; wow64.asset = "GE-Proton9-10-x86_64_wow64.tar.gz";
    check(toolstore::find_updates({old}, {wow64}).empty(), "WoW64 is a distinct update variant");
    auto current = old; current.id = toolstore::installation_id(next); current.asset = next.asset; current.version = next.version; current.published_at = next.published_at;
    check(toolstore::find_updates({old, current}, {previous, next}).empty(), "already installed newer releases not offered");
    old.published_at.clear();
    check(toolstore::find_updates({old}, {previous, next}).size() == 1, "legacy metadata uses matching upstream publication date");
    rejects([&] { downloads::require_space(root.string(), std::numeric_limits<uint64_t>::max()); }, "disk-space preflight rejects impossible allocation without overflow");

    auto proton_release = release("ge", "Test-Proton");
    const auto good = root / "proton.tar";
    archive_file(good, {
        {"Test-Proton/proton", "#!/bin/sh\nexit 0\n", ""},
        {"Test-Proton/version", "0 Test-Proton\n", ""},
        {"Test-Proton/protonfixes/winetricks", "w_metadata corefonts fonts\nw_metadata vcrun2022 dlls\n", ""},
        {"Test-Proton/files/bin/wineserver", "#!/bin/sh\nexit 0\n", ""},
        {"Test-Proton/files/lib/link", "", "../bin/wineserver", AE_IFLNK},
        {"Test-Proton/files/bin/server-copy", "", "Test-Proton/files/bin/wineserver"},
        {"Test-Proton/setuid", "test", "", AE_IFREG, 04755}
    });
    proton_release.digest = "sha256:" + downloads::hash_file(good, "sha256", job);
    auto tool = toolstore::install_archive(proton_release, good, job);
    check(util::file_exists(tool.entrypoint), "complete tool installed");
    check(fs::is_symlink(fs::path(tool.entrypoint).parent_path() / "files/lib/link"), "safe relative symlinks preserved");
    check((fs::status(fs::path(tool.entrypoint).parent_path() / "setuid").permissions() & fs::perms::set_uid) == fs::perms::none, "setuid mode stripped");
    rejects([&] { toolstore::install_archive(proton_release, good, job); }, "duplicate install must not overwrite");
    rejects([&] { toolstore::remove(tool, {util::dirname(tool.entrypoint)}); }, "assigned version cannot be removed");
    check(util::file_exists(tool.entrypoint), "in-use tool intact");
    const auto info = scan_installations(false);
    check(info.root.empty() && info.libraries.empty() && info.prefixes.empty() && info.protons.size() == 1, "managed tool discovered without Steam");
    const auto missing_launcher = build_launch(info.protons.front(), (root / "prefix").string(), "cmd.exe", "", "run", true, {}, "", root.string(), "Missing launcher");
    check(!missing_launcher.error.empty() && missing_launcher.argv.empty(), "missing runtime launcher produces an actionable error");

    for (const auto& bad_entry : std::vector<Entry>{
        {"../escape", "bad", ""},
        {"/tmp/xetal-archive-escape", "bad", ""},
        {"tool/escape", "", "../../escape", AE_IFLNK},
        {"tool/absolute", "", "/tmp", AE_IFLNK},
        {"tool/hard", "", "../escape"}
    }) {
        const auto bad = root / "bad.tar";
        archive_file(bad, {bad_entry});
        const auto out = root / "bad-output";
        fs::remove_all(out);
        rejects([&] { downloads::extract(bad, out, job); }, "unsafe archive rejected: " + bad_entry.path);
    }
    check(!fs::exists(root / "escape"), "no path traversal output");
    auto wrong = release("ge", "Wrong-checksum"); wrong.digest = "sha256:" + std::string(64, '0');
    rejects([&] { toolstore::install_archive(wrong, good, job); }, "checksum mismatch rejected");
    check(toolstore::installed().size() == 1, "checksum failure not visible in inventory");
    downloads::Job cancelled; cancelled.cancelled = true;
    rejects([&] { toolstore::install_archive(release("ge", "Cancelled"), good, cancelled); }, "cancellation rejected");
    check(toolstore::installed().size() == 1, "cancelled installation not visible");
    for (const auto& dir : util::list_dir(util::tools_dir())) check(!util::basename(dir).starts_with(".staging-"), "staging cleaned after failure");

    const auto nested = root / "nested.zip";
    std::string archive_bytes; util::read_file(good, archive_bytes);
    archive_file(nested, {{"proton-build.tar", archive_bytes, ""}}, true);
    auto tkg = toolstore::install_archive(release("tkg", "CI-test"), nested, job);
    check(util::file_exists(tkg.entrypoint), "nested CI archive installed");

    auto launcher_release = release("umu-launcher", "Test-UMU");
    const auto launcher_archive = root / "umu.tar";
    archive_file(launcher_archive, {{"umu/umu-run", "#!/bin/sh\nprintf '%s\\n' \"$PROTONPATH\" \"$WINEPREFIX\" \"$UMU_FOLDERS_PATH\" \"$STEAM_COMPAT_CLIENT_INSTALL_PATH\" \"$@\" > \"$XETAL_TEST_OUTPUT\"\n", ""}});
    const auto launcher = toolstore::install_archive(launcher_release, launcher_archive, job);
    check(toolstore::umu_launcher() == launcher.entrypoint, "managed UMU selected");
    const auto prefix = (root / "data/prefixes/Shared prefix").string();
    auto spec = build_launch(info.protons[0], prefix, "/tmp/Program Files/app.exe", "--flag 'two words'", "run", true, {{"XETAL_TEST_OUTPUT", (root / "launch.txt").string()}}, "", root.string(), "Example app");
    check(spec.error.empty(), spec.error);
    check(spec.argv.size() == 4 && spec.argv[0] == launcher.entrypoint && spec.argv[3] == "two words", "UMU command preserves arguments");
    check(spec.env.at("PROTONPATH") == util::dirname(tool.entrypoint) && spec.env.at("UMU_FOLDERS_PATH") == util::runtimes_dir(), "managed tool and runtime env");
    check(spec.env.at("STEAM_COMPAT_CLIENT_INSTALL_PATH").empty() && spec.env.at("STEAM_COMPAT_LIBRARY_PATHS").empty(), "launch does not use Steam");
    ProcessManager process;
    check(process.start(spec) > 0, "launch mock UMU");
    for (int count = 0; count < 100 && process.snapshot()[0].running; ++count) std::this_thread::sleep_for(std::chrono::milliseconds(10));
    check(!process.snapshot()[0].running && process.snapshot()[0].exit_code == 0, "process reaped successfully");
    check(fs::is_directory(prefix + "/pfx"), "compatdata prefix layout created before UMU");
    std::string launch_output; check(util::read_file((root / "launch.txt").string(), launch_output), "captured launcher output");
    check(launch_output.find("two words\n") != std::string::npos && launch_output.find(util::runtimes_dir()) != std::string::npos, "actual child environment");
    const auto script = root / "launch.sh";
    util::write_file(script, spec_to_script(spec));
    int code = -1; util::run_capture({"/bin/sh", script.string(), "extra arg"}, &code);
    check(code == 0, "exported launch script");
    util::read_file((root / "launch.txt").string(), launch_output);
    check(launch_output.ends_with("extra arg\n"), "exported script appends arguments to launch");
    auto host = build_launch(info.protons[0], prefix, "winecfg", "", "runinprefix", false, {}, "", root.string(), "Host tool");
    const auto second_host = build_launch(info.protons[0], prefix, "winecfg", "", "runinprefix", false, {}, "", root.string(), "Host tool");
    check(host.log_path != second_host.log_path, "simultaneous launches have distinct logs");
    const auto invalid_environment = build_launch(info.protons[0], prefix, "winecfg", "", "runinprefix", false, {}, "BAD;COMMAND=value", root.string(), "Invalid environment");
    check(!invalid_environment.error.empty(), "invalid environment names cannot enter exported scripts");
    check(host.argv[0] == info.protons[0].script() && host.env.at("WINEPREFIX") == prefix + "/pfx", "explicit host mode");
    const auto native = build_launch(info.protons[0], prefix, "/path/to/wineserver", "-k", "run", true, {{"@native", "1"}}, "", root.string(), "Wine helper");
    check(native.argv[1] == "/usr/bin/env" && native.argv[2] == "WINEPREFIX=" + prefix + "/pfx" && native.env.at("UMU_NO_PROTON") == "1", "native helpers address the actual Wine prefix");
    check(dependencies::status(prefix).installed.empty(), "new prefix has no recorded dependencies");
    util::write_file(prefix + "/pfx/winetricks.log", "corefonts\nvcrun2022\nvcrun20100\n# dotnet48\n");
    const auto components = dependencies::status(prefix);
    check(components.installed.contains("corefonts") && !components.installed.contains("vcrun2010") && !components.installed.contains("dotnet48"), "dependency records match exact verbs");
    check(dependencies::status((root / "other-prefix").string()).installed.empty(), "dependency status is isolated by prefix");
    dependencies::record_result(prefix, "corefonts", "Installer failed");
    check(!dependencies::status(prefix).installed.contains("corefonts"), "failure overrides prematurely written Winetricks record");
    dependencies::record_result(prefix, "corefonts", "");
    check(dependencies::status(prefix).installed.contains("corefonts"), "successful retry clears failure state");
    const auto install = dependencies::build_install(info.protons[0], prefix, "corefonts");
    check(install.error.empty() && install.exclusive_prefix, "supported dependency has exclusive installation spec");
    check(install.argv == std::vector<std::string>{launcher.entrypoint, "winetricks", "corefonts"}, "dependency uses selected managed UMU");
    check(install.env.at("PROTON_VERB") == "waitforexitandrun", "Protonfixes recognizes the Winetricks launch verb");
    check(install.env.at("PROTONPATH") == info.protons[0].dir && install.env.at("WINEPREFIX") == prefix &&
        install.env.at("W_CACHE").starts_with(util::data_dir()), "dependency prefix, Proton, and cache are app-managed");
    check(!dependencies::build_install(info.protons[0], prefix, "dotnet48").error.empty(), "unsupported verbs disabled for older bundled Winetricks");
    check(!dependencies::build_install(info.protons[0], prefix, "corefonts; touch /tmp/bad").error.empty(), "only catalogued dependency verbs allowed");
    LaunchSpec sleeper;
    sleeper.argv = {"/bin/sleep", "10"}; sleeper.cwd = root.string(); sleeper.prefix_path = prefix;
    sleeper.log_path = (root / "lock.log").string(); sleeper.label = "Prefix lock test"; sleeper.exclusive_prefix = true;
    const auto owner = process.start(sleeper);
    check(owner > 0 && dependencies::busy(prefix), "installer holds prefix lock");
    check(process.start(spec) < 0, "app launch rejected while installer owns prefix");
    auto other = sleeper; other.prefix_path = (root / "unrelated-prefix").string();
    const auto other_pid = process.start(other);
    check(other_pid > 0, "another prefix remains usable");
    process.kill(owner); process.kill(other_pid);
    for (int n = 0; n < 100 && dependencies::busy(prefix); ++n) { process.snapshot(); std::this_thread::sleep_for(std::chrono::milliseconds(10)); }
    check(!dependencies::busy(prefix), "prefix lock released when installer exits");
    toolstore::remove(tkg, {});
    toolstore::remove(tool, {});
    check(fs::is_directory(prefix + "/pfx"), "removing Proton keeps prefixes");
    check(scan_installations(false).protons.empty(), "removed versions disappear from discovery");
    rejects([&] { auto external = tool; external.directory = root.string(); toolstore::remove(external, {}); }, "external directory removal rejected");
    toolstore::remove(launcher, {});
    std::cout << "All offline core tests passed\n";
}
void download_tests(const fs::path& root, const std::string& url, const std::string& ca) {
    downloads::Job job; job.ca_bundle = ca;
    const std::string bytes(256 * 1024, 'a'), changed(256 * 1024, 'b');
    for (const auto& mode : {"resume", "ignore", "changed", "changed-range", "range416", "unknown"}) {
        const auto path = (root / mode).string();
        downloads::fetch(url + "/" + mode, path, std::string(mode) == "unknown" ? 0 : bytes.size(), job);
        std::string data; check(util::read_file(path, data), "read downloaded data");
        check(data == (std::string(mode).starts_with("changed") ? changed : bytes), std::string(mode) + " produces complete, unmixed bytes");
        downloads::fetch(url + "/" + mode, path, std::string(mode) == "unknown" ? 0 : bytes.size(), job); // completed cache, no network
    }
    check(downloads::get(url + "/metadata", job) == "recovered", "metadata retry after HTTP 503");
    const auto cancelled_path = (root / "cancelled-download").string();
    downloads::Job cancel; cancel.ca_bundle = ca;
    cancel.progress = [&](const auto&, uint64_t done, uint64_t) { if (done >= 32768) cancel.cancelled = true; };
    rejects([&] { downloads::fetch(url + "/cancel", cancelled_path, bytes.size(), cancel); }, "mid-transfer cancellation");
    check(fs::file_size(cancelled_path) > 0 && fs::file_size(cancelled_path) < bytes.size(), "cancelled partial retained");
    downloads::fetch(url + "/cancel", cancelled_path, bytes.size(), job);
    std::string data; util::read_file(cancelled_path, data); check(data == bytes, "cancelled transfer resumes correctly");
    const auto crash_path = (root / "crashed-download").string();
    const auto child = fork();
    check(child >= 0, "fork crash recovery test");
    if (child == 0) {
        downloads::Job crash; crash.ca_bundle = ca;
        crash.progress = [](const auto&, uint64_t done, uint64_t) { if (done >= 32768) _exit(17); };
        try { downloads::fetch(url + "/crash", crash_path, bytes.size(), crash); } catch (...) {}
        _exit(18);
    }
    int child_status = 0; waitpid(child, &child_status, 0);
    check(WIFEXITED(child_status) && WEXITSTATUS(child_status) == 17, "downloader exited abruptly");
    downloads::fetch(url + "/crash", crash_path, bytes.size(), job);
    util::read_file(crash_path, data); check(data == bytes, "new process resumes after abrupt exit");
    rejects([&] { downloads::fetch(url + "/invalid-range", (root / "invalid").string(), bytes.size(), job); }, "malformed Content-Range rejected");
    rejects([&] { downloads::get(url + "/missing", job); }, "permanent HTTP error not retried");
    downloads::Job untrusted;
    rejects([&] { downloads::get(url + "/metadata", untrusted); }, "untrusted HTTPS certificates still rejected");
    std::cout << "HTTPS retry/resume/cancellation tests passed\n";
}
void upstream_tests(bool install_umu) {
    downloads::Job job;
    for (const auto& provider : toolstore::providers()) {
        const auto page = toolstore::releases(provider, 1, job);
        check(!page.releases.empty(), "No upstream assets for " + provider.name);
        check(page.notice.empty(), "Expected live metadata for " + provider.name);
        std::cout << provider.name << ": " << page.releases.size() << " assets\n";
        if (install_umu && provider.kind == toolstore::Kind::Launcher) {
            const auto i = toolstore::install(page.releases.front(), job);
            int code = -1;
            const auto output = util::run_capture({"python3", i.entrypoint, "--help"}, &code);
            check(code == 0 && output.find("usage:") != std::string::npos, "real UMU zipapp runs");
            std::cout << "Real UMU download, checksum, install and --help passed\n";
        }
    }
}
void proton_smoke(const fs::path& root) {
    downloads::Job job;
    std::string previous;
    job.progress = [&](const std::string& phase, uint64_t, uint64_t) {
        if (phase != previous) { previous = phase; std::cout << phase << std::endl; }
    };
    const auto page = toolstore::releases(toolstore::provider("umu-proton"), 1, job);
    check(!page.releases.empty(), "No UMU-Proton release available");
    toolstore::install(page.releases.front(), job);
    const auto info = scan_installations(false);
    check(info.root.empty() && info.protons.size() == 1, "smoke test has only app-managed Proton");
    const auto prefix = (root / "data/prefixes/smoke").string();
    const auto spec = build_launch(info.protons.front(), prefix, "cmd.exe", "/c echo XETALPROTON_SMOKE_OK", "waitforexitandrun", true, {}, "", root.string(), "Standalone smoke");
    check(spec.error.empty(), spec.error);
    std::cout << "Launching real Proton via UMU. Log: " << spec.log_path << std::endl;
    ProcessManager process;
    check(process.start(spec) > 0, "start Proton smoke");
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::minutes(5);
    while (process.snapshot().front().running && std::chrono::steady_clock::now() < deadline) std::this_thread::sleep_for(std::chrono::milliseconds(100));
    const auto state = process.snapshot().front();
    if (state.running) { process.kill(state.pid, true); throw std::runtime_error("Proton smoke timed out: " + spec.log_path); }
    std::string output; util::read_file(spec.log_path, output);
    if (state.exit_code != 0) std::cerr << output << '\n';
    check(state.exit_code == 0, "Real Proton exit code " + std::to_string(state.exit_code));
    check(output.find("\nXETALPROTON_SMOKE_OK") != std::string::npos, "Windows command output missing");
    check(fs::is_directory(prefix + "/pfx/drive_c"), "real Windows prefix created");
    check(fs::is_directory(util::runtimes_dir() + "/umu"), "runtime stored under XetalProton");
    std::cout << "Real Proton ran cmd.exe without Steam paths; prefix and runtime are app-owned\n";
}
int main(int argc, char** argv) {
    std::string temporary = "/tmp/xetalproton-tests-XXXXXX";
    if (!mkdtemp(temporary.data())) return 1;
    const fs::path root = temporary;
    setenv("XETALPROTON_HOME", (root / "data").c_str(), 1);
    try {
        if (argc == 4 && std::string(argv[1]) == "--download-tests") download_tests(root, argv[2], argv[3]);
        else if (argc > 1 && std::string(argv[1]) == "--upstream") upstream_tests(true);
        else if (argc > 1 && std::string(argv[1]) == "--proton-smoke") proton_smoke(root);
        else offline_tests(root);
        fs::remove_all(root);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << "\nFixtures retained at " << root << '\n';
        return 1;
    }
}

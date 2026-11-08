#include "dependencies.h"
#include "util.h"
#include <nlohmann/json.hpp>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>

namespace dependencies {
const std::vector<Component>& catalog() {
    static const std::vector<Component> list = {
        {"vcrun2005", "Visual C++ 2005", "Visual C++", "Runtime for programs built with Visual C++ 2005."},
        {"vcrun2008", "Visual C++ 2008", "Visual C++", "Runtime for programs built with Visual C++ 2008."},
        {"vcrun2010", "Visual C++ 2010", "Visual C++", "Runtime for programs built with Visual C++ 2010."},
        {"vcrun2012", "Visual C++ 2012", "Visual C++", "Runtime for programs built with Visual C++ 2012."},
        {"vcrun2013", "Visual C++ 2013", "Visual C++", "Runtime for programs built with Visual C++ 2013."},
        {"vcrun2015", "Visual C++ 2015", "Visual C++", "Choose the version your app requires; 2015 and newer runtimes can replace each other."},
        {"vcrun2017", "Visual C++ 2017", "Visual C++", "Choose the version your app requires; 2015 and newer runtimes can replace each other."},
        {"vcrun2019", "Visual C++ 2019", "Visual C++", "Choose the version your app requires; 2015 and newer runtimes can replace each other."},
        {"vcrun2022", "Visual C++ 2015-2022", "Visual C++", "Common modern C++ runtime. Can replace older 2015+ redistributables."},
        {"vcrun2026", "Visual C++ 2015-2026", "Visual C++", "Latest C++ runtime, when supported by this Proton's Winetricks."},
        {"dotnet35sp1", ".NET Framework 3.5 SP1", ".NET", "For older .NET applications. Installation can take several minutes."},
        {"dotnet48", ".NET Framework 4.8", ".NET", "Microsoft Framework for apps requiring it; replaces Wine Mono."},
        {"dotnetdesktop6", ".NET Desktop Runtime 6", ".NET", "Windows desktop runtime for .NET 6 apps."},
        {"dotnetdesktop8", ".NET Desktop Runtime 8", ".NET", "Windows desktop runtime for .NET 8 apps."},
        {"dotnetdesktop9", ".NET Desktop Runtime 9", ".NET", "Windows desktop runtime for .NET 9 apps."},
        {"dotnetdesktop10", ".NET Desktop Runtime 10", ".NET", "Windows desktop runtime for .NET 10 apps."},
        {"corefonts", "Microsoft core fonts", "Fonts", "Arial, Times New Roman, Courier New and other core fonts."},
        {"tahoma", "Tahoma", "Fonts", "Tahoma font used by many Windows applications."},
        {"liberation", "Liberation fonts", "Fonts", "Free fonts with metrics compatible with common Microsoft fonts."},
        {"d3dx9", "DirectX 9 helper libraries", "Graphics & audio", "Legacy D3DX9 libraries required by some games."},
        {"d3dx10", "DirectX 10 helper libraries", "Graphics & audio", "Legacy D3DX10 libraries."},
        {"d3dx11_43", "DirectX 11 helper library", "Graphics & audio", "D3DX11_43 from the June 2010 DirectX runtime."},
        {"d3dcompiler_43", "Direct3D compiler 43", "Graphics & audio", "Legacy shader compiler DLL."},
        {"d3dcompiler_47", "Direct3D compiler 47", "Graphics & audio", "Shader compiler DLL required by some applications."},
        {"xact", "XACT audio", "Graphics & audio", "Microsoft XACT engine and supporting audio libraries."},
        {"xinput", "XInput", "Graphics & audio", "Legacy Microsoft controller input libraries."},
        {"gdiplus", "GDI+", "Windows libraries", "Microsoft GDI+ graphics library."},
        {"msxml6", "MSXML 6", "Windows libraries", "Microsoft XML services for applications requiring MSXML 6."},
    };
    return list;
}
namespace {
std::string result_path(const std::string& prefix) { return prefix + "/.xetalproton-dependencies.json"; }
std::map<std::string, std::string> failures(const std::string& prefix) {
    std::string text;
    if (!std::filesystem::exists(result_path(prefix))) return {};
    if (!util::read_file(result_path(prefix), text)) throw std::runtime_error("Cannot read dependency installation results");
    return nlohmann::json::parse(text).get<std::map<std::string, std::string>>();
}
}
Status status(const std::string& prefix) {
    Status result;
    if (prefix.empty()) return result;
    // Proton's compatdata directory is the parent; Wine's actual prefix is pfx/.
    const auto path = prefix + "/pfx/winetricks.log";
    if (std::filesystem::exists(path)) {
        std::ifstream file(path);
        if (!file) throw std::runtime_error("Cannot read this prefix's Winetricks records");
        std::string line;
        while (std::getline(file, line)) {
            line = util::trim(line);
            if (!line.empty() && line.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789_") == std::string::npos)
                result.installed.insert(line);
        }
        if (!file.eof()) throw std::runtime_error("Cannot read complete Winetricks records");
    }
    result.failures = failures(prefix);
    for (const auto& [verb, error] : result.failures) result.installed.erase(verb);
    return result;
}
std::set<std::string> available(const ProtonVersion& proton) {
    std::ifstream file(proton.dir + "/protonfixes/winetricks");
    std::set<std::string> result;
    std::string line, token, verb;
    while (std::getline(file, line)) {
        std::istringstream words(line);
        if (words >> token >> verb && token == "w_metadata") result.insert(verb);
    }
    return result;
}
LaunchSpec build_install(const ProtonVersion& proton, const std::string& prefix, const std::string& verb, bool retry) {
    LaunchSpec error;
    bool known = false;
    for (const auto& component : catalog()) if (component.verb == verb) known = true;
    if (!known) { error.error = "Unknown dependency"; return error; }
    if (!available(proton).contains(verb)) {
        error.error = "This Proton's bundled Winetricks does not support this component. Choose a newer Proton-GE or UMU-Proton in Library.";
        return error;
    }
    // Protonfixes dispatches native Winetricks only for waitforexitandrun.
    auto spec = build_launch(proton, prefix, "winetricks", (retry ? "--force " : "") + verb, "waitforexitandrun", true, {}, "", util::home_dir(), "Install " + verb);
    spec.exclusive_prefix = true;
    spec.env["W_CACHE"] = util::data_dir() + "/cache/winetricks";
    spec.env["XDG_CONFIG_HOME"] = util::config_dir();
    spec.env["WINETRICKS_POST"] = util::data_dir() + "/winetricks/postinstall";
    spec.env["WINETRICKS_AUTH"] = util::data_dir() + "/winetricks/auth";
    spec.env["WINETRICKS_LATEST_VERSION_CHECK"] = "disabled";
    spec.env["WINETRICKS_GUI"] = "none";
    // A runtime should not inherit host overrides that can change the installer.
    spec.env["WINE"] = ""; spec.env["WINESERVER"] = ""; spec.env["WINEARCH"] = "";
    spec.env["WINETRICKS_DOWNLOADER_RETRIES"] = "3";
    return spec;
}
void record_result(const std::string& prefix, const std::string& verb, const std::string& error) {
    auto result = failures(prefix);
    if (error.empty()) result.erase(verb); else result[verb] = error;
    if (!util::write_file(result_path(prefix), nlohmann::json(result).dump(2)))
        throw std::runtime_error("Cannot save dependency installation result");
}
bool busy(const std::string& prefix) {
    if (prefix.empty() || !std::filesystem::exists(prefix + "/.xetalproton.lock")) return false;
    const int fd = open((prefix + "/.xetalproton.lock").c_str(), O_RDWR | O_CLOEXEC);
    if (fd < 0) return true;
    const bool locked = flock(fd, LOCK_EX | LOCK_NB) != 0;
    close(fd);
    return locked;
}
}

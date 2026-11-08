#pragma once
#include <string>
#include <vector>
#include <map>

struct Shortcut {
    std::string id;         // unique id
    std::string name;
    std::string exe;        // linux path to the .exe / .msi / .bat
    std::string args;
    std::string workdir;    // empty = exe dir
    std::string prefix;     // prefix path (folder that contains pfx/)
    std::string proton;     // proton dir override, "" = prefix default
    std::string verb = "run";   // run | waitforexitandrun | runinprefix
    bool use_runtime = true;    // use UMU's independently managed runtime
    std::map<std::string, std::string> env;  // option key -> value ("1" for bools); keys starting with '@' are wrappers
    std::string custom_env;     // free text KEY=VALUE per line
    std::string icon_override;  // optional path to png/ico
};

struct CustomPrefix {
    std::string name;
    std::string path;
};

struct Config {
    std::string prefixes_root;                    // where new prefixes get created
    std::vector<CustomPrefix> prefixes;
    std::vector<Shortcut> shortcuts;
    std::map<std::string, std::string> prefix_proton;  // prefix path -> proton dir
    std::string last_prefix;
    float ui_scale = 1.0f;
    int icon_size = 64;
    bool discover_steam = false; // optional access to existing Steam installations
};

std::string config_path();
Config load_config();
bool save_config(const Config& c);
std::string new_id();

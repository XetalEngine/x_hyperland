#pragma once
#include <string>
#include <vector>
#include <map>

// Minimal text-VDF node (libraryfolders.vdf, appmanifest_*.acf, compatibilitytool.vdf)
struct VdfNode {
    std::map<std::string, std::string> values;
    std::map<std::string, VdfNode> children;
    const VdfNode* child(const std::string& k) const { auto it = children.find(k); return it == children.end() ? nullptr : &it->second; }
    std::string value(const std::string& k, const std::string& def = "") const { auto it = values.find(k); return it == values.end() ? def : it->second; }
};
bool parse_vdf_text(const std::string& text, VdfNode& root);

struct ProtonVersion {
    std::string name;          // display name, e.g. "Proton - Experimental"
    std::string dir;           // directory containing the "proton" script
    std::string version;       // contents of the "version" file (2nd token)
    std::string prefix_version; // CURRENT_PREFIX_VERSION inside the proton script, matches compatdata/<id>/version
    std::string runtime_dir;   // Steam Linux Runtime dir with _v2-entry-point, may be empty
    std::string runtime_name;
    std::string source;        // "steam" or "custom"
    std::string script() const { return dir + "/proton"; }
};

struct SteamPrefix {
    std::string name;          // resolved app / shortcut name
    std::string appid;
    std::string path;          // .../steamapps/compatdata/<appid>
    std::string version_hint;  // contents of compatdata/<id>/version
};

struct SteamInfo {
    std::string root;                        // ~/.local/share/Steam (resolved)
    std::vector<std::string> libraries;      // all steam library roots (each contains steamapps/)
    std::vector<ProtonVersion> protons;
    std::vector<SteamPrefix> prefixes;
    std::map<std::string, std::string> runtime_by_appid; // appid -> dir
};

SteamInfo scan_steam();
SteamInfo scan_installations(bool include_steam = false);
const ProtonVersion* find_proton(const SteamInfo& s, const std::string& dir);
// Best guess of which installed proton last touched a prefix (matches the "version" file)
const ProtonVersion* guess_proton_for_prefix(const SteamInfo& s, const std::string& version_hint);

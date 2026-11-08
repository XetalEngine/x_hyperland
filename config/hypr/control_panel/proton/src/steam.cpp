#include "steam.h"
#include "util.h"
#include "tools.h"
#include <algorithm>
#include <cstring>
#include <set>

// ---------------- text VDF ----------------
namespace {
struct Tok { std::string s; bool brace_open = false, brace_close = false, eof = false; };
struct Lexer {
    const std::string& t; size_t i = 0;
    explicit Lexer(const std::string& s) : t(s) {}
    Tok next() {
        for (;;) {
            while (i < t.size() && isspace((unsigned char)t[i])) i++;
            if (i >= t.size()) { Tok e; e.eof = true; return e; }
            if (t[i] == '/' && i + 1 < t.size() && t[i+1] == '/') { while (i < t.size() && t[i] != '\n') i++; continue; }
            break;
        }
        Tok k;
        if (t[i] == '{') { i++; k.brace_open = true; return k; }
        if (t[i] == '}') { i++; k.brace_close = true; return k; }
        if (t[i] == '"') {
            i++;
            while (i < t.size() && t[i] != '"') { if (t[i] == '\\' && i + 1 < t.size()) i++; k.s += t[i++]; }
            i++;
            return k;
        }
        while (i < t.size() && !isspace((unsigned char)t[i]) && t[i] != '{' && t[i] != '}') k.s += t[i++];
        return k;
    }
};
void parse_block(Lexer& lx, VdfNode& node) {
    for (;;) {
        Tok k = lx.next();
        if (k.eof || k.brace_close) return;
        if (k.brace_open) continue;
        Tok v = lx.next();
        if (v.eof) return;
        if (v.brace_open) { parse_block(lx, node.children[k.s]); }
        else if (v.brace_close) { node.values[k.s] = ""; return; }
        else node.values[k.s] = v.s;
    }
}
}
bool parse_vdf_text(const std::string& text, VdfNode& root) {
    Lexer lx(text); parse_block(lx, root); return true;
}

// ---------------- binary VDF (shortcuts.vdf) ----------------
// We only need: for each shortcut, "appid" (int32, treated as uint32) and "AppName".
static void parse_shortcuts_vdf(const std::string& path, std::map<std::string, std::string>& out) {
    std::vector<uint8_t> d;
    if (!util::read_file_bytes(path, d)) return;
    size_t i = 0;
    auto read_str = [&](std::string& s) { s.clear(); while (i < d.size() && d[i] != 0) s += (char)d[i++]; if (i < d.size()) i++; };
    // Walk recursively; track current shortcut's appid/name at depth 2.
    struct Frame { std::string appid, name; };
    std::vector<Frame> stack;
    while (i < d.size()) {
        uint8_t type = d[i++];
        if (type == 0x08) {
            if (!stack.empty()) {
                Frame f = stack.back(); stack.pop_back();
                if (stack.size() == 1 && !f.appid.empty()) out[f.appid] = f.name.empty() ? ("Shortcut " + f.appid) : f.name;
            }
            continue;
        }
        std::string key; read_str(key);
        if (type == 0x00) { stack.push_back({}); continue; }
        if (type == 0x01) {
            std::string val; read_str(val);
            if (!stack.empty() && util::lower(key) == "appname") stack.back().name = val;
        } else if (type == 0x02 || type == 0x03 || type == 0x04 || type == 0x06) {
            if (i + 4 > d.size()) break;
            uint32_t v; memcpy(&v, &d[i], 4); i += 4;
            if (!stack.empty() && util::lower(key) == "appid" && type == 0x02) stack.back().appid = std::to_string(v);
        } else if (type == 0x07) { i += 8; }
        else if (type == 0x05) { i += 8; }   // wide string, unlikely; skip conservatively
        else break;
    }
}

// ---------------- scanning ----------------
static std::string read_version_file(const std::string& dir) {
    std::string v;
    if (!util::read_file(dir + "/version", v)) return "";
    v = util::trim(v);
    auto sp = v.find(' ');
    return sp == std::string::npos ? v : util::trim(v.substr(sp + 1));
}

static void add_proton_dir(SteamInfo& info, const std::string& dir, const std::string& source, std::set<std::string>& seen) {
    if (!util::file_exists(dir + "/proton")) return;
    std::string canon = dir;
    if (seen.count(canon)) return;
    seen.insert(canon);
    ProtonVersion p;
    p.dir = dir; p.source = source;
    p.name = util::basename(dir);
    std::string ct;
    if (util::read_file(dir + "/compatibilitytool.vdf", ct)) {
        VdfNode root; parse_vdf_text(ct, root);
        if (auto* ctn = root.child("compatibilitytools")) if (auto* ct2 = ctn->child("compat_tools"))
            for (auto& [k, v] : ct2->children) { std::string dn = v.value("display_name"); if (!dn.empty()) { p.name = dn; break; } }
    }
    p.version = read_version_file(dir);
    {
        std::string script;
        if (util::read_file(dir + "/proton", script)) {
            const char* key = "CURRENT_PREFIX_VERSION=\"";
            auto at = script.find(key);
            if (at != std::string::npos) { at += strlen(key); auto end = script.find('"', at); if (end != std::string::npos) p.prefix_version = script.substr(at, end - at); }
        }
    }
    std::string tm;
    if (util::read_file(dir + "/toolmanifest.vdf", tm)) {
        VdfNode root; parse_vdf_text(tm, root);
        if (auto* m = root.child("manifest")) {
            std::string req = m->value("require_tool_appid");
            auto it = info.runtime_by_appid.find(req);
            if (it != info.runtime_by_appid.end()) { p.runtime_dir = it->second; p.runtime_name = util::basename(it->second); }
        }
    }
    info.protons.push_back(p);
}

SteamInfo scan_steam() {
    SteamInfo info;
    std::string home = util::home_dir();
    for (const std::string& cand : { home + "/.local/share/Steam", home + "/.steam/root", home + "/.steam/steam",
                                     home + "/.var/app/com.valvesoftware.Steam/.local/share/Steam", home + "/.steam/debian-installation" }) {
        if (util::dir_exists(cand + "/steamapps")) { char buf[4096]; const char* r = realpath(cand.c_str(), buf); info.root = r ? r : cand; break; }
    }
    if (info.root.empty()) return info;

    // libraries
    std::set<std::string> libs; libs.insert(info.root);
    std::string lf;
    if (util::read_file(info.root + "/steamapps/libraryfolders.vdf", lf) || util::read_file(info.root + "/config/libraryfolders.vdf", lf)) {
        VdfNode root; parse_vdf_text(lf, root);
        if (auto* l = root.child("libraryfolders"))
            for (auto& [k, v] : l->children) { std::string p = v.value("path"); if (!p.empty() && util::dir_exists(p + "/steamapps")) libs.insert(p); }
    }
    info.libraries.assign(libs.begin(), libs.end());

    // app manifests: appid -> (name, installdir, library)
    struct AppInfo { std::string name, installdir, library; };
    std::map<std::string, AppInfo> apps;
    for (auto& lib : info.libraries) {
        for (auto& f : util::list_dir(lib + "/steamapps")) {
            std::string bn = util::basename(f);
            if (bn.rfind("appmanifest_", 0) != 0 || !util::ends_with_ci(bn, ".acf")) continue;
            std::string txt; if (!util::read_file(f, txt)) continue;
            VdfNode root; parse_vdf_text(txt, root);
            auto* a = root.child("AppState"); if (!a) continue;
            std::string id = a->value("appid"); if (id.empty()) id = bn.substr(12, bn.size() - 16);
            apps[id] = { a->value("name"), a->value("installdir"), lib };
        }
    }
    // runtimes
    for (auto& [id, a] : apps) {
        std::string d = a.library + "/steamapps/common/" + a.installdir;
        if (util::file_exists(d + "/_v2-entry-point")) info.runtime_by_appid[id] = d;
    }
    // protons
    std::set<std::string> seen;
    for (auto& [id, a] : apps) {
        std::string d = a.library + "/steamapps/common/" + a.installdir;
        add_proton_dir(info, d, "steam", seen);
    }
    for (auto& lib : info.libraries)
        for (auto& d : util::list_dir(lib + "/steamapps/common", true)) add_proton_dir(info, d, "steam", seen);
    for (const std::string& ctd : { info.root + "/compatibilitytools.d", home + "/.steam/root/compatibilitytools.d", home + "/.local/share/Steam/compatibilitytools.d" })
        for (auto& d : util::list_dir(ctd, true)) add_proton_dir(info, d, "custom", seen);
    std::sort(info.protons.begin(), info.protons.end(), [](const ProtonVersion& a, const ProtonVersion& b) {
        if (a.source != b.source) return a.source == "steam";
        return util::lower(a.name) < util::lower(b.name);
    });

    // shortcut names
    std::map<std::string, std::string> shortcut_names;
    for (auto& ud : util::list_dir(info.root + "/userdata", true)) parse_shortcuts_vdf(ud + "/config/shortcuts.vdf", shortcut_names);

    // prefixes
    for (auto& lib : info.libraries) {
        for (auto& d : util::list_dir(lib + "/steamapps/compatdata", true)) {
            if (!util::dir_exists(d + "/pfx")) continue;
            SteamPrefix p; p.appid = util::basename(d); p.path = d;
            if (auto it = apps.find(p.appid); it != apps.end() && !it->second.name.empty()) p.name = it->second.name;
            else if (auto it2 = shortcut_names.find(p.appid); it2 != shortcut_names.end()) p.name = it2->second + " (non-Steam)";
            else p.name = "App " + p.appid;
            p.version_hint = read_version_file(d);
            info.prefixes.push_back(p);
        }
    }
    std::sort(info.prefixes.begin(), info.prefixes.end(), [](const SteamPrefix& a, const SteamPrefix& b) { return util::lower(a.name) < util::lower(b.name); });
    return info;
}

SteamInfo scan_installations(bool include_steam) {
    SteamInfo info = include_steam ? scan_steam() : SteamInfo{};
    std::vector<ProtonVersion> external = std::move(info.protons);
    std::set<std::string> seen;
    for (const auto& tool : toolstore::installed()) {
        if (tool.kind != toolstore::Kind::Proton) continue;
        add_proton_dir(info, util::dirname(tool.entrypoint), "XetalProton", seen);
        if (!info.protons.empty()) {
            info.protons.back().runtime_dir.clear();
            info.protons.back().runtime_name = "UMU (managed by XetalProton)";
        }
    }
    info.protons.insert(info.protons.end(), external.begin(), external.end());
    return info;
}

const ProtonVersion* find_proton(const SteamInfo& s, const std::string& dir) {
    for (auto& p : s.protons) if (p.dir == dir) return &p;
    return nullptr;
}
const ProtonVersion* guess_proton_for_prefix(const SteamInfo& s, const std::string& hint) {
    if (hint.empty()) return nullptr;
    for (auto& p : s.protons) if (!p.prefix_version.empty() && p.prefix_version == hint) return &p;
    for (auto& p : s.protons) if (!p.version.empty() && p.version == hint) return &p;
    // loose match on the major version ("11.0-100" -> "11.0"), preferring Experimental
    auto dash = hint.find('-');
    std::string stem = dash == std::string::npos ? hint : hint.substr(0, dash);
    const ProtonVersion* best = nullptr;
    for (auto& p : s.protons) {
        std::string pv = p.prefix_version.empty() ? p.version : p.prefix_version;
        if (pv.rfind(stem, 0) != 0 && p.version.find(stem) == std::string::npos) continue;
        if (!best || p.name.find("Experimental") != std::string::npos) best = &p;
    }
    return best;
}

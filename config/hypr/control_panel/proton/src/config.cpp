#include "config.h"
#include "util.h"
#include <nlohmann/json.hpp>
#include <random>
#include <chrono>
#include <unistd.h>

using json = nlohmann::json;

std::string config_path() { return util::config_dir() + "/config.json"; }

std::string new_id() {
    static std::mt19937_64 rng((uint64_t)std::chrono::steady_clock::now().time_since_epoch().count() ^ (uint64_t)getpid());
    char buf[32]; snprintf(buf, sizeof buf, "%016llx", (unsigned long long)rng()); return buf;
}

static std::string gs(const json& j, const char* k, const std::string& def = "") {
    auto it = j.find(k); return (it != j.end() && it->is_string()) ? it->get<std::string>() : def;
}

Config load_config() {
    Config c;
    c.prefixes_root = util::data_dir() + "/prefixes";
    std::string txt;
    if (!util::read_file(config_path(), txt)) return c;
    json j = json::parse(txt, nullptr, false);
    if (j.is_discarded() || !j.is_object()) return c;
    c.prefixes_root = gs(j, "prefixes_root", c.prefixes_root);
    c.last_prefix = gs(j, "last_prefix");
    if (j.contains("discover_steam") && j["discover_steam"].is_boolean()) c.discover_steam = j["discover_steam"].get<bool>();
    if (j.contains("ui_scale") && j["ui_scale"].is_number()) c.ui_scale = j["ui_scale"].get<float>();
    if (j.contains("icon_size") && j["icon_size"].is_number()) c.icon_size = j["icon_size"].get<int>();
    if (j.contains("prefixes") && j["prefixes"].is_array())
        for (auto& p : j["prefixes"]) c.prefixes.push_back({ gs(p, "name"), gs(p, "path") });
    if (j.contains("prefix_proton") && j["prefix_proton"].is_object())
        for (auto& [k, v] : j["prefix_proton"].items()) if (v.is_string()) c.prefix_proton[k] = v.get<std::string>();
    if (j.contains("shortcuts") && j["shortcuts"].is_array()) {
        for (auto& s : j["shortcuts"]) {
            Shortcut sc;
            sc.id = gs(s, "id", new_id()); sc.name = gs(s, "name"); sc.exe = gs(s, "exe"); sc.args = gs(s, "args");
            sc.workdir = gs(s, "workdir"); sc.prefix = gs(s, "prefix"); sc.proton = gs(s, "proton");
            sc.verb = gs(s, "verb", "run"); sc.custom_env = gs(s, "custom_env"); sc.icon_override = gs(s, "icon_override");
            if (s.contains("use_runtime") && s["use_runtime"].is_boolean()) sc.use_runtime = s["use_runtime"].get<bool>();
            if (s.contains("desktop_integration") && s["desktop_integration"].is_object()) {
                const auto &d=s["desktop_integration"];
                sc.desktop.schemes=gs(d,"schemes"); sc.desktop.argument=gs(d,"argument","{url}");
                for (auto [key,value]:std::initializer_list<std::pair<const char *,bool *>>{
                    {"enabled",&sc.desktop.enabled},{"include_args",&sc.desktop.include_args},
                    {"make_default",&sc.desktop.make_default},{"private_output",&sc.desktop.private_output}})
                    if(d.contains(key) && d[key].is_boolean()) *value=d[key].get<bool>();
            }
            if (s.contains("env") && s["env"].is_object())
                for (auto& [k, v] : s["env"].items()) if (v.is_string()) sc.env[k] = v.get<std::string>();
            c.shortcuts.push_back(sc);
        }
    }
    return c;
}

bool save_config(const Config& c) {
    json j;
    j["prefixes_root"] = c.prefixes_root;
    j["last_prefix"] = c.last_prefix;
    j["ui_scale"] = c.ui_scale;
    j["icon_size"] = c.icon_size;
    j["discover_steam"] = c.discover_steam;
    j["prefixes"] = json::array();
    for (auto& p : c.prefixes) j["prefixes"].push_back({ {"name", p.name}, {"path", p.path} });
    j["prefix_proton"] = json::object();
    for (auto& [k, v] : c.prefix_proton) j["prefix_proton"][k] = v;
    j["shortcuts"] = json::array();
    for (auto& s : c.shortcuts) {
        json e = json::object();
        for (auto& [k, v] : s.env) if (!v.empty()) e[k] = v;
        j["shortcuts"].push_back({ {"id", s.id}, {"name", s.name}, {"exe", s.exe}, {"args", s.args}, {"workdir", s.workdir},
            {"prefix", s.prefix}, {"proton", s.proton}, {"verb", s.verb}, {"use_runtime", s.use_runtime}, {"env", e},
            {"custom_env", s.custom_env}, {"icon_override", s.icon_override},
            {"desktop_integration", {{"enabled",s.desktop.enabled},{"schemes",s.desktop.schemes},
                {"argument",s.desktop.argument},{"include_args",s.desktop.include_args},
                {"make_default",s.desktop.make_default},{"private_output",s.desktop.private_output}}} });
    }
    return util::write_file(config_path(), j.dump(2));
}

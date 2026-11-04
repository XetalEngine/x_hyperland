// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../effects/window_close/native/policies.hpp"
#include <fnmatch.h>
#include <optional>
#include <vector>
namespace WindowRules {
struct ButtonRule { std::string app, title; WindowButtons::Rule controls; };
using ButtonRules = std::vector<ButtonRule>;
inline ButtonRules read(const std::filesystem::path& path) {
    using namespace WindowButtons;
    if (!std::filesystem::exists(path)) return {};
    if (std::filesystem::file_size(path)>1024*1024) throw std::runtime_error("Window rules file is too large");
    std::ifstream file(path); std::string text((std::istreambuf_iterator<char>(file)),{});
    auto document=parseJson(text); auto rows=field(document.get(),"rules",json_type_array);
    if (json_object_get_int64(field(document.get(),"version",json_type_int))!=1 || json_object_array_length(rows)>256)
        throw std::runtime_error("Invalid window rules document");
    ButtonRules result;
    for (size_t i=0;i<json_object_array_length(rows);++i) {
        auto item=json_object_array_get_idx(rows,i);
        if (!json_object_get_boolean(field(item,"enabled",json_type_boolean))) continue;
        json_object* controls=nullptr;
        if (!json_object_object_get_ex(item,"controls",&controls) || !controls || json_object_is_type(controls,json_type_null)) continue;
        std::string app=json_object_get_string(field(item,"app",json_type_string));
        std::string title=json_object_get_string(field(item,"title",json_type_string));
        if(app.empty()||app.size()>256||title.size()>256)throw std::runtime_error("Invalid window match");
        result.push_back({app,title,readRule(controls)});
    }
    return result;
}
inline std::optional<WindowButtons::Rule> effective(const ButtonRules& rules,const std::string& app,const std::string& title) {
    for(auto i=rules.rbegin();i!=rules.rend();++i)
        if(fnmatch(i->app.c_str(),app.c_str(),FNM_NOESCAPE)==0 &&
           (i->title.empty()||fnmatch(i->title.c_str(),title.c_str(),FNM_NOESCAPE)==0))return i->controls;
    return {};
}
}

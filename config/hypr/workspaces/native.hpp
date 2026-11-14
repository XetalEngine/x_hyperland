// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstdlib>
#include <cstdint>
#include "../effects/window_close/native/policies.hpp"

namespace WorkspaceRules {
struct Policy {std::string layout="off",controls="individual";WindowButtons::Rule rule;};
inline bool floats(const Policy& p){return p.layout=="floating"||p.layout=="kde";}
struct Policies {std::map<int64_t,Policy> workspaces;std::string defaultLayout="off";};
inline std::filesystem::path path(){return std::filesystem::path(std::getenv("HOME"))/".config/hypr/workspaces/rules.json";}
inline Policies read(const std::filesystem::path& source=path()){
    if(!std::filesystem::exists(source))return {};
    if(std::filesystem::file_size(source)>1024*1024)throw std::runtime_error("Workspace rules file is too large");
    std::ifstream file(source);std::string text((std::istreambuf_iterator<char>(file)),{});
    using namespace WindowButtons;auto doc=parseJson(text);
    json_object* defaultLayout=nullptr;
    const bool hasDefault=json_object_object_get_ex(doc.get(),"default_layout",&defaultLayout);
    if(json_object_object_length(doc.get())!=2+int(hasDefault)||json_object_get_int64(field(doc.get(),"version",json_type_int))!=1)
        throw std::runtime_error("Unsupported workspace rules file");
    auto entries=field(doc.get(),"workspaces",json_type_object);
    if(json_object_object_length(entries)>512)throw std::runtime_error("Too many workspace rules");
    Policies result;
    if(hasDefault){
        result.defaultLayout=json_object_get_string(field(doc.get(),"default_layout",json_type_string));
        if(!std::set<std::string>{"off","tile","floating","kde"}.contains(result.defaultLayout))throw std::runtime_error("Invalid default workspace mode");
    }
    json_object_object_foreach(entries,key,value){
        std::string id=key;
        if(id.empty()||id.size()>10||id[0]=='0'||!std::ranges::all_of(id,[](char c){return c>='0'&&c<='9';}))throw std::runtime_error("Invalid workspace number");
        auto number=std::stoll(id);if(number>2147483647)throw std::runtime_error("Invalid workspace number");
        if(!json_object_is_type(value,json_type_object)||json_object_object_length(value)!=3)throw std::runtime_error("Incomplete workspace rule");
        Policy p;
        p.layout=json_object_get_string(field(value,"layout",json_type_string));
        p.controls=json_object_get_string(field(value,"controls",json_type_string));
        p.rule=readRule(field(value,"rule",json_type_object));
        if(!std::set<std::string>{"off","tile","floating","kde"}.contains(p.layout)||
           !std::set<std::string>{"individual","on","off"}.contains(p.controls)||p.rule.mode!="always")throw std::runtime_error("Invalid workspace mode");
        result.workspaces.emplace(number,p);
    }
    return result;
}
inline Policy forWorkspace(const Policies& policies,int64_t id){
    // Special workspaces (including the minimize stash) retain native behavior.
    if(id<1)return {};
    auto it=policies.workspaces.find(id);
    if(it!=policies.workspaces.end())return it->second;
    Policy fallback;fallback.layout=policies.defaultLayout;return fallback;
}
inline bool needsControls(const Policies& policies){
    return policies.defaultLayout=="kde"||std::ranges::any_of(policies.workspaces,[](const auto& entry){
        return entry.second.controls=="on"||entry.second.layout=="kde";
    });
}
}

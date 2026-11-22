// SPDX-License-Identifier: GPL-2.0-or-later
// Read optional caps without replacing any saved Compiz preferences.
#pragma once
#include <json-c/json.h>
#include <filesystem>
#include <fstream>
#include <memory>
#include <ctime>
#include <algorithm>
#include <cstdlib>
#include <string>
#include <csignal>
namespace FusionVisuals {
struct Policy {bool lightweight=false,hover=false;int fps=144,width=360;};
inline Policy read(const std::filesystem::path& root){
    Policy result;
    // Quality profiles and enlarged hover previews are parked. Do not impose
    // hidden caps on the user's existing Compiz effect settings.
    constexpr bool experimentalVisuals=false;
    if(!experimentalVisuals)return result;
    using Json=std::unique_ptr<json_object,decltype(&json_object_put)>;
    auto parse=[](const std::filesystem::path& path)->Json{
        std::ifstream in(path);if(!in)return Json(nullptr,json_object_put);
        std::string text(262145,'\0');in.read(text.data(),text.size());text.resize(in.gcount());
        if(text.size()>262144)return Json(nullptr,json_object_put);
        return Json(json_tokener_parse(text.c_str()),json_object_put);
    };
    Json saved=parse(root/"visuals/settings.json"),lease(nullptr,json_object_put);
    json_object* settings=saved.get();
    const char* runtime=std::getenv("XDG_RUNTIME_DIR"),*signature=std::getenv("HYPRLAND_INSTANCE_SIGNATURE");
    if(runtime&&signature&&std::string(signature).find('/')==std::string::npos){
        lease=parse(std::filesystem::path(runtime)/"hypr"/signature/"fusion-visuals/preview.json");
        json_object *path=nullptr,*expires=nullptr,*values=nullptr,*pid=nullptr;
        if(lease&&json_object_object_get_ex(lease.get(),"root",&path)&&json_object_object_get_ex(lease.get(),"expires",&expires)&&
           json_object_object_get_ex(lease.get(),"settings",&values)&&json_object_is_type(path,json_type_string)&&json_object_get_string(path)==root.string()&&
           json_object_get_double(expires)>std::time(nullptr)&&json_object_object_get_ex(lease.get(),"pid",&pid)&&
           json_object_get_int(pid)>0&&kill(json_object_get_int(pid),0)==0)settings=values;
    }
    if(!settings||!json_object_is_type(settings,json_type_object))return result;
    json_object* value=nullptr;
    if(json_object_object_get_ex(settings,"quality",&value)&&json_object_is_type(value,json_type_string)){
        const std::string quality=json_object_get_string(value);
        result.lightweight=quality=="lightweight";
        result.fps=quality=="lightweight"?5:quality=="balanced"?20:quality=="full"?60:144;
    }
    if(json_object_object_get_ex(settings,"preview_size",&value)&&json_object_is_type(value,json_type_int))result.width=std::clamp(json_object_get_int(value),240,520);
    if(json_object_object_get_ex(settings,"hover_previews",&value)&&json_object_is_type(value,json_type_boolean))result.hover=json_object_get_boolean(value);
    return result;
}
}

// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <algorithm>
#include <json-c/json.h>
#include <filesystem>
#include <fstream>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <stdexcept>

namespace WindowButtons {
struct Rule {
    std::string mode="super",anchor="top-right",background="auto",backgroundColor="#20242b";
    int size=18,x=8,y=8,proximity=80;
};
using Rules=std::map<std::string,Rule>;
using Json=std::unique_ptr<json_object,decltype(&json_object_put)>;
inline Json json(json_object* p){return Json(p,json_object_put);}
inline json_object* field(json_object* object,const char* key,json_type type){
    json_object* value=nullptr;
    if(!json_object_object_get_ex(object,key,&value)||!json_object_is_type(value,type))throw std::runtime_error("Invalid window button rule field: "+std::string(key));
    return value;
}
inline Json parseJson(const std::string& text){
    auto tokener=json_tokener_new();json_tokener_set_flags(tokener,JSON_TOKENER_STRICT|JSON_TOKENER_VALIDATE_UTF8);
    auto doc=json(json_tokener_parse_ex(tokener,text.data(),text.size()));auto error=json_tokener_get_error(tokener);json_tokener_free(tokener);
    if(error!=json_tokener_success||!doc||!json_object_is_type(doc.get(),json_type_object))throw std::runtime_error("Invalid window button settings");
    return doc;
}
inline Rule readRule(json_object* value){
    if(!json_object_is_type(value,json_type_object)||(json_object_object_length(value)!=6&&json_object_object_length(value)!=8))throw std::runtime_error("Incomplete window button rule");
    Rule r;r.mode=json_object_get_string(field(value,"mode",json_type_string));r.anchor=json_object_get_string(field(value,"anchor",json_type_string));
    if(!std::set<std::string>{"super","always","nearby","off"}.contains(r.mode)||
       !std::set<std::string>{"top-left","top-center","top-right","bottom-left","bottom-center","bottom-right"}.contains(r.anchor))throw std::runtime_error("Unknown button display mode or position");
    auto number=[&](const char* key,int lo,int hi){auto n=json_object_get_int64(field(value,key,json_type_int));if(n<lo||n>hi)throw std::runtime_error("Button rule value out of range");return int(n);};
    r.size=number("size",10,64);r.x=number("x",0,4000);r.y=number("y",0,4000);r.proximity=number("proximity",12,400);
    if(json_object_object_length(value)==8){
        r.background=json_object_get_string(field(value,"background",json_type_string));
        auto color=field(value,"background_color",json_type_string);
        r.backgroundColor=std::string(json_object_get_string(color),json_object_get_string_len(color));
        if((r.background!="auto"&&r.background!="manual")||r.backgroundColor.size()!=7||r.backgroundColor[0]!='#'||
           !std::all_of(r.backgroundColor.begin()+1,r.backgroundColor.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f')||(c>='A'&&c<='F');}))
            throw std::runtime_error("Invalid window control background");
        std::transform(r.backgroundColor.begin(),r.backgroundColor.end(),r.backgroundColor.begin(),[](unsigned char c){return std::tolower(c);});
    }
    return r;
}
inline Rules readRules(const std::filesystem::path& path,const char* section){
    if(!std::filesystem::exists(path))return {};
    if(std::filesystem::file_size(path)>1024*1024)throw std::runtime_error("Window button rules file is too large");
    std::ifstream file(path);std::string text((std::istreambuf_iterator<char>(file)),{});
    auto doc=parseJson(text);
    if(json_object_object_length(doc.get())!=2||
       json_object_get_int64(field(doc.get(),"version",json_type_int))!=1)throw std::runtime_error("Invalid window button rules file");
    auto entries=field(doc.get(),section,json_type_object);
    if(json_object_object_length(entries)>512)throw std::runtime_error("Too many window button rules");
    Rules result;
    json_object_object_foreach(entries,key,value){
        std::string id=key;
        if(id.empty()||id.size()>512||std::ranges::any_of(id,[](unsigned char c){return c<32;}))throw std::runtime_error("Invalid window identity");
        if(std::string(section)=="windows"&&!std::ranges::all_of(id,[](char c){return c>='0'&&c<='9';}))throw std::runtime_error("Invalid window ID");
        result.emplace(id,readRule(value));
    }
    return result;
}
inline Json ruleJson(const Rule& r){
    auto result=json(json_object_new_object());
    json_object_object_add(result.get(),"mode",json_object_new_string(r.mode.c_str()));
    json_object_object_add(result.get(),"anchor",json_object_new_string(r.anchor.c_str()));
    json_object_object_add(result.get(),"background",json_object_new_string(r.background.c_str()));
    json_object_object_add(result.get(),"background_color",json_object_new_string(r.backgroundColor.c_str()));
    for(auto [key,value]:{std::pair{"size",r.size},{"x",r.x},{"y",r.y},{"proximity",r.proximity}})
        json_object_object_add(result.get(),key,json_object_new_int(value));
    return result;
}
inline std::string quoted(const std::string& text){auto object=json(json_object_new_string_len(text.data(),text.size()));return json_object_to_json_string_ext(object.get(),JSON_C_TO_STRING_PLAIN);}
}

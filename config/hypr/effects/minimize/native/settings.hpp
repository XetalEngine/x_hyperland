// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <array>
#include <algorithm>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
// Keep adapter definitions local across dlclose/dlopen upgrades. Hyprland's
// own headers must retain default visibility for their shared global state.
namespace Minimize __attribute__((visibility("hidden"))) {
inline const std::map<std::string,int> dockStyles{{"raw",0},{"modern",1},{"breakpoint",2},{"binaryknife",3},
    {"tidalglass",4},{"porcelainink",5},{"obsidianforge",6},{"candycloud",7},{"shadowedge",8},{"hollowgrove",9},{"gildedhollow",10},{"hyperfusionblue",11},{"midnighttransit",12},{"blackwood",13},{"atomicafterglow",14},{"mycelium",15},{"platform95",16},{"midnightrun",17},{"infernalencore",18}};
struct Settings {
    bool enabled=true, followTheme=true, rightEdge=false, bottomToTop=true;
    bool dock=true, autoHide=true;
    bool burnHide=false, fireIndicator=false;
    int duration=420, size=76, shape=-1, speed=100, bubbles=70, surface=0;
    int hideDelay=1200,dockDuration=320,proximity=12,dockZoom=125,dockStyle=-1;
    std::string dockEdge="auto";
    std::string effect="fireball", color="#39a9ff";
    std::array<float,3> rgb{.224F,.663F,1.F};
    std::array<float,3> background{.07F,.10F,.14F},light{.7F,.85F,.9F};
};
inline Settings readSettings(const std::filesystem::path& path, const std::filesystem::path& palette) {
    std::ifstream file(path);if(!file)throw std::runtime_error("Cannot read Minimize settings: "+path.string());
    Settings next;std::set<std::string> seen;std::string line;
    while(std::getline(file,line)) {
        if(line.empty() || line[0]=='#')continue;
        auto pos=line.find('=');if(pos==std::string::npos)throw std::runtime_error("Invalid Minimize setting");
        auto key=line.substr(0,pos),value=line.substr(pos+1);
        if(!seen.insert(key).second)throw std::runtime_error("Duplicate Minimize setting");
        if(key=="presentation"){
            if(value!="dock" && value!="stack")throw std::runtime_error("Unknown minimize presentation");
            next.dock=value=="dock";continue;
        }
        if(key=="dock_edge"){
            if(value!="auto" && value!="bottom" && value!="top" && value!="left" && value!="right")throw std::runtime_error("Unknown dock edge");
            next.dockEdge=value;continue;
        }
        if(key=="dock_style"){
            if(value!="follow" && !dockStyles.contains(value))throw std::runtime_error("Unknown dock design");
            next.dockStyle=value=="follow"?-1:dockStyles.at(value);continue;
        }
        if(key=="hide_animation"){
            if(value!="slide" && value!="burn")throw std::runtime_error("Unknown dock hide animation");
            next.burnHide=value=="burn";continue;
        }
        if(key=="edge") {
            if(value!="left" && value!="right")throw std::runtime_error("Unknown minimize edge");
            next.rightEdge=value=="right";continue;
        }
        if(key=="order") {
            if(value!="bottom-to-top" && value!="top-to-bottom")throw std::runtime_error("Unknown minimize order");
            next.bottomToTop=value=="bottom-to-top";continue;
        }
        if(key=="effect") {
            if(value!="fireball" && value!="splat")throw std::runtime_error("Unknown minimize effect");
            // Splat is intentionally disabled; retain its source/preferences.
            next.effect="fireball";continue;
        }
        if(key=="shape") {
            const std::map<std::string,int> shapes{{"random",-1},{"bloom",0},{"star",1},{"spill",2},{"claw",3},{"wide",4},{"coral",5},{"web",6},{"droplets",7}};
            if(!shapes.contains(value))throw std::runtime_error("Unknown Splat shape");
            next.shape=shapes.at(value);continue;
        }
        if(key=="surface") {
            const std::map<std::string,int> surfaces{{"slime",0},{"membrane",1},{"paint",2}};
            if(!surfaces.contains(value))throw std::runtime_error("Unknown Splat surface");
            next.surface=surfaces.at(value);continue;
        }
        if(key=="color") {
            if(value.size()!=7 || value[0]!='#' || value.substr(1).find_first_not_of("0123456789abcdefABCDEF")!=std::string::npos)
                throw std::runtime_error("Invalid Minimize color");
            next.color=value;continue;
        }
        size_t used=0;int n=std::stoi(value,&used);if(used!=value.size())throw std::runtime_error("Invalid Minimize value");
        if(key=="enabled" && (n==0 || n==1))next.enabled=n;
        else if(key=="follow_theme" && (n==0 || n==1))next.followTheme=n;
        else if(key=="auto_hide" && (n==0 || n==1))next.autoHide=n;
        else if(key=="fire_indicator" && (n==0 || n==1))next.fireIndicator=n;
        else if(key=="hide_delay" && n>=200 && n<=10000)next.hideDelay=n;
        else if(key=="dock_duration" && n>=100 && n<=1000)next.dockDuration=n;
        else if(key=="proximity" && n>=2 && n<=64)next.proximity=n;
        else if(key=="dock_zoom" && n>=100 && n<=150)next.dockZoom=n;
        else if(key=="duration" && n>=150 && n<=1200)next.duration=n;
        else if(key=="size" && n>=48 && n<=160)next.size=n;
        else if(key=="speed" && n>=25 && n<=200)next.speed=n;
        else if(key=="bubbles" && n>=0 && n<=100)next.bubbles=n;
        else throw std::runtime_error("Unknown or out-of-range Minimize setting: "+key);
    }
    const std::set<std::string> legacy{"enabled","effect","duration","size"};
    auto all=legacy;for(const auto* k:{"follow_theme","color","shape","speed","bubbles"})all.insert(k);
    auto previous=all;all.insert("surface");auto materials=all;all.insert("edge");all.insert("order");
    auto stack=all;
    for(const auto* k:{"presentation","dock_edge","dock_style","auto_hide","hide_delay","dock_duration","proximity","dock_zoom"})all.insert(k);
    auto slide=all;all.insert("hide_animation");all.insert("fire_indicator");
    if(seen!=legacy && seen!=previous && seen!=materials && seen!=stack && seen!=slide && seen!=all)throw std::runtime_error("Incomplete Minimize settings");
    if(!seen.contains("presentation"))next.dock=false;
    for(int i=0;i<3;++i)next.rgb[i]=std::stoi(next.color.substr(1+i*2,2),nullptr,16)/255.F;
    // Only our profile's palette, never KDE's shared color settings.
    {
        std::ifstream colors(palette);bool window=false;
        while(std::getline(colors,line)) {
            if(line.starts_with("ColorScheme=") && next.dockStyle<0){
                auto scheme=line.substr(12);std::ranges::transform(scheme,scheme.begin(),[](unsigned char c){return char(std::tolower(c));});
                for(const auto& [name,id]:dockStyles)if(scheme.starts_with("xetal"+name)){next.dockStyle=id;break;}
            }
            if(line.starts_with('[')){window=line=="[Colors:Window]";continue;}
            if(!window)continue;
            auto pos=line.find('=');if(pos==std::string::npos)continue;
            std::istringstream input(line.substr(pos+1));int r,g,b;char c,d;
            if(input>>r>>c>>g>>d>>b && c==',' && d==',' && r>=0 && r<=255 && g>=0 && g<=255 && b>=0 && b<=255){
                const std::array<float,3> rgb{r/255.F,g/255.F,b/255.F};
                const auto key=line.substr(0,pos);
                if(key=="DecorationFocus" && next.followTheme)next.rgb=rgb;
                else if(key=="BackgroundNormal")next.background=rgb;
                else if(key=="ForegroundNormal")next.light=rgb;
            }
        }
    }
    if(next.dockStyle<0)next.dockStyle=0;
    return next;
}
}

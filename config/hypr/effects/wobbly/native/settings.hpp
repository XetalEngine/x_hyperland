#pragma once
#include <json-c/json.h>
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#include <fnmatch.h>

namespace Wobbly {
inline const std::vector<std::string> types={"Normal","Dialog","Utility","Toolbar","Menu","Splash","DropdownMenu","PopupMenu","Tooltip","Notification","Combo","Dnd","Unknown","Dock","Desktop","Any"};
inline std::string trim(std::string s){auto a=s.find_first_not_of(" \t");return a==s.npos?"":s.substr(a,s.find_last_not_of(" \t")-a+1);}
struct WindowInfo {
    std::string type="Normal",app,title,role,state="normal";
    bool floating=false,xwayland=false,overrideRedirect=false,rgba=false;
    uint32_t xid=0;
};
class Match {
    struct Node {char op=0;std::string key,value;std::shared_ptr<Node> a,b;};
    std::shared_ptr<Node> root;
    std::vector<std::string> tokens;
    size_t pos=0;
    std::shared_ptr<Node> atom(int depth){
        if(depth>32||pos==tokens.size())throw std::runtime_error("Incomplete window match");
        auto s=tokens[pos++];
        if(s=="!")return std::make_shared<Node>(Node{'!',"","",atom(depth+1),{}});
        if(s=="("){auto n=expression(depth+1);if(pos==tokens.size()||tokens[pos++]!=")")throw std::runtime_error("Unclosed match group");return n;}
        auto n=std::make_shared<Node>();auto eq=s.find('=');
        n->key=eq==s.npos?"type":s.substr(0,eq);n->value=eq==s.npos?s:s.substr(eq+1);
        auto& k=n->key;auto& v=n->value;
        if(k=="type"){if(std::find(types.begin(),types.end(),v)==types.end())throw std::runtime_error("Unknown window type: "+v);}
        else if(k=="class"||k=="title"||k=="role"){if(v.empty())throw std::runtime_error("Empty match value");}
        else if(k=="floating"||k=="xwayland"||k=="override_redirect"||k=="rgba"){if(v!="0"&&v!="1")throw std::runtime_error("Match flag needs 0 or 1");}
        else if(k=="state"){if(v!="normal"&&v!="fullscreen"&&v!="maximized")throw std::runtime_error("Unknown window state");}
        else if(k=="xid"){
            size_t used=0;try{std::stoul(v,&used,0);}catch(...){throw std::runtime_error("Invalid X11 ID");}
            if(used!=v.size())throw std::runtime_error("Invalid X11 ID");
        }else throw std::runtime_error("Unknown window match: "+k);
        return n;
    }
    std::shared_ptr<Node> conjunction(int depth){
        auto n=atom(depth);while(pos<tokens.size()&&tokens[pos]=="&"){++pos;n=std::make_shared<Node>(Node{'&',"","",n,atom(depth)});}return n;
    }
    std::shared_ptr<Node> expression(int depth){
        auto n=conjunction(depth);while(pos<tokens.size()&&tokens[pos]=="|"){++pos;n=std::make_shared<Node>(Node{'|',"","",n,conjunction(depth)});}return n;
    }
    bool eval(const std::shared_ptr<Node>& n,const WindowInfo& w)const{
        if(!n)return false;
        if(n->op=='!')return !eval(n->a,w);
        if(n->op=='&')return eval(n->a,w)&&eval(n->b,w);
        if(n->op=='|')return eval(n->a,w)||eval(n->b,w);
        auto& k=n->key;auto& v=n->value;
        if(k=="type")return v=="Any"||v==w.type;
        if(k=="class")return fnmatch(v.c_str(),w.app.c_str(),0)==0;
        if(k=="title")return fnmatch(v.c_str(),w.title.c_str(),0)==0;
        if(k=="role")return fnmatch(v.c_str(),w.role.c_str(),0)==0;
        if(k=="state")return v==w.state;
        if(k=="xid")return w.xwayland&&std::stoul(v,nullptr,0)==w.xid;
        return (v=="1")== (k=="floating"?w.floating:k=="xwayland"?w.xwayland:k=="rgba"?w.rgba:w.overrideRedirect);
    }
  public:
    Match(const std::string& s=""){
        if(s.size()>1024||std::any_of(s.begin(),s.end(),[](unsigned char c){return c<32;}))throw std::runtime_error("Invalid window match");
        size_t begin=0;
        for(size_t i=0;i<=s.size();++i)if(i==s.size()||std::string("!&|()").find(s[i])!=std::string::npos){
            auto t=trim(s.substr(begin,i-begin));if(!t.empty())tokens.push_back(t);
            if(i<s.size())tokens.push_back(s.substr(i,1));
            begin=i+1;
        }
        if(!tokens.empty())root=expression(0);
        if(pos!=tokens.size())throw std::runtime_error("Invalid window match");
    }
    bool matches(const WindowInfo& w)const{return eval(root,w);}
};
struct Settings {
    bool enabled=false,snap_inverted=false,shiver=false,maximize_effect=true;
    double friction=3,spring_k=8;
    int grid_resolution=8,min_grid_size=8,map_effect=0,focus_effect=0;
    uint32_t snapModifiers=1;
    Match map_window_match{"Splash | DropdownMenu | PopupMenu | Tooltip | Notification | Combo | Dnd | Unknown"};
    Match focus_window_match,grab_window_match;
    Match move_window_match{"Toolbar | Menu | Utility | Dialog | Normal | Unknown"};
};
inline Settings readSettings(const std::filesystem::path& path){
    Settings s;if(!std::filesystem::exists(path))return s;
    std::ifstream f(path);std::string content((std::istreambuf_iterator<char>(f)),{});
    if(content.size()>32768)throw std::runtime_error("Wobbly settings are too large");
    std::unique_ptr<json_object,decltype(&json_object_put)> root(json_tokener_parse(content.c_str()),json_object_put);
    if(!root||!json_object_is_type(root.get(),json_type_object)||json_object_object_length(root.get())!=15)throw std::runtime_error("Invalid Wobbly settings");
    auto get=[&](const char* name,json_type type){json_object* v=nullptr;if(!json_object_object_get_ex(root.get(),name,&v)||!json_object_is_type(v,type))throw std::runtime_error(std::string("Invalid Wobbly option: ")+name);return v;};
    auto boolean=[&](const char* k){return bool(json_object_get_boolean(get(k,json_type_boolean)));};
    auto number=[&](const char* k,double lo,double hi,bool integer){
        json_object* v=nullptr;if(!json_object_object_get_ex(root.get(),k,&v)||(!json_object_is_type(v,json_type_int)&&!json_object_is_type(v,json_type_double)))throw std::runtime_error(std::string("Invalid number: ")+k);
        double n=json_object_get_double(v);if(!std::isfinite(n)||n<lo||n>hi||(integer&&std::floor(n)!=n))throw std::runtime_error(std::string("Out of range: ")+k);return n;};
    auto string=[&](const char* k){auto v=get(k,json_type_string);return std::string(json_object_get_string(v),json_object_get_string_len(v));};
    s.enabled=boolean("enabled");s.snap_inverted=boolean("snap_inverted");s.shiver=boolean("shiver");s.maximize_effect=boolean("maximize_effect");
    s.friction=number("friction",.1,10,false);s.spring_k=number("spring_k",.1,10,false);
    s.grid_resolution=number("grid_resolution",1,64,true);s.min_grid_size=number("min_grid_size",4,128,true);
    s.map_effect=number("map_effect",0,1,true);s.focus_effect=number("focus_effect",0,1,true);
    s.map_window_match=Match(string("map_window_match"));s.focus_window_match=Match(string("focus_window_match"));
    s.grab_window_match=Match(string("grab_window_match"));s.move_window_match=Match(string("move_window_match"));
    const std::vector<std::pair<std::string,uint32_t>> modifiers={{"Shift",1},{"Control",4},{"Alt",8},{"Super",64},{"Mod2",16},{"Mod3",32},{"Mod5",128}};
    auto key=string("snap_key");s.snapModifiers=0;
    while(!key.empty()){
        auto end=key.find('>');if(key[0]!='<'||end==key.npos)throw std::runtime_error("Invalid snap modifiers");
        auto part=key.substr(1,end-1);auto it=std::find_if(modifiers.begin(),modifiers.end(),[&](auto& m){return m.first==part;});
        if(it==modifiers.end()||(s.snapModifiers&it->second))throw std::runtime_error("Invalid snap modifiers");
        s.snapModifiers|=it->second;key.erase(0,end+1);
    }
    return s;
}
} // namespace Wobbly

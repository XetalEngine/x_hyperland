#include "dominant.hpp"
#include "policies.hpp"
#include <cassert>
#include <cmath>
#include <vector>
int main(){
    std::vector<uint8_t> pixels;
    for(int i=0;i<480;++i){
        // Similar toolbar shades form the dominant cluster; isolated bright
        // glyphs and fully transparent pixels must not change its average.
        const uint8_t shade=32+i%8;
        const std::array<uint8_t,4> p=i%5==0?std::array<uint8_t,4>{255,255,255,255}:
            i%7==0?std::array<uint8_t,4>{255,0,0,0}:std::array<uint8_t,4>{shade,48,64,255};
        pixels.insert(pixels.end(),p.begin(),p.end());
    }
    auto color=WindowButtons::dominant(pixels.data(),pixels.size()/4);assert(color);
    assert((*color)[0]>=32/255.&&(*color)[0]<=39/255.);
    assert(std::abs((*color)[1]-48/255.)<1e-6&&std::abs((*color)[2]-64/255.)<1e-6);
    assert(!WindowButtons::dominant(pixels.data(),0));
    auto legacy=WindowButtons::parseJson(R"({"mode":"always","size":42,"anchor":"top-left","x":20,"y":30,"proximity":80})");
    auto rule=WindowButtons::readRule(legacy.get());assert(rule.background=="auto"&&rule.size==42&&rule.x==20);
    auto encoded=WindowButtons::ruleJson(rule);assert(WindowButtons::readRule(encoded.get()).background=="auto");
    for(const char* bad:{"#123","#ff000000","invalid","#12345g"}){
        json_object_object_add(encoded.get(),"background_color",json_object_new_string(bad));
        bool rejected=false;try{WindowButtons::readRule(encoded.get());}catch(const std::runtime_error&){rejected=true;}assert(rejected);
    }
}

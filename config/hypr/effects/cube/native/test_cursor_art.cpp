#include "cursor_art.hpp"
#include <cassert>
#include <iostream>
#include <set>

int main(){
    std::vector<MouseArt::Mark> marks;
    for(unsigned i=0;i<120;++i)marks.push_back({{100+i*4.,200+std::sin(i*.12)*30},{1,0},1+i*.003,i,false});
    std::set<std::pair<size_t,long long>> signatures;
    for(auto style:{"plasma","orbit","fracture","circuit","tidal","ink","cinder","cloud"}){
        const auto art=MouseArt::make(style,marks,1.4,.56);size_t size=0;double sum=0;
        for(auto& batch:art)for(auto v:batch){
            assert(std::isfinite(v.x)&&std::isfinite(v.y)&&std::isfinite(v.alpha));
            assert(v.alpha>=0&&v.alpha<=1);assert(v.x>20&&v.x<700&&v.y>100&&v.y<300);sum+=v.x*v.alpha;size++;
        }
        assert(size>100&&size<50000);signatures.emplace(size,std::llround(sum));
        auto ended=MouseArt::make(style,marks,2,.56);for(auto& b:ended)assert(b.empty());
        // No frame-count dependence; redrawing one output cannot age another.
        auto again=MouseArt::make(style,marks,1.4,.56);
        for(int n=0;n<3;++n){assert(art[n].size()==again[n].size());for(size_t i=0;i<art[n].size();++i)assert(art[n][i].alpha==again[n][i].alpha);}
        std::cout<<style<<": "<<size<<" vertices\n";
    }
    assert(signatures.size()==8);
    assert(MouseArt::resolve("follow","tidalglass")=="tidal");
    assert(MouseArt::resolve("follow","obsidianforge")=="cinder");
    assert(MouseArt::resolve("follow","candycloud")=="cloud");
    assert(MouseArt::resolve("cloud","obsidianforge")=="cloud");
    assert(MouseArt::resolve("none","candycloud")=="none");
    assert(MouseArt::resolve("cinder","tidalglass")=="cinder");
    assert(MouseArt::resolve("ink","tidalglass")=="ink");
    std::cout<<"Distinct, bounded, time-based mouse art passed\n";
}

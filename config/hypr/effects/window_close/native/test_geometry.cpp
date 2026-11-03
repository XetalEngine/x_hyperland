#include "geometry.hpp"
#include <cassert>
#include <limits>
using namespace WindowButtons;
int main(){
    const Rect work{-1200,40,1180,1840},current{-1200,40,1180,1840};
    const auto inside=[&](Rect b){assert(b.x>=work.x&&b.y>=work.y&&b.x+b.w<=work.x+work.w+1&&b.y+b.h<=work.y+work.h+1);};
    auto b=restore(work,current,{700,500});inside(b);assert(b.w==700&&b.h==500);
    b=restore(work,current,{});inside(b);assert(b.w<current.w&&b.h<current.h);
    // A real remembered size remains valid even if it happens to match a tile.
    b=restore(work,current,{current.w,current.h});inside(b);assert(b.w==current.w&&b.h==current.h);
    b=restore(work,current,{3840,2160});inside(b);assert(b.w==work.w&&b.h==work.h);
    b=restore(work,current,{500,500},{800,600},{900,700});inside(b);assert(b.w==800&&b.h==600);
    b=restore(work,current,{4000,3000},{4000,3000});inside(b);
    b=restore(work,{-1160,100,700,500},{700,500},{},{},false);inside(b);assert(b.x==-1160&&b.y==100&&b.w==700&&b.h==500);
    b=restore(work,current,{std::numeric_limits<double>::infinity(),0});inside(b);assert(b.w<current.w);
    for(const Rect screen:{Rect{0,28,1920,1052},Rect{1920,-320,864,1536},Rect{-640,0,640,480}}){
        b=restore(screen,{0,0,2560,1440},{1600,1000});
        assert(b.x>=screen.x&&b.y>=screen.y&&b.x+b.w<=screen.x+screen.w+1&&b.y+b.h<=screen.y+screen.h+1);
    }
}

// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <algorithm>
#include <cmath>

namespace Minimize {
struct Rect { double x=0, y=0, w=0, h=0; };
inline double ease(double t) { t=std::clamp(t,0.0,1.0); return t*t*(3-2*t); }
// One column, paged by scrolling when a monitor cannot hold all its windows.
struct Column {
    int capacity, offset;
    double x, y, size, step;
    Column(double width, double height, double left, double top, double bottom, int requestedSize, int count, int scroll) {
        size=std::max(24.0,std::min({double(requestedSize),width-24,height-top-bottom-24}));
        step=size+12; x=left+8; y=top+12;
        capacity=std::max(1,int((height-top-bottom-12)/step));
        offset=std::clamp(scroll,0,std::max(0,count-capacity));
    }
    bool visible(int index) const { return index>=offset && index<offset+capacity; }
    Rect box(int index) const { return {x,y+(index-offset)*step,size,size}; }
};
inline Rect travel(Rect from, Rect to, double progress) {
    double t=ease(progress), bend=std::sin(t*3.141592653589793)*std::min(100.0,std::abs(to.x-from.x)*.12);
    return {from.x+(to.x-from.x)*t, from.y+(to.y-from.y)*t-bend,
            from.w+(to.w-from.w)*t, from.h+(to.h-from.h)*t};
}
}

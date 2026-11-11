// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "geometry.hpp"
#include <array>

namespace WindowButtons::Titlebar {
inline int height(int buttonSize) { return std::max(28, buttonSize + 12); }
// These are local decoration coordinates, not clipped to the owning output.
// The compositor positions/clips the complete decoration on each output.
struct Layout {
    std::array<Rect,4> buttons; // gear, minimize, maximize/restore, close
    Rect title;
};
inline Layout layout(double width, double barHeight, int requestedSize) {
    Layout result{};
    if(width<=0 || barHeight<=0)return result;
    const double pad=std::min(8.,width*.05);
    const double gap=std::min(std::max(4.,requestedSize/5.),width*.025);
    const double size=std::max(0.,std::min({double(requestedSize),barHeight-4,(width-2*pad-3*gap)/4}));
    const double x=width-pad-4*size-3*gap;
    for(int i=0;i<4;++i)result.buttons[i]={x+i*(size+gap),(barHeight-size)/2,size,size};
    result.title={pad,0,std::max(0.,x-2*pad),barHeight};
    return result;
}
inline int hit(const Layout& layout,double x,double y) {
    for(int i=0;i<4;++i){const auto& b=layout.buttons[i];
        if(b.w>0&&b.h>0&&x>=b.x&&y>=b.y&&x<b.x+b.w&&y<b.y+b.h)return i;}
    return -1;
}
}

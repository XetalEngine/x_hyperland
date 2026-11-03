// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <algorithm>
#include <cmath>

namespace WindowButtons {
struct Size {double w=0,h=0;};
struct Rect {double x=0,y=0,w=0,h=0;};
inline bool valid(Size size){return std::isfinite(size.w)&&std::isfinite(size.h)&&size.w>5&&size.h>5;}

// Work is the current output's usable content rectangle, after panel/border
// extents and a small outer margin. Never turn an unknown tiled size into an
// almost-fullscreen floating window, or restore another output's offscreen size.
inline Rect restore(Rect work,Rect current,Size saved,Size minimum={},Size maximum={},bool wasTiled=true){
    if(!valid(saved))
        saved={std::min(work.w*.78,current.w*.84),std::min(work.h*.78,current.h*.84)};
    const double maxW=std::max(1.,std::min(work.w,maximum.w>0?maximum.w:work.w));
    const double maxH=std::max(1.,std::min(work.h,maximum.h>0?maximum.h:work.h));
    const double w=std::floor(std::clamp(saved.w,std::min(maxW,std::max(1.,minimum.w)),maxW));
    const double h=std::floor(std::clamp(saved.h,std::min(maxH,std::max(1.,minimum.h)),maxH));
    const double x=wasTiled?current.x+(current.w-w)/2:current.x;
    const double y=wasTiled?current.y+(current.h-h)/2:current.y;
    return {std::round(std::clamp(x,work.x,work.x+work.w-w)),
            std::round(std::clamp(y,work.y,work.y+work.h-h)),w,h};
}
}

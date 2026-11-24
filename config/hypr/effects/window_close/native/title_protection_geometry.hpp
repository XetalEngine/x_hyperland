// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <algorithm>
#include <cmath>
#include <optional>

namespace TitleProtection {
struct Box { double x,y,w,h; };
struct Extents { double left,top,right,bottom; };
inline bool valid(Box b) {
    return std::isfinite(b.x)&&std::isfinite(b.y)&&std::isfinite(b.w)&&std::isfinite(b.h)&&b.w>0&&b.h>0;
}
// Protect the decorated header, not the whole window. Oversized windows keep
// their size, and windows spanning outputs may keep their existing position.
inline std::optional<Box> reachable(Box client,Box work,Extents ext) {
    if(!valid(client)||!valid(work))return std::nullopt;
    for(double v:{ext.left,ext.top,ext.right,ext.bottom})
        if(!std::isfinite(v)||v<0)return std::nullopt;
    const double width=client.w+ext.left+ext.right;
    const double grip=std::min({128.,width,work.w});
    const double header=std::min(work.h,std::max(32.,ext.top));
    const double x=std::clamp(client.x-ext.left,work.x+grip-width,work.x+work.w-grip)+ext.left;
    const double y=std::clamp(client.y-ext.top,work.y,work.y+work.h-header)+ext.top;
    if(std::abs(x-client.x)<.01&&std::abs(y-client.y)<.01)return std::nullopt;
    return Box{x,y,client.w,client.h};
}
}

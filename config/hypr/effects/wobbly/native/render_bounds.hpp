// SPDX-License-Identifier: GPL-2.0-or-later
// Conservative world-coordinate bounds of the interpolated Bezier surface.
#pragma once
#include "engine.hpp"

namespace Wobbly {
inline Box renderBounds(const Engine& engine) {
    const auto& b=engine.box;
    double left=b.x,top=b.y,right=b.x+b.w,bottom=b.y+b.h;
    // A Bezier patch stays inside its control-point hull. Use the same
    // interpolated points as Mesh::update, including the immediate grab anchor.
    for(auto p:engine.renderPoints()){
        left=std::min(left,double(p.x));top=std::min(top,double(p.y));
        right=std::max(right,double(p.x));bottom=std::max(bottom,double(p.y));
    }
    return {std::floor(left)-3,std::floor(top)-3,
            std::ceil(right)-std::floor(left)+6,std::ceil(bottom)-std::floor(top)+6};
}

inline bool overlaps(Box a,Box b) {
    return a.w>0 && a.h>0 && b.w>0 && b.h>0 &&
        a.x<b.x+b.w && b.x<a.x+a.w && a.y<b.y+b.h && b.y<a.y+a.h;
}
} // namespace Wobbly

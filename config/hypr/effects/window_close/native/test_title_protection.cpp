// SPDX-License-Identifier: GPL-2.0-or-later
#include "title_protection_geometry.hpp"
#include <cassert>
#include <limits>
using namespace TitleProtection;
int main() {
    const Box area{0,40,1920,1040};const Extents kde{1,29,1,1},csd{1,1,1,1};
    assert(!reachable({300,200,600,400},area,kde));
    auto a=reachable({300,30,600,400},area,kde);assert(a&&a->y==69&&a->x==300&&a->w==600&&a->h==400);
    a=reachable({300,-800,600,400},area,csd);assert(a&&a->y==41);
    a=reachable({-1800,-900,2600,1500},area,kde);assert(a&&a->x==-1800&&a->y==69&&a->w==2600&&a->h==1500);
    assert(!reachable({-400,100,600,400},area,csd)); // Reachable spanning window.
    a=reachable({-900,100,600,400},area,csd);assert(a&&a->x==-473&&a->y==100);
    a=reachable({2100,100,600,400},area,csd);assert(a&&a->x==1793);
    a=reachable({300,2000,600,400},area,kde);assert(a&&a->y==1077);
    for(const Box work:{Box{-1920,-160,1920,1040},Box{2560,72,1706.6666667,960},Box{-1280,40,1280,680}}) {
        const Box before{work.x+50,work.y-80,600,400};
        const auto result=reachable(before,work,kde);assert(result);
        assert(result->y-kde.top==work.y);
        assert(result->x==before.x&&result->w==before.w&&result->h==before.h);
        assert(!reachable(*result,work,kde)); // Idempotence: no recurring nudges.
    }
    a=reachable({0,-80,600,400},{0,0,64,20},kde);assert(a&&a->y==29);
    assert(!reachable({0,0,0,400},area,kde));
    assert(!reachable({0,0,600,400},{0,0,0,100},kde));
    assert(!reachable({0,std::numeric_limits<double>::quiet_NaN(),600,400},area,kde));
    assert(!reachable({0,-100,600,400},area,{-1,0,0,0}));
}

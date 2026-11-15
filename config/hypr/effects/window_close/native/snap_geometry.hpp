// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <optional>
#include <vector>
namespace SnapGeometry {
struct Point {double x=0,y=0;};
struct Box {double x=0,y=0,w=0,h=0;};
enum Zone {NoSnap,Left,Right,TopLeft,TopRight,BottomLeft,BottomRight,FirstThird,MiddleThird,LastThird};
inline bool valid(Box b){return std::isfinite(b.x)&&std::isfinite(b.y)&&std::isfinite(b.w)&&std::isfinite(b.h)&&b.w>=1&&b.h>=1;}
inline bool contains(Box b,Point p){return valid(b)&&p.x>=b.x&&p.x<b.x+b.w&&p.y>=b.y&&p.y<b.y+b.h;}
inline bool same(Box a,Box b){return std::abs(a.x-b.x)<2&&std::abs(a.y-b.y)<2&&std::abs(a.w-b.w)<2&&std::abs(a.h-b.h)<2;}
inline Box region(Box area,Zone zone){
    if(!valid(area)||zone==NoSnap)return {};
    if(zone>=FirstThird){
        const auto i=int(zone)-int(FirstThird);const double left=std::round(area.w*i/3),right=std::round(area.w*(i+1)/3);
        return {area.x+left,area.y,right-left,area.h};
    }
    const bool right=zone==Right||zone==TopRight||zone==BottomRight;
    const double half=std::round(area.w/2),middle=std::round(area.h/2);
    Box box{area.x+(right?half:0),area.y,right?area.w-half:half,area.h};
    if(zone==TopLeft||zone==TopRight)box.h=middle;
    if(zone==BottomLeft||zone==BottomRight){box.y+=middle;box.h-=middle;}
    return box;
}
inline Zone edge(Box monitor,Box work,Point p){
    if(!contains(monitor,p)||!valid(work))return NoSnap;
    const bool left=p.x<work.x+16,right=p.x>=work.x+work.w-16;
    if(!left&&!right)return NoSnap;
    if(p.y<work.y+64)return left?TopLeft:TopRight;
    if(p.y>=work.y+work.h-64)return left?BottomLeft:BottomRight;
    return left?Left:Right;
}
struct Cell {Box box;Zone zone;};
inline Box palette(Box work){
    const double width=std::min(440.,work.w-24);
    return width>=150?Box{work.x+(work.w-width)/2,work.y+12,width,80}:Box{};
}
inline std::vector<Cell> cells(Box panel){
    std::vector<Cell> result;if(!valid(panel))return result;
    const double unit=(panel.w-32)/3;
    const std::array<std::vector<Zone>,3> groups{{{Left,Right},{TopLeft,TopRight,BottomLeft,BottomRight},{FirstThird,MiddleThird,LastThird}}};
    for(int group=0;group<3;++group){
        Box area{panel.x+8+group*(unit+8),panel.y+8,unit,panel.h-16};
        for(auto zone:groups[group]){auto box=region(area,zone);box.x+=2;box.y+=2;box.w-=4;box.h-=4;result.push_back({box,zone});}
    }
    return result;
}
inline std::optional<Box> client(Box outer,Point topLeft,Point bottomRight,Point minimum,Point maximum){
    Box result{outer.x+topLeft.x,outer.y+topLeft.y,outer.w-topLeft.x-bottomRight.x,outer.h-topLeft.y-bottomRight.y};
    if(!valid(result)||!std::isfinite(minimum.x)||!std::isfinite(minimum.y)||!std::isfinite(maximum.x)||!std::isfinite(maximum.y)||
       result.w<std::max(1.,minimum.x)||result.h<std::max(1.,minimum.y)||
       (maximum.x>0&&result.w>maximum.x)||(maximum.y>0&&result.h>maximum.y))return std::nullopt;
    return result;
}
inline Box restore(Box normal,Box snapped,Box work,Point pointer){
    if(!valid(normal)||!valid(snapped)||!valid(work))return {};
    normal.w=std::min(normal.w,work.w);normal.h=std::min(normal.h,work.h);
    const double anchor=std::clamp((pointer.x-snapped.x)/snapped.w,0.,1.);
    const double yOffset=pointer.y-snapped.y;
    // Keep a title-bar grab at the same height; interior Super-drags keep the
    // same relative point in the content. Native dragBegin then owns the grab.
    normal.x=std::clamp(pointer.x-anchor*normal.w,work.x,work.x+work.w-normal.w);
    normal.y=std::clamp(pointer.y-(yOffset<=64?yOffset:std::clamp(yOffset/snapped.h,0.,1.)*normal.h),work.y,work.y+work.h-normal.h);
    return normal;
}
}

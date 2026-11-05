// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "motion.hpp"
#include <map>
#include <cstdint>

namespace Minimize __attribute__((visibility("hidden"))) {
enum class Edge { Bottom, Top, Left, Right };
inline const char* edgeName(Edge e) {
    switch(e){case Edge::Top:return "top";case Edge::Left:return "left";case Edge::Right:return "right";default:return "bottom";}
}
inline bool vertical(Edge e){return e==Edge::Left || e==Edge::Right;}
inline bool contains(Rect b,double x,double y){return x>=b.x && y>=b.y && x<b.x+b.w && y<b.y+b.h;}
inline Rect expand(Rect b,double n){return {b.x-n,b.y-n,b.w+2*n,b.h+2*n};}
inline Rect translate(Rect b,double x,double y){b.x+=x;b.y+=y;return b;}
inline double approach(double value,double target,double dt,double seconds) {
    const double result=target+(value-target)*std::exp(-7*std::clamp(dt,0.0,.1)/std::max(.05,seconds));
    return std::abs(result-target)<.02?target:result;
}
inline Rect approach(Rect value,Rect target,double dt,double seconds) {
    return {approach(value.x,target.x,dt,seconds),approach(value.y,target.y,dt,seconds),
            approach(value.w,target.w,dt,seconds),approach(value.h,target.h,dt,seconds)};
}
struct DockLayout {
    Edge edge;
    Rect panel, sensor;
    double size, step, thickness, hideDistance;
    int capacity, offset, shown;
    DockLayout(double width,double height,double left,double top,double right,double bottom,
               int requested,int count,int scroll,Edge side,int proximity):edge(side) {
        const bool v=vertical(edge);
        const double axis=std::max(32.0,v?height-top-bottom:width-left-right);
        const double cross=std::max(32.0,v?width-left-right:height-top-bottom);
        const double limit=std::max(32.0,axis*.88-24);
        size=std::clamp(double(requested),24.0,std::max(24.0,std::min(limit-24,cross-32)));
        // Grow the tray with its windows, then reduce slots before paging.
        if(count>0)size=std::min(size,std::max(48.0,(limit-24)/count-10));
        step=size+10;thickness=size+20;
        hideDistance=thickness+40+(edge==Edge::Bottom?bottom:edge==Edge::Top?top:edge==Edge::Left?left:right);
        capacity=std::max(1,int((limit-14)/step));offset=std::clamp(scroll,0,std::max(0,count-capacity));
        shown=std::min(count,capacity);
        const double length=shown?shown*step+14:0;
        const double start=(v?top:left)+(axis-length)/2;
        if(edge==Edge::Bottom)panel={start,height-bottom-thickness-10,length,thickness};
        else if(edge==Edge::Top)panel={start,top+10,length,thickness};
        else if(edge==Edge::Left)panel={left+10,start,thickness,length};
        else panel={width-right-thickness-10,start,thickness,length};
        const double reach=std::max(2,proximity), span=std::min(axis,std::max(length,120.0)+32);
        const double sensorStart=(v?top:left)+(axis-span)/2;
        if(edge==Edge::Bottom)sensor={sensorStart,height-std::max(reach,bottom+10),span,std::max(reach,bottom+10)};
        else if(edge==Edge::Top)sensor={sensorStart,0,span,std::max(reach,top+10)};
        else if(edge==Edge::Left)sensor={0,sensorStart,std::max(reach,left+10),span};
        else sensor={width-std::max(reach,right+10),sensorStart,std::max(reach,right+10),span};
    }
    bool visible(int index)const{return index>=offset && index<offset+capacity;}
    Rect slot(int index)const{
        const double along=12+(index-offset)*step;
        return vertical(edge)?Rect{panel.x+10,panel.y+along,size,size}:Rect{panel.x+along,panel.y+10,size,size};
    }
    Rect shifted(Rect b,double reveal)const {
        const double distance=hideDistance*(1-ease(reveal));
        if(edge==Edge::Bottom)return translate(b,0,distance);
        if(edge==Edge::Top)return translate(b,0,-distance);
        if(edge==Edge::Left)return translate(b,-distance,0);
        return translate(b,distance,0);
    }
};
struct DockState {
    Rect panel;
    Edge edge=Edge::Bottom;
    double reveal=0, holdUntil=0, last=0;
    bool initialized=false, awake=false;
    std::map<uint64_t,Rect> slots;
    std::map<uint64_t,double> zoom;
    void hold(double now,double seconds){holdUntil=std::max(holdUntil,now+seconds);}
    bool update(const DockLayout& layout,double now,bool hovered,bool arriving,bool autoHide,double delay,double duration,int count) {
        const double dt=initialized?std::max(0.0,now-last):.016;last=now;
        if(!initialized || edge!=layout.edge){
            edge=layout.edge;panel=layout.panel;
            if(vertical(edge)){panel.y+=panel.h/2;panel.h=0;}else{panel.x+=panel.w/2;panel.w=0;}
            initialized=true;
        }
        if(hovered || arriving)hold(now,delay);
        const double target=count && (!autoHide || arriving || hovered || now<holdUntil)?1:0;
        const auto previous=panel;const double before=reveal;
        panel=approach(panel,layout.panel,dt,duration);
        reveal=approach(reveal,target,dt,duration);
        awake=reveal!=target || panel.x!=layout.panel.x || panel.y!=layout.panel.y || panel.w!=layout.panel.w || panel.h!=layout.panel.h;
        return before!=reveal || previous.x!=panel.x || previous.y!=panel.y || previous.w!=panel.w || previous.h!=panel.h;
    }
};
}

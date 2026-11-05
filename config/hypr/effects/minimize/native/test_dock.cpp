// SPDX-License-Identifier: GPL-2.0-or-later
#include "dock.hpp"
#include <cassert>
#include <cmath>
using namespace Minimize;
int main(){
    // Each edge respects reserved space and centers the tray on usable space.
    for(auto edge:{Edge::Bottom,Edge::Top,Edge::Left,Edge::Right}){
        DockLayout d(1280,800,32,40,56,28,76,4,0,edge,18);
        assert(d.shown==4 && d.offset==0);
        assert(d.panel.x>=32 && d.panel.y>=40);
        assert(d.panel.x+d.panel.w<=1224 && d.panel.y+d.panel.h<=772);
        for(int i=0;i<4;i++){
            auto s=d.slot(i);
            assert(contains(d.panel,s.x,s.y) && contains(d.panel,s.x+s.w-1,s.y+s.h-1));
        }
        auto hidden=d.shifted(d.panel,0),shown=d.shifted(d.panel,1);
        assert(shown.x==d.panel.x && shown.y==d.panel.y);
        assert(hidden.x+hidden.w<0 || hidden.y+hidden.h<0 || hidden.x>1280 || hidden.y>800);
        assert(d.sensor.x>=0 && d.sensor.y>=0 && d.sensor.x+d.sensor.w<=1280 && d.sensor.y+d.sensor.h<=800);
        assert(!contains(d.sensor,640,400));
    }
    DockLayout one(1280,800,0,32,0,0,100,1,0,Edge::Bottom,12);
    DockLayout four(1280,800,0,32,0,0,100,4,0,Edge::Bottom,12);
    DockLayout many(1280,800,0,32,0,0,100,60,999,Edge::Bottom,12);
    assert(four.panel.w>one.panel.w && four.size==one.size);
    assert(many.size<four.size && many.size>=48 && many.panel.w<1280);
    assert(many.visible(59) && !many.visible(0));
    assert(many.shown==many.capacity && many.offset==60-many.capacity);
    DockLayout small(320,120,0,36,0,0,160,12,-5,Edge::Bottom,12);
    assert(small.offset==0 && small.panel.y>=36 && small.panel.y+small.panel.h<=120);

    // Deadlines restart on interaction/arrival. Hidden docks become idle.
    DockState s;s.hold(1,1.2);
    for(int i=0;i<60;i++)s.update(one,1+i*.016,false,false,true,1.2,.32,1);
    assert(s.reveal==1 && s.panel.w==one.panel.w);
    s.update(one,2,true,false,true,1.2,.32,1);
    for(int i=1;i<60;i++)s.update(one,2+i*.016,false,false,true,1.2,.32,1);
    assert(s.reveal==1);
    for(int i=0;i<120;i++)s.update(one,3+i*.016,false,false,true,1.2,.32,1);
    assert(s.reveal==0 && !s.awake);
    s.update(one,5,true,false,true,1.2,.32,1);
    assert(s.reveal>0 && s.reveal<1 && s.awake);
    for(int i=1;i<90;i++)s.update(one,5+i*.016,false,false,false,1.2,.32,1);
    assert(s.reveal==1);
    auto before=s.panel;s.update(four,6.5,false,true,false,1.2,.32,4);
    assert(s.panel.w>before.w && s.panel.w<four.panel.w);
    for(int i=1;i<60;i++)s.update(four,6.5+i*.016,false,false,false,1.2,.32,4);
    assert(s.panel.w==four.panel.w);
    DockLayout empty(1280,800,0,32,0,0,100,0,0,Edge::Bottom,12);
    for(int i=0;i<120;i++)s.update(empty,8+i*.016,false,false,false,1.2,.32,0);
    assert(s.reveal==0 && s.panel.w==0 && !s.awake);
    // The same time at different refresh rates yields the same transition.
    double a=0,b=0;
    for(int i=0;i<12;i++)a=approach(a,100,1./60,.32);
    for(int i=0;i<24;i++)b=approach(b,100,1./120,.32);
    assert(std::abs(a-b)<.000001);
}

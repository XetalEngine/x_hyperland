// SPDX-License-Identifier: GPL-2.0-or-later
#include "snap_geometry.hpp"
#include <cassert>
#include <limits>
using namespace SnapGeometry;
int main(){
    // Three differently positioned/scaled logical outputs; negative positions
    // and an odd width must partition without gaps or overlapping pixels.
    for(Box work:std::array<Box,3>{{{-1920,32,1920,1048},{0,36,2048,1116},{2048,-864,1707,929}}}){
        const auto a=region(work,Left),b=region(work,Right);
        assert(a.x+a.w==b.x&&a.w+b.w==work.w);
        auto first=region(work,FirstThird),middle=region(work,MiddleThird),last=region(work,LastThird);
        assert(first.x+first.w==middle.x&&middle.x+middle.w==last.x&&last.x+last.w==work.x+work.w);
        auto top=region(work,TopRight),bottom=region(work,BottomRight);
        assert(top.y+top.h==bottom.y&&top.h+bottom.h==work.h);
        auto fitted=client(a,{2,32},{2,2},{300,200},{});
        assert(fitted&&fitted->x==a.x+2&&fitted->y==work.y+32&&fitted->h==work.h-34);
        assert(!client(a,{2,32},{2,2},{20000,200},{}));
        assert(!client(a,{2,32},{2,2},{},{600,300}));
        Box monitor{work.x,work.y-32,work.w,work.h+32};
        assert(edge(monitor,work,{work.x+2,work.y+100})==Left);
        assert(edge(monitor,work,{work.x+work.w-2,work.y+work.h-4})==BottomRight);
        assert(edge(monitor,work,{work.x+work.w+1,work.y})==NoSnap);
        assert(edge(monitor,work,{work.x+work.w/2,work.y+200})==NoSnap);
        assert(edge(monitor,work,{work.x+work.w/2,monitor.y})==Maximize);
        assert(edge(monitor,work,{work.x+work.w/2,work.y+16})==Maximize);
        assert(edge(monitor,work,{work.x+work.w/2,work.y+17})==NoSnap);
        assert(edge(monitor,work,{work.x+work.w/2,monitor.y-1})==NoSnap);
        assert(edge(monitor,work,{work.x+2,monitor.y})==TopLeft);
        assert(edge(monitor,work,{work.x+work.w-2,monitor.y})==TopRight);
        assert(same(region(work,Maximize),work));
        auto panel=palette(work);auto choices=cells(panel);assert(choices.size()==9);
        for(const auto& cell:choices){
            assert(contains(panel,{cell.box.x,cell.box.y}));assert(valid(region(work,cell.zone)));
            // Moving down into the chooser still selects halves/quarters/thirds.
            assert(cell.zone!=Maximize&&cell.box.y>work.y+16);
        }
    }
    Box work{100,64,1600,900},snapped{100,64,800,900},normal{200,170,640,480};
    auto restored=restore(normal,snapped,work,{500,80});
    assert(restored.w==640&&restored.h==480&&restored.x==180&&restored.y==64);
    restored=restore(normal,snapped,work,{500,500});
    assert(restored.y>=work.y&&restored.y+restored.h<=work.y+work.h);
    restored=restore({0,0,9000,9000},snapped,work,{130,75});assert(restored.w==1600&&restored.h==900);
    assert(!valid(region({},Left)));assert(!valid(restore({},snapped,work,{})));
    assert(!client({0,0,std::numeric_limits<double>::infinity(),100},{},{},{},{}));
    assert(!client({0,0,100,100},{2,150},{2,2},{},{}));
    assert(same({0,0,500,400},{1,1,500,400}));assert(!same({0,0,500,400},{0,0,502,400}));
}

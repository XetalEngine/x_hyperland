#include "engine.hpp"
#include "settings.hpp"
#include <cassert>
#include <iostream>
using namespace Wobbly;
bool near(float a,float b,float tolerance=.001){return std::abs(a-b)<tolerance;}
int main(int argc,char** argv){
    Engine e({100,200,300,150});
    for(int y=0;y<=10;++y)for(int x=0;x<=10;++x){auto p=e.evaluate(x/10.f,y/10.f);assert(near(p.x,100+x*30));assert(near(p.y,200+y*15));}
    assert(e.model->numObjects==16 && e.model->numSprings==24);
    e.grab(100,200,false);e.geometry({160,200,300,150},false,160,200);
    e.step(15,3,8);
    // Original Compiz: k * .5 * 60 / MASS = 16 px on each adjacent node.
    assert(near(e.model->objects[0].position.x,160));
    assert(near(e.model->objects[1].position.x,216));
    assert(near(e.model->objects[4].position.x,116));
    assert(near(e.model->objects[15].position.x,400));
    auto p=e.evaluate(.5,.5);assert(p.x>250 && p.x<310);
    e.release();int n=0;while(e.step(15,3,8)&&n++<5000){}assert(n<5000);
    assert(near(e.model->bottomRight.x-e.model->topLeft.x,300,1));
    Engine a({0,0,900,600}),b({0,0,900,600});a.grab(0,0,false);b.grab(0,0,false);
    a.geometry({90,0,900,600},false,90,0);b.geometry({90,0,900,600},false,90,0);
    for(int i=0;i<100;++i)a.step(15,3,8);
    for(int i=0;i<300;++i)b.step(5,3,8);
    for(int i=0;i<16;++i)assert(near(a.model->objects[i].position.x,b.model->objects[i].position.x));
    Engine snap({30,100,300,200});Compiz::CompScreen screen;screen.outputDev.push_back({{0,0,1000,800}});
    snap.window.screen=&screen;snap.grab(30,100,false);snap.snap(true);snap.geometry({-10,100,300,200},false,-10,100);
    for(int i=0;i<35;++i)snap.step(15,3,8);
    assert(snap.model->snapCnt[Compiz::WEST]>0);
    snap.snap(false);assert(snap.model->snapCnt[Compiz::WEST]==0);
    for(int i=0;i<16;++i)assert(!snap.model->objects[i].vertEdge.snapped);
    Engine max({100,100,400,300});max.geometry({0,0,1000,800},true,0,0);
    assert(max.model->objects[0].immobile && max.model->objects[15].immobile);
    max.step(15,3,8);assert(near(max.model->objects[15].position.x,1000));
    max.geometry({100,100,400,300},false,100,100);assert(!max.model->objects[15].immobile);
    max.shiver();assert(max.step(15,3,8));
    for(double friction:{.1,3.,10.})for(double spring:{.1,8.,10.}){
        Engine extreme({100,100,1200,800});extreme.grab(100,100,true);extreme.geometry({700,-100,1200,800},false,700,-100);extreme.release();
        for(int i=0;i<10000&&extreme.step(15,friction,spring);++i){}
    }
    WindowInfo w;w.app="kitty";w.title="Terminal";w.floating=true;
    assert(Match("Normal & class=ki*").matches(w));assert(!Match("Normal & !class=kitty").matches(w));
    assert(Match("Dialog | (Normal & floating=1)").matches(w));assert(!Match("").matches(w));
    for(auto s:{"Normal &", "(Normal", "bogus", "class=", "floating=2", "Normal || Dialog"}){bool bad=false;try{Match m(s);}catch(...){bad=true;}assert(bad);}
    if(argc>1){auto settings=readSettings(argv[1]);assert(settings.friction==3 && settings.spring_k==8 && settings.snapModifiers==1);}
    std::cout<<"Original Compiz spring forces, fixed steps, Bezier mesh, edge snapping, resize and matches passed\n";
}

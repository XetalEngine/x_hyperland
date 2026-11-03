#include "engine.hpp"
#include "settings.hpp"
#include "mesh.hpp"
#include <cassert>
#include <iostream>
#include <chrono>
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
    // A 120 Hz display must see positions between the original 15 ms poses,
    // while the grabbed point follows input without an interpolation delay.
    Engine smooth({0,0,300,150});smooth.grab(0,0,false);smooth.geometry({60,0,300,150},false,60,0);
    smooth.step(15,3,8);auto solved=smooth.model->objects[1].position.x;
    auto start=smooth.renderPoints();smooth.step(5,3,8);auto third=smooth.renderPoints();smooth.step(5,3,8);auto twoThirds=smooth.renderPoints();
    assert(smooth.model->objects[1].position.x==solved);
    assert(start[1].x<third[1].x && third[1].x<twoThirds[1].x && twoThirds[1].x<solved);
    assert(start[0].x==60 && third[0].x==60);
    // Cached vertices preserve the exact Bezier surface and source coordinates.
    Mesh mesh;Box viewport{0,0,1920,1080};mesh.update(smooth,8,8,viewport);
    auto reference=*smooth.model;std::array<Compiz::Object,16> objects;
    for(int i=0;i<16;++i){objects[i]=smooth.model->objects[i];objects[i].position=twoThirds[i];}
    reference.objects=objects.data();
    for(auto v:mesh.vertices){
        float x,y;Compiz::bezierPatchEvaluate(&reference,(v.u*viewport.w-smooth.box.x)/smooth.box.w,(v.v*viewport.h-smooth.box.y)/smooth.box.h,&x,&y);
        assert(near(v.x*viewport.w,x,.002) && near(v.y*viewport.h,y,.002));
    }
    auto allocation=mesh.vertices.data();mesh.update(smooth,8,8,viewport);assert(mesh.vertices.data()==allocation);
    // Full-window captures have their own UV origin even when the original
    // window is outside an output. A screen-sized source would discard these
    // texels before the spring lattice can bend them back onto either output.
    for(const auto box: {Box{-180,200,620,400},Box{1100,200,620,400},
                         Box{250,-180,620,400},Box{250,800,620,400}}){
        Engine edge(box);edge.grab(box.x+300,box.y+200,false);
        edge.geometry({box.x+80,box.y+40,box.w,box.h},false,box.x+380,box.y+240);
        edge.step(8,3,3);
        const Box source{edge.box.x-2,edge.box.y-2,edge.box.w+4,edge.box.h+4};
        for(const auto screen:{Box{0,0,1280,900},Box{1280,0,640,800}}){
            Mesh complete;complete.update(edge,3,8,screen,source);
            for(const auto v:complete.vertices){
                assert(v.u>=0 && v.u<=1 && v.v>=0 && v.v<=1);
                const auto point=edge.evaluate((v.u*source.w+source.x-edge.box.x)/edge.box.w,
                                                (v.v*source.h+source.y-edge.box.y)/edge.box.h);
                assert(near(v.x*screen.w+screen.x,point.x,.003));
                assert(near(v.y*screen.h+screen.y,point.y,.003));
            }
        }
    }
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
    // The same elapsed time produces the same springs on 60/120/144/240 Hz
    // outputs. Mixed cadence models moving a window between those monitors.
    auto simulate=[](const std::vector<double>& frames){
        Engine e({0,0,600,400});e.grab(50,20,true);e.geometry({160,80,600,400},false,210,100);e.release();
        for(auto ms:frames)e.step(ms,3,3);
        return e.renderPoints();
    };
    auto cadence=[](int hz,double seconds){std::vector<double> v(int(hz*seconds),1000./hz);return v;};
    auto expected=simulate(cadence(60,.5));
    for(int hz:{120,144,240}){
        auto actual=simulate(cadence(hz,.5));
        for(int i=0;i<16;++i){assert(std::abs(actual[i].x-expected[i].x)<.01);assert(std::abs(actual[i].y-expected[i].y)<.01);}
    }
    auto mixed=cadence(60,.25);auto high=cadence(144,.25);mixed.insert(mixed.end(),high.begin(),high.end());
    auto switched=simulate(mixed);for(int i=0;i<16;++i)assert(std::abs(switched[i].x-expected[i].x)<.01);
    if(argc>1){auto settings=readSettings(argv[1]);assert(settings.enabled && settings.friction==3 && settings.spring_k==3 && settings.snapModifiers==1);
        assert(settings.grid_resolution==3 && settings.focus_effect==1 && settings.hotkey_drag && settings.normal_drag);}
    std::cout<<"Original Compiz spring forces, fixed steps, Bezier mesh, edge snapping, resize and matches passed\n";
    if(argc>2 && std::string(argv[2])=="--benchmark"){
        Engine large({100,100,1600,1000});Mesh cached;Box screen{0,0,2560,1440};
        double checksum=0;constexpr int repeats=1000;
        auto begin=std::chrono::steady_clock::now();
        for(int n=0;n<repeats;++n)for(int pass=0;pass<2;++pass)
            for(int y=0;y<1000;y+=15)for(int x=0;x<1600;x+=25)
                for(auto uv:{std::pair{x,y},std::pair{x+25,y},std::pair{x+25,y+15},std::pair{x,y+15}}){
                    auto p=large.evaluate(std::min(uv.first/1600.f,1.f),std::min(uv.second/1000.f,1.f));checksum+=p.x+p.y;
                }
        auto old=std::chrono::steady_clock::now();
        for(int n=0;n<repeats;++n){cached.update(large,64,4,screen);checksum+=cached.vertices[n%cached.vertices.size()].x;}
        auto now=std::chrono::steady_clock::now();
        std::cout<<"Mesh benchmark (color + blur), previous "<<std::chrono::duration<double,std::micro>(old-begin).count()/repeats
                 <<" us/frame; cached "<<std::chrono::duration<double,std::micro>(now-old).count()/repeats<<" us/frame; checksum "<<checksum<<"\n";
    }
}

// SPDX-License-Identifier: GPL-2.0-or-later
#include "engine.hpp"
#include "fire_texture.hpp"
#include <cassert>
#include <iostream>

int main() {
    using namespace Burn;
    // Upstream updateParticles reference: position is advanced with the OLD
    // velocity; velocity and life then advance by time/50.
    Particle p; p.life=1; p.fade=.2; p.x=10; p.y=20; p.xi=4; p.yi=-5; p.xg=-1; p.yg=-3;
    std::vector<Particle> ps{p};Engine::update(ps,30,.5);
    assert(std::abs(ps[0].x-10.8)<.0001 && std::abs(ps[0].y-19)<.0001);
    assert(std::abs(ps[0].xi-3.4)<.0001 && std::abs(ps[0].yi+6.8)<.0001);
    assert(std::abs(ps[0].life-.88)<.0001);

    for (int direction=0;direction<6;++direction) {
        Settings s;s.fire_direction=direction;s.fire_smoke=true;
        Engine e(s,{100,50,600,400},100,50,123);
        assert(e.direction>=0 && e.direction<4);
        assert(e.fire.size()==1000 && e.smoke.size()==100);
        float area=600*400;
        for (int frame=0;frame<200 && !e.done();++frame) {
            e.step();auto v=e.visible();assert(v.w*v.h<=area+.1);area=v.w*v.h;
            for (const auto& particles : {&e.fire,&e.smoke}) for (const auto& q:*particles)
                assert(std::isfinite(q.x) && std::isfinite(q.y) && std::isfinite(q.life));
        }
        assert(e.done());
    }
    Settings s;s.duration=1000;s.fire_constant_speed=true;
    assert(Engine(s,{0,0,600,250},0,0,1).total==500);
    assert(Engine(s,{0,0,600,1000},0,0,1).total==2000);
    s.fire_constant_speed=false;s.fire_direction=5;
    assert(Engine(s,{100,100,100,100},150,0,1).direction==1);
    assert(Engine(s,{100,100,100,100},150,300,1).direction==0);
    assert(Engine(s,{100,100,100,100},0,150,1).direction==2);
    assert(Engine(s,{100,100,100,100},300,150,1).direction==3);

    // Valid combinations that caused division by zero in the original must
    // finish without NaNs, including duration <= the intense timestep.
    for (int timestep : {1,30,200,400}) for (int duration : {50,200,4000}) {
        Settings x;x.time_step_intense=timestep;x.duration=duration;x.fire_particles=100;
        x.fire_life=1;x.fire_slowdown=.1;
        Engine e(x,{0,0,600,400},0,0,42);
        int ticks=0;
        while(!e.done() && ++ticks<40000) e.step();
        assert(e.done() && std::isfinite(e.progress));
    }
    // Smoke is independent of flame alpha; color alpha must survive the port.
    Settings c;c.fire_color={10000,20000,30000,12345};
    Engine e(c,{0,0,600,400},0,0,7);e.step();int count=0;
    for (const auto& q:e.fire) if(q.life>0) {
        ++count;assert(std::abs(q.g-2*q.r)<.0001 && std::abs(q.b-3*q.r)<.0001);
        assert(std::abs(q.a-12345/65535.F)<.0001);
    }
    assert(count>0 && count<=200);
    static_assert(sizeof(fireTex)==4097);
    std::cout << "Compiz particle equations, directions, lifetime, constant speed, RGBA and boundary cases passed\n";
}

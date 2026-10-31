// SPDX-License-Identifier: GPL-2.0-or-later
// Persistent emitter using Compiz animationaddon particle motion (2006),
// Erkin Bahceci and Dennis Kasprzyk. See ../README.md and ../../burn/COPYING.
#pragma once
#include "../../burn/native/engine.hpp"
namespace Minimize {
class Fire {
    std::mt19937 rng;
    double elapsed=0;
    float random(){return float(rng()&255)/255.F;}
    void step() {
        Burn::Engine::update(particles,30.F,.65F);
        int budget=20;
        for(auto& p:particles) {
            if(p.life>0){p.xg=(p.x<p.xo?1.F:-1.F);continue;}
            if(budget--<=0)continue;
            p.life=1;p.fade=random()*.27F+.062F;
            p.width=5.5F+random()*3;p.height=p.width*1.5F;
            p.w_mod=p.h_mod=random()*1.8F;
            float angle=random()*6.283185F,radius=std::sqrt(random());
            p.x=p.xo=50+std::cos(angle)*16*radius;
            p.y=74+std::sin(angle)*7*radius;
            p.xi=random()*20-10;p.yi=random()*12-16;p.yg=-3;
            p.a=.65F+random()*.35F;p.r=1-random()/1.7F;
        }
    }
  public:
    std::vector<Burn::Particle> particles=std::vector<Burn::Particle>(384);
    explicit Fire(uint32_t seed=1):rng(seed){for(int i=0;i<45;++i)step();}
    void advance(double seconds){
        // Fixed Compiz timestep, bounded catch-up after a locked/idle desktop.
        elapsed+=std::clamp(seconds,0.0,.12);
        while(elapsed>=.030){step();elapsed-=.030;}
    }
};
}

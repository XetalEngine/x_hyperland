// Copyright (c) 2026 XetalEngine. Original physics: compiz.hpp / COPYING.
#pragma once
#include "compiz.hpp"
#include <memory>
#include <stdexcept>

namespace Wobbly {
struct Box { double x=0,y=0,w=0,h=0; };
class Engine {
  public:
    Compiz::CompWindow window;
    Compiz::Model* model;
    Box box;
    bool grabbed=false, snapping=false, maximized=false;
    int active=Compiz::WobblyInitial;
    Engine(Box b):box(b) {
        model=Compiz::createModel(b.x,b.y,b.w,b.h,15);
        if(!model)throw std::bad_alloc();
    }
    ~Engine(){std::free(model->objects);std::free(model);}
    Engine(const Engine&)=delete;
    Engine& operator=(const Engine&)=delete;
    void wake(){active|=Compiz::WobblyInitial;}
    void grab(float x,float y,bool impulse) {
        grabbed=true;
        Compiz::modelRemoveEdgeAnchors(model,box.x,box.y,box.w,box.h);
        if(model->anchorObject)model->anchorObject->immobile=false;
        model->anchorObject=Compiz::modelFindNearestObject(model,x,y);
        model->anchorObject->immobile=true;
        Compiz::modelDisableSnapping(&window,model);
        snapping=false;
        if(impulse)for(int i=0;i<model->numSprings;++i){
            auto& s=model->springs[i];
            if(s.a==model->anchorObject){s.b->velocity.x-=s.offset.x*.05f;s.b->velocity.y-=s.offset.y*.05f;}
            else if(s.b==model->anchorObject){s.a->velocity.x+=s.offset.x*.05f;s.a->velocity.y+=s.offset.y*.05f;}
        }
        wake();
    }
    void release() {
        grabbed=false;
        if(model->anchorObject)model->anchorObject->immobile=false;
        model->anchorObject=nullptr;
        if(maximized)Compiz::modelAddEdgeAnchors(model,box.x,box.y,box.w,box.h);
        wake();
    }
    void snap(bool on) {
        if(on==snapping)return;
        snapping=on;
        if(on)Compiz::modelUpdateSnapping(&window,model);
        else Compiz::modelDisableSnapping(&window,model);
        wake();
    }
    void shiver() {
        Compiz::modelSetMiddleAnchor(model,box.x,box.y,box.w,box.h);
        Compiz::modelAdjustObjectsForShiver(model,box.x,box.y,box.w,box.h);
        wake();
    }
    void geometry(Box next,bool max,float pointerX,float pointerY) {
        const bool resized=next.w!=box.w || next.h!=box.h;
        if(max!=maximized){
            if(max){
                if(model->anchorObject)model->anchorObject->immobile=false;
                model->anchorObject=nullptr;
                Compiz::modelAddEdgeAnchors(model,next.x,next.y,next.w,next.h);
            } else {
                Compiz::modelRemoveEdgeAnchors(model,next.x,next.y,next.w,next.h);
                Compiz::modelSetMiddleAnchor(model,next.x,next.y,next.w,next.h);
            }
            maximized=max;
            Compiz::modelInitSprings(model,next.x,next.y,next.w,next.h);
            wake();
        } else if(resized){
            if(max)Compiz::modelAddEdgeAnchors(model,next.x,next.y,next.w,next.h);
            else Compiz::modelSetTopAnchor(model,next.x,next.y,next.w);
            Compiz::modelInitSprings(model,next.x,next.y,next.w,next.h);
            wake();
        } else if(next.x!=box.x || next.y!=box.y){
            if(grabbed && model->anchorObject){
                model->anchorObject->position.x+=next.x-box.x;
                model->anchorObject->position.y+=next.y-box.y;
                wake();
            } else Compiz::modelMove(model,next.x-box.x,next.y-box.y);
        }
        if(resized && grabbed){
            if(model->anchorObject)model->anchorObject->immobile=false;
            model->anchorObject=Compiz::modelFindNearestObject(model,pointerX,pointerY);
            model->anchorObject->immobile=true;
            Compiz::modelAdjustObjectPosition(model,model->anchorObject,next.x,next.y,next.w,next.h);
        }
        box=next;
    }
    bool step(float ms,float friction,float spring) {
        // Keep original 15 ms integration even on high-refresh outputs. Bound
        // catch-up after suspend, without changing the spring equations.
        active=Compiz::modelStep(&window,model,friction,spring,std::clamp(ms,0.f,120.f));
        if(active==Compiz::WobblyForce && !grabbed){Compiz::modelReduceEdgeEscapeVelocity(model);wake();}
        for(int i=0;i<model->numObjects;++i){
            const auto& p=model->objects[i].position;
            if(!std::isfinite(p.x)||!std::isfinite(p.y)||std::abs(p.x-box.x)>100000||std::abs(p.y-box.y)>100000)
                throw std::runtime_error("Wobbly model exceeded its geometry bounds");
        }
        return active!=0;
    }
    Compiz::Point evaluate(float u,float v) const {
        Compiz::Point p;Compiz::bezierPatchEvaluate(model,u,v,&p.x,&p.y);return p;
    }
};
} // namespace Wobbly

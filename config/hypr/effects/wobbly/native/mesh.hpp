// SPDX-License-Identifier: GPL-2.0-or-later
// Cached tessellation of the original Compiz bicubic patch.
#pragma once
#include "engine.hpp"

namespace Wobbly {
struct Vertex {float x,y,u,v;};
class Mesh {
    struct Sample {float u,v;std::array<float,16> weights;};
    double width=0,height=0;
    int cellW=0,cellH=0;
    std::vector<Sample> samples;
    std::vector<size_t> triangles;
    std::vector<Vertex> points;
    static std::array<float,4> basis(float t){return {(1-t)*(1-t)*(1-t),3*t*(1-t)*(1-t),3*t*t*(1-t),t*t*t};}
  public:
    std::vector<Vertex> vertices;
    void update(const Engine& engine,int resolution,int minimum,Box viewport,Box source={}){
        if(source.w<=0||source.h<=0)source=viewport;
        const auto& b=engine.box;
        int gw=std::max(int(b.w/resolution),minimum),gh=std::max(int(b.h/resolution),minimum);
        if(b.w!=width||b.h!=height||gw!=cellW||gh!=cellH){
            width=b.w;height=b.h;cellW=gw;cellH=gh;
            int nx=std::ceil(width/gw),ny=std::ceil(height/gh);
            samples.clear();triangles.clear();samples.reserve((nx+1)*(ny+1));triangles.reserve(nx*ny*6);
            for(int y=0;y<=ny;++y)for(int x=0;x<=nx;++x){
                Sample s{float(std::min(double(x*gw),width)/width),float(std::min(double(y*gh),height)/height),{}};
                auto u=basis(s.u),v=basis(s.v);
                for(int j=0;j<4;++j)for(int i=0;i<4;++i)s.weights[j*4+i]=u[i]*v[j];
                samples.push_back(s);
                if(x<nx&&y<ny){size_t a=y*(nx+1)+x,c=a+nx+2;triangles.insert(triangles.end(),{a,a+1,c,a,c,c-1});}
            }
            points.resize(samples.size());vertices.resize(triangles.size());
        }
        auto control=engine.renderPoints();
        for(size_t i=0;i<samples.size();++i){
            const auto& s=samples[i];float x=0,y=0;
            for(size_t j=0;j<16;++j){x+=control[j].x*s.weights[j];y+=control[j].y*s.weights[j];}
            points[i]={float((x-viewport.x)/viewport.w),float((y-viewport.y)/viewport.h),
                float((b.x+s.u*b.w-source.x)/source.w),float((b.y+s.v*b.h-source.y)/source.h)};
        }
        for(size_t i=0;i<triangles.size();++i)vertices[i]=points[triangles[i]];
    }
};
} // namespace Wobbly

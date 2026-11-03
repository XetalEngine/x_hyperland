// SPDX-License-Identifier: GPL-2.0-or-later
// Procedural mouse trails: bounded geometry, absolute age, no renderer state.
#pragma once
#include <array>
#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

namespace MouseArt {
constexpr double PI=3.141592653589793;
struct Point {double x=0,y=0;Point operator+(Point b)const{return {x+b.x,y+b.y};}Point operator-(Point b)const{return {x-b.x,y-b.y};}Point operator*(double n)const{return {x*n,y*n};}};
struct Mark {Point p,d;double born=0;unsigned seed=0;bool click=false;};
struct Vertex {float x,y,alpha;};
using Batch=std::vector<Vertex>;
using Art=std::array<Batch,3>;
inline std::string resolve(std::string trail,const std::string& design){
    if(trail!="follow")return trail;
    if(design=="modern")return "orbit";
    if(design=="breakpoint")return "fracture";
    if(design=="binaryknife")return "circuit";
    if(design=="tidalglass")return "tidal";
    if(design=="porcelainink")return "ink";
    if(design=="obsidianforge")return "cinder";
    if(design=="candycloud")return "cloud";
    if(design=="shadowedge")return "blade";
    return "plasma";
}
inline std::array<std::string,3> palette(const std::string& style){
    if(style=="orbit")return {"#83bfff","#dfbdff","#f6faff"};
    if(style=="fracture")return {"#ff405d","#ffd8b0","#fff2f4"};
    if(style=="circuit")return {"#32adff","#bcf1ff","#ffffff"};
    if(style=="tidal")return {"#68dfed","#d2faff","#f2ffff"};
    if(style=="ink")return {"#bb3b30","#f0e4cc","#20252b"};
    if(style=="cinder")return {"#ff8a3d","#a84b23","#ffe1a3"};
    if(style=="cloud")return {"#f6a5d7","#c4a7ff","#fff0d9"};
    if(style=="blade")return {"#c9cfd8","#e04459","#f4f6f9"};
    return {"#32e7ee","#c4ff76","#f1ffff"};
}
inline void triangle(Batch& out,Point a,Point b,Point c,double alpha,double beta=-1,double gamma=-1){
    if(alpha<=0)return;
    out.insert(out.end(),{{float(a.x),float(a.y),float(alpha)},
                         {float(b.x),float(b.y),float(beta<0?alpha:beta)},
                         {float(c.x),float(c.y),float(gamma<0?alpha:gamma)}});
}
inline void line(Batch& out,Point a,Point b,double width,double alpha,double end=-1){
    auto d=b-a;double len=std::hypot(d.x,d.y);if(len<.01)return;
    Point n{-d.y/len*width*.5,d.x/len*width*.5};if(end<0)end=alpha;
    triangle(out,a+n,a-n,b+n,alpha,alpha,end);triangle(out,a-n,b-n,b+n,alpha,end,end);
}
inline Point polar(double a,double r){return {std::cos(a)*r,std::sin(a)*r};}
inline void disc(Batch& out,Point p,double r,double alpha,bool glow=false,int sides=12){
    for(int n=0;n<sides;++n)triangle(out,p,p+polar(n*2*PI/sides,r),p+polar((n+1)*2*PI/sides,r),alpha,glow?0:alpha,glow?0:alpha);
}
inline void ring(Batch& out,Point p,double r,double width,double alpha,double tilt=1,double rotation=0){
    const int sides=24;auto at=[&](int n,double radius){double a=n*2*PI/sides;
        Point v{std::cos(a)*radius,std::sin(a)*radius*tilt};return p+Point{v.x*std::cos(rotation)-v.y*std::sin(rotation),v.x*std::sin(rotation)+v.y*std::cos(rotation)};};
    for(int n=0;n<sides;++n){auto a=at(n,r),b=at(n+1,r),c=at(n,r-width),d=at(n+1,r-width);
        triangle(out,a,b,c,alpha);triangle(out,b,d,c,alpha);}
}
inline Art make(const std::string& style,const std::vector<Mark>& marks,double now,double lifetime){
    Art out;for(auto& b:out)b.reserve(marks.size()*70);
    for(size_t i=0;i<marks.size();++i){
        const auto& m=marks[i];double age=std::clamp((now-m.born)/lifetime,0.,1.);if(age>=1)continue;
        const double fade=(1-age)*(1-age),seed=m.seed*.61803398875;
        Point p=m.p,n{-m.d.y,m.d.x};const double angle=std::atan2(m.d.y,m.d.x);
        if(m.click){ring(out[1],p,6+age*34,1.5,fade);continue;}
        const bool joined=i>0&&!marks[i-1].click&&std::hypot((p-marks[i-1].p).x,(p-marks[i-1].p).y)<64;
        const double oldFade=i?std::pow(std::max(0.,1-(now-marks[i-1].born)/lifetime),2):fade;
        if(style=="plasma"){
            if(joined)for(int strand:{-1,1}){
                auto offset=n*(std::sin(m.born*24+age*8)*7*strand);
                const auto& old=marks[i-1];Point oldN{-old.d.y,old.d.x};
                auto prior=old.p+oldN*(std::sin(old.born*24+(now-old.born)/lifetime*8)*7*strand);
                line(out[0],prior,p+offset,7,oldFade*.18,fade*.18);
                line(out[strand==1?0:1],prior,p+offset,1.5,oldFade,fade);
            }
            if(m.seed%4==0){disc(out[0],p,10,fade*.3,true);disc(out[2],p,1.8,fade);}
        }else if(style=="orbit"){
            if(m.seed%3)continue;
            double rotation=seed+age*3,r=4+age*15;
            disc(out[0],p,r*1.5,fade*.18,true);ring(out[0],p,r,1.3,fade,.55,rotation);
            ring(out[1],p,r*.75,1.,fade*.7,.55,-rotation);
            disc(out[2],p+polar(rotation,r),2.1,fade);
        }else if(style=="fracture"){
            if(m.seed%2)continue;
            double side=m.seed%4?1:-1;
            p=p+n*(side*age*26)-m.d*(age*10);double a=angle+seed+age*side*4;
            double size=2+(m.seed%5);auto tip=p+polar(a,size*1.6),left=p+polar(a+2.5,size),right=p+polar(a-2.5,size*.6);
            triangle(out[m.seed%3==0?1:0],tip,left,right,fade);
            line(out[2],tip,left,.8,fade*.8);line(out[0],p,p-m.d*(6*(1-age)),1,fade*.5);
        }else if(style=="circuit"){
            if(joined){auto before=marks[i-1].p;Point elbow{p.x,before.y};
                line(out[0],before,elbow,1.4,oldFade,fade);line(out[0],elbow,p,1.4,fade);}
            if(m.seed%5)continue;
            p=p+n*(age*18)+Point{0,age*18};
            double w=3,h=5;auto& batch=out[1];
            if(m.seed%2){line(batch,p+Point{0,-h},p+Point{0,h},1.2,fade);line(batch,p+Point{-2,-3},p+Point{0,-h},1.2,fade);}
            else{line(batch,p+Point{-w,-h},p+Point{w,-h},1.2,fade);line(batch,p+Point{w,-h},p+Point{w,h},1.2,fade);
                line(batch,p+Point{w,h},p+Point{-w,h},1.2,fade);line(batch,p+Point{-w,h},p+Point{-w,-h},1.2,fade);}
            disc(out[2],m.p,1.5,fade);
        }else if(style=="tidal"){
            if(joined)line(out[0],marks[i-1].p,p,5,oldFade*.17,fade*.17);
            if(m.seed%3)continue;
            p=p+Point{std::sin(seed+age*4)*age*13,-age*28};double r=2+(m.seed%6)+age*5;
            disc(out[0],p,r*2,fade*.22,true);ring(out[0],p,r,1,fade*.8);
            disc(out[2],p+Point{-r*.35,-r*.45},1.4,fade);disc(out[1],p+n*12,1.1,fade*.7);
        }else if(style=="ink"){
            if(joined){line(out[1],marks[i-1].p,p,5*fade+.7,oldFade*.5,fade*.5);
                line(out[2],marks[i-1].p,p,3.6*fade+.4,oldFade,fade);}
            if(m.seed%4)continue;
            p=p+n*(std::sin(seed)*age*24)+Point{age*8,age*14};
            double a=seed+age*2;Point tip=p+polar(a,4),side=polar(a+PI/2,1.8);
            triangle(out[0],tip,p+side,p-polar(a,4),fade);triangle(out[0],tip,p-polar(a,4),p-side,fade);
            disc(out[2],p+n*6,1.1,fade);
        }else if(style=="blade"){
            if(joined){
                line(out[0],marks[i-1].p,p,4,oldFade*.12,fade*.12);
                line(out[2],marks[i-1].p,p,.9,oldFade*.85,fade*.85);
            }
            if(m.seed%6)continue;
            const double side=m.seed%12?1:-1;
            const auto center=p+n*(side*age*14)-m.d*(age*14);
            const double r=3+age*13,rotation=angle+side*age*1.7;
            for(int j=0;j<8;++j){
                const double a=rotation+side*(-.8+j*1.5/8);
                line(out[0],center+polar(a,r),center+polar(a+side*1.5/8,r),
                     .4+std::sin(j*PI/8)*2*(1-age),fade*.8);
            }
            const auto needle=p+n*(side*(4+age*24))+m.d*(age*6);
            triangle(out[1],needle+m.d*5,needle-m.d*3+n*1.2,needle-m.d*3-n*1.2,fade);
        }else if(style=="cloud"){
            if(joined){
                line(out[1],marks[i-1].p,p,5,oldFade*.16,fade*.16);
                line(out[0],marks[i-1].p,p,1.3,oldFade*.7,fade*.7);
            }
            if(m.seed%5)continue;
            p=p+Point{std::sin(seed+age*2)*age*12,-age*22};
            const double r=3.5+age*3;
            // Three solid lobes form a little cloud, rather than a bubble ring.
            disc(out[1],p+Point{0,1},r*2.5,fade*.22,true);
            disc(out[0],p+Point{-r*.8,r*.35},r*.75,fade*.7);
            disc(out[0],p+Point{r*.85,r*.35},r*.8,fade*.7);
            disc(out[0],p+Point{0,-r*.1},r,fade*.82);
            line(out[2],p+Point{-r*.3,-r*.7},p+Point{r*.25,-r*.7},.9,fade*.8);
            const Point star=p+Point{std::sin(seed)*15,9+age*13};
            const double rotation=seed+age*1.8,size=2+std::sin(age*PI)*2;
            for(int arm=0;arm<4;++arm){double a=rotation+arm*PI/2;
                triangle(out[2],star+polar(a,size),star+polar(a+PI/4,size*.26),star,fade);
                triangle(out[2],star+polar(a,size),star,star+polar(a-PI/4,size*.26),fade);
            }
        }else if(style=="cinder"){
            if(joined){auto before=marks[i-1].p;
                line(out[0],before,p,8,oldFade*.18,fade*.18);
                line(out[1],before,p,3,oldFade,fade);
                line(out[2],before,p,1.1,oldFade*(1-age),fade*(1-age));}
            if(m.seed%4)continue;
            double side=m.seed%8?1:-1;auto crack=p+n*(side*7)+m.d*3;
            line(out[1],p,crack,1.2,fade*.6);line(out[0],crack,crack+n*(side*4)-m.d*4,.8,fade*.4);
            auto ember=p+Point{std::sin(seed)*age*22,-age*(22+m.seed%14)};
            disc(out[0],ember,6*(1-age)+1,fade*.45,true);
            line(out[0],ember+Point{-age*2,3+age*3},ember,1.4,fade);
            disc(out[2],ember,1.3*(1-age)+.3,fade);
        }else if(style=="sparkle"){
            line(out[0],p+Point{-4*fade,0},p+Point{4*fade,0},1.4,fade);
            line(out[0],p+Point{0,-4*fade},p+Point{0,4*fade},1.4,fade);
        }else disc(out[0],p,(style=="glow"?12:4)*fade,fade,style=="glow");
    }return out;
}
} // namespace MouseArt

// SPDX-License-Identifier: GPL-2.0-or-later
// Living slime: stable silhouettes, advected surface, swelling blisters and pop ripples.
#pragma once
namespace Minimize __attribute__((visibility("hidden"))) {
inline constexpr const char* splatFragment=R"GLSL(#version 300 es
precision highp float;
in vec2 coord; out vec4 fragColor;
uniform vec3 tint;
uniform float time, opacity, emphasis, seed, outlineSeed, bubbles;
uniform int shape, surface;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);
 return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);}
float fbm(vec2 p){return noise(p)*.57+noise(p*2.03+17.1)*.28+noise(p*4.11+5.4)*.15;}
float smoothUnion(float a,float b,float k){float h=clamp(.5+.5*(b-a)/k,0.0,1.0);return mix(b,a,h)-k*h*(1.0-h);}
float silhouette(vec2 p){
 float a=atan(p.y,p.x),r=length(p),s=float(shape),rot=outlineSeed*.721;
 float lobes=shape==1?12.0:shape==3?6.0:shape==5?14.0:shape==6?11.0:shape==7?7.0:9.0;
 float radius=(shape==3?.20:.245)+.018*sin(a*3.0+rot)+.014*cos(a*5.0-rot*1.7);
 if(shape==2)radius+=.024*sin(a*2.0-1.1)+.02*cos(a+1.5);
 radius+=.003*sin(a*7.0+time*.9+seed)*sin(time*.7+a*2.0);
 float d=r-radius;
 // Tapered, round-ended tendrils merge like viscous liquid, with no sharp
 // polygonal spikes. Their outline is independent of the moving surface.
 for(int i=0;i<14;++i){
   float j=float(i);if(j>=lobes)break;
   float h=hash(vec2(j+outlineSeed,s+7.0));
   float angle=j/lobes*6.283185+rot+(h-.5)*.38;
   vec2 dir=vec2(cos(angle),sin(angle));
   vec2 start=dir*.17,end=dir*(.30+h*.08+(shape==3||shape==6?.04:0.0));
   float t=clamp(dot(p-start,end-start)/dot(end-start,end-start),0.0,1.0);
   float width=mix(.035,shape==1?.009:.017+.013*hash(vec2(j+8.0,outlineSeed)),t);
   if(shape==6 || shape==7)width=mix(shape==7?.048:.026,.008,t)+
        (shape==7?.036:.022)*smoothstep(.62,1.0,t);
   float arm=length(p-mix(start,end,t))-width;
   d=smoothUnion(d,arm,.035);
 }
 for(int i=0;i<8;++i){
   float j=float(i),h=hash(vec2(j+outlineSeed,s+17.0));
   float angle=j*2.39996+rot;
   vec2 center=vec2(cos(angle),sin(angle))*(.405+h*.025);
   float bead=.008+.009*hash(vec2(j+4.0,outlineSeed));
   d=min(d,length(p-center)-bead*(1.0+.08*sin(time*1.7+j)));
 }
 if(shape==6){
   for(int i=0;i<6;++i){
     float angle=float(i)*1.0472+rot+.27;
     vec2 center=vec2(cos(angle),sin(angle))*.235;
     float hole=length((p-center)/vec2(1.0,.72))-(.014+.009*hash(center+outlineSeed));
     d=max(d,-hole);
   }
 }
 return d;
}
// Warped moving cells form the membranes, with raised connecting ridges.
vec2 cells(vec2 p){
 vec2 id=floor(p),f=fract(p);float nearest=10.0,second=10.0;
 for(int y=-1;y<=1;++y)for(int x=-1;x<=1;++x){
   vec2 n=vec2(float(x),float(y));
   float h=hash(id+n+seed);
   vec2 center=n+.5+.28*sin(vec2(5.3,7.7)*h+vec2(time*.13,-time*.16));
   float distance=length(center-f);
   if(distance<nearest){second=nearest;nearest=distance;}else second=min(second,distance);
 }
 return vec2(nearest,second-nearest);
}
void main(){
 vec2 p=coord-vec2(.5,.53);
 vec2 stretch=shape==4?vec2(1.08,.76):shape==2?vec2(.89,1.0):vec2(.94,.94);
 p/=stretch;
 float d=silhouette(p);
 float aa=max(fwidth(d),.001);
 float coverage=1.0-smoothstep(-aa,aa,d);
 vec2 flow=vec2(fbm(p*4.0+vec2(time*.16,seed)),fbm(p*4.0+vec2(seed,-time*.14)));
 float tissue=fbm(p*18.0+flow*2.0+vec2(time*.10,-time*.12));
 float depth=clamp(-d/.14,0.0,1.0);
 float height=.075*sqrt(max(depth,0.0001))+.007*tissue*depth;
 float vein=0.0,pocket=0.0;
 if(surface==1){
   vec2 cell=cells(p*8.0+flow*.85);
   vein=exp(-cell.y*cell.y*180.0);
   pocket=smoothstep(.02,.38,cell.y);
   height+=(.024*vein-.018*pocket+.006*fbm(p*42.0+flow))*depth;
 }else if(surface==2){
   height=.085*sqrt(max(depth,0.0001))+.012*(1.0-dot(p,p)*2.0)+.002*fbm(p*10.0+flow)*depth;
 }
 // Each blister swells, ruptures and leaves a fading ring in the skin.
 vec2 cellGrid=p*6.8;
 vec2 cell=floor(cellGrid),local=fract(cellGrid)-.5;
 vec2 offset=vec2(hash(cell+seed),hash(cell+seed+39.0))-.5;
 float phase=fract(time*(.20+hash(cell+8.0)*.16)+hash(cell+seed+3.0));
 float radius=mix(.07,.34,smoothstep(0.0,.74,phase));
 float q=length(local-offset*.42)/radius;
 float alive=1.0-smoothstep(.73,.82,phase);
 float dome=sqrt(max(0.0,1.0-q*q));
 float ripple=exp(-pow((q-(1.0+(phase-.8)*3.2))*7.0,2.0))*smoothstep(.76,.82,phase)*(1.0-smoothstep(.86,1.0,phase));
 float bubbleMask=smoothstep(.012,.06,-d)*bubbles;
 height+=(.048*dome*alive-.012*ripple)*bubbleMask*(surface==1?.7:surface==2?.28:1.0);
 vec2 gradient=vec2(dFdx(height)/max(abs(dFdx(coord.x)),.00001),dFdy(height)/(abs(dFdy(coord.y))>.00001?dFdy(coord.y):.00001));
 vec3 normal=normalize(vec3(-gradient*.7,1.0));
 vec3 light=normalize(vec3(-.55,-.70,1.1));
 float diffuse=max(dot(normal,light),0.0);
 vec3 halfLight=normalize(light+vec3(0,0,1));
 float spec=pow(max(dot(normal,halfLight),0.0),surface==2?58.0:42.0);
 float broad=pow(max(dot(normal,halfLight),0.0),9.0);
 float veins=pow(1.0-abs(tissue*2.0-1.0),12.0);
 vec3 color;
 if(surface==1){
   color=tint*(.08+.20*diffuse+.07*tissue)*(1.0-pocket*.40);
   color+=mix(tint,vec3(1),.12)*vein*.62;
   color+=mix(tint,vec3(1),.72)*(spec*.65+broad*.035);
 }else if(surface==2){
   color=tint*(.45+.60*diffuse);
   color+=mix(tint,vec3(1),.92)*(spec*.70+broad*.035);
   // A narrow strip light makes the rounded liquid silhouette read as wet.
   float strip=pow(max(dot(normal,normalize(vec3(.62,-.35,1.2))),0.0),110.0);
   color+=vec3(.30)*strip;
 }else{
   color=tint*(.17+.57*diffuse+.27*tissue);
   color*=1.0-.14*veins;
   color+=mix(tint,vec3(1),.64)*(spec*.80+broad*.075);
 }
 color+=tint*(surface==1?.50:.30)*exp(-abs(d)*95.0);
 color+=tint*ripple*bubbleMask*.25;
 color*=1.0+emphasis*.17;
 float halo=exp(-max(d,0.0)*65.0)*.11*(1.0-coverage);
 float alpha=(coverage*.98+halo)*opacity;
 color=mix(tint*.33,color,coverage);
 fragColor=vec4(color*alpha,alpha);
}
)GLSL";
}

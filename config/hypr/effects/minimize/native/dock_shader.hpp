// SPDX-License-Identifier: GPL-2.0-or-later
// Procedural materials: no wallpaper screenshots or bitmap dependencies.
#pragma once
namespace Minimize {
inline constexpr const char* dockFragment=R"(#version 300 es
precision highp float;
uniform vec2 dimensions;
uniform vec3 tint,base,ink;
uniform float time,opacity,emphasis;
uniform int style,part,vertical;
in vec2 coord;in vec4 particleColor;out vec4 fragColor;
float line(vec2 p,vec2 a,vec2 b){vec2 ab=b-a;return length(p-a-ab*clamp(dot(p-a,ab)/dot(ab,ab),0.,1.));}
float roundBox(vec2 p,vec2 b,float r){vec2 q=abs(p)-b+r;return min(max(q.x,q.y),0.)+length(max(q,0.))-r;}
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
void main(){
 vec2 dims=vertical==1?dimensions.yx:dimensions;
 vec2 uv=vertical==1?coord.yx:coord;
 vec2 p=(uv-.5)*dims;vec2 halfSize=dims*.5-vec2(8.);
 float radius=style==0?3.:style==2?10.:style==3?5.:style==5?5.:style==6?9.:style==8?4.:halfSize.y;
 if(part==1)radius=style==0?2.:style==2||style==3||style==6||style==8?8.:16.;
 radius=min(radius,min(halfSize.x,halfSize.y));
 float distance=roundBox(p,halfSize,radius);
 if(style==2||style==3||style==8)distance=max(distance,(abs(p.x)+abs(p.y)-halfSize.x-halfSize.y+10.)*.7071);
 float mask=1.-smoothstep(-.7,1.,distance);
 float border=(1.-smoothstep(.4,1.5,abs(distance+1.2)))*mask;
 float shadow=exp(-max(distance,0.)*.40)*.24;
 float shine=pow(clamp(1.-uv.y,0.,1.),3.);
 vec3 body=mix(base,tint,.055)+ink*shine*.065;
 float decoration=0.;float metal=0.;
 float rim=.26;
 if(part==0){
  if(style==0){
   decoration=(1.-smoothstep(.4,1.3,abs(p.y-halfSize.y+6.)))*.6;
   decoration+=step(.88,fract((p.x+halfSize.x)/14.))*(1.-smoothstep(1.,2.,abs(p.y+halfSize.y-7.)))*.4;
  }else if(style==1){
   decoration=exp(-abs(p.y+halfSize.y-3.)*.75)*(.3+.1*sin(p.x*.012+time*.6));rim=.35;
  }else if(style==2){
   decoration=(1.-smoothstep(.5,1.6,abs(p.y-halfSize.y+5.)))*.75;
   decoration+=step(.92,fract((p.x+p.y)/17.))*step(halfSize.x-30.,abs(p.x))*.35;
   metal=step(.96,fract(p.x/36.))*.04;
  }else if(style==3){
   decoration=exp(-abs(abs(p.x)+abs(p.y)-halfSize.x-halfSize.y+15.)*.8)*.7;
   metal=(sin(p.x*.07+p.y*.16+time*.3)*.5+.5)*.055;rim=.45;
  }else if(style==4){
   float wave=sin(p.x*.025+time*.7)*3.+sin(p.x*.06-time*.4)*2.;
   decoration=exp(-abs(p.y-halfSize.y+9.+wave)*.5)*.35;
   metal=pow(.5+.5*sin(p.x*.02+p.y*.08+time*.6),4.)*.06;rim=.5;
  }else if(style==5){
   body+=ink*(hash(floor(p*1.5))-.5)*.025;
   decoration=(1.-smoothstep(.5,1.5,abs(p.y-halfSize.y+6.+sin(p.x*.04)*.5)))*.45;
   vec2 stamp=p-vec2(halfSize.x-17.,0.);decoration+=exp(-abs(length(stamp)-7.)*1.4)*.5;
  }else if(style==6){
   body+=ink*(hash(vec2(floor(p.y*2.),0.))-.5)*.04;
   decoration=exp(-abs(p.y-halfSize.y+6.)*.9)*(.6+.15*sin(time+p.x*.05));
   vec2 rivet=vec2(abs(p.x)-halfSize.x+13.,abs(p.y)-halfSize.y+13.);
   metal+=(1.-smoothstep(1.,3.,length(rivet)))*.25;rim=.4;
  }else if(style==7){
   body=mix(body,ink,.055+shine*.07);
   decoration=0.12*pow(.5+.5*sin(p.x*.06+sin(p.y*.12)+time*.4),5.);
   vec2 star=vec2(mod(p.x+17.,47.)-23.5,p.y-halfSize.y+12.);
   decoration+=exp(-(abs(star.x)+abs(star.y))*.9)*(.4+.2*sin(time*1.4+p.x));rim=.48;
  }else if(style==8){
   metal=step(.94,fract((p.x-p.y)*.09))*.05;
   decoration=exp(-abs(p.y+halfSize.y-4.)*1.3)*.4+exp(-abs(p.y-halfSize.y+5.)*1.3)*.25;rim=.38;
  }else if(style==9){
   // Silver vines and paired leaves curl around the tray's ends.
   vec2 q=vec2(halfSize.x-abs(p.x),p.y);
   float vine=line(q,vec2(12.,-halfSize.y+9.),vec2(30.,halfSize.y-9.));
   decoration=exp(-vine*1.5)*.35;
   for(int i=0;i<4;i++){
    float h=-halfSize.y+14.+float(i)*10.;float x=16.+float(i)*4.;
    vec2 leaf=q-vec2(x+(i%2==0?-4.:5.),h);
    vec2 rotated=vec2(leaf.x*.8+leaf.y*.6,-leaf.x*.6+leaf.y*.8);
    decoration+=(1.-smoothstep(.7,1.,length(rotated/vec2(5.5,2.2))))*.45;
   }
   decoration*=.85+.15*sin(time*.8+p.y*.09);rim=.4;
  }
 }else{
  body=mix(base,tint,.08+emphasis*.14)+ink*shine*.045;
  rim=.08+emphasis*.25;
  decoration=exp(-abs(p.y-halfSize.y+3.)*1.7)*(.25+.4*emphasis);
 }
 vec3 surface=body+ink*metal+tint*decoration;
 surface=mix(surface,mix(tint,ink,.3),border*rim);
 float alpha=mask*(part==1?.28+emphasis*.18:.9);
 vec3 rgb=surface*alpha;
 float outside=shadow*(1.-mask);
 alpha+=outside;
 fragColor=vec4(rgb,alpha)*opacity;
})";
}

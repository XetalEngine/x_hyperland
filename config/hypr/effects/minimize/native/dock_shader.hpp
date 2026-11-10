// SPDX-License-Identifier: GPL-2.0-or-later
// Procedural materials: no wallpaper screenshots or bitmap dependencies.
#pragma once
namespace Minimize __attribute__((visibility("hidden"))) {
inline constexpr const char* dockFragment=R"(#version 300 es
precision highp float;
uniform vec2 dimensions;
uniform vec3 tint,base,ink;
uniform float time,opacity,emphasis,reveal;
uniform int style,part,vertical,edge;
in vec2 coord;in vec4 particleColor;out vec4 fragColor;
float line(vec2 p,vec2 a,vec2 b){vec2 ab=b-a;return length(p-a-ab*clamp(dot(p-a,ab)/dot(ab,ab),0.,1.));}
float roundBox(vec2 p,vec2 b,float r){vec2 q=abs(p)-b+r;return min(max(q.x,q.y),0.)+length(max(q,0.))-r;}
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+1.),f.x),f.y);}
void main(){
 vec2 dims=vertical==1?dimensions.yx:dimensions;
 vec2 uv=vertical==1?coord.yx:coord;
 if(part==2){
  float x=uv.x*dims.x;
  float depth=((edge==0||edge==3)?1.-uv.y:uv.y)*dims.y;
  float flicker=noise(vec2(x*.12-time*.9,time*1.1));
  float tips=3.+9.*pow(noise(vec2(x*.085+time*.35,time*1.7)),2.);
  float flame=exp(-depth*.24)*(1.-smoothstep(tips-2.,tips+2.,depth));
  float ends=smoothstep(0.,12.,x)*smoothstep(0.,12.,dims.x-x);
  float core=exp(-depth*.8)*(.55+.25*flicker);
  vec3 warm=mix(tint,vec3(1.,.25,.035),.30);
  float a=(flame*(.32+.24*flicker)+core*.3)*ends;
  fragColor=vec4(mix(warm,mix(ink,vec3(1.,.72,.25),.5),core)*a,a)*opacity;return;
 }
 vec2 p=(uv-.5)*dims;vec2 halfSize=dims*.5-vec2(8.);
 float radius=style==20?6.:style==19?14.:style==18?5.:style==17?7.:style==16?1.:style==0?3.:style==2?10.:style==3?5.:style==5?5.:style==6?9.:style==8?4.:style==11?12.:style==12?9.:style==13||style==14?5.:style==15?20.:halfSize.y;
 if(part==1)radius=style==20?4.:style==19?11.:style==18?4.:style==17?6.:style==16?1.:style==0?2.:style==14?3.:style==13?4.:style==12?6.:style==2||style==3||style==6||style==8?8.:style==10||style==11?10.:16.;
 radius=min(radius,min(halfSize.x,halfSize.y));
 float distance=roundBox(p,halfSize,radius);
 if(style==2||style==3||style==8)distance=max(distance,(abs(p.x)+abs(p.y)-halfSize.x-halfSize.y+(style==3?19.:style==8?14.:10.))*.7071);
 if(style==7&&part==0)distance+=sin(p.x*.10)*.9*smoothstep(0.,halfSize.y,p.y);
 float mask=1.-smoothstep(-.7,1.,distance);
 float border=(1.-smoothstep(.4,1.5,abs(distance+1.2)))*mask;
 float shadow=exp(-max(distance,0.)*.40)*.24;
 float shine=pow(clamp(1.-uv.y,0.,1.),3.);
 vec3 body=mix(base,tint,.055)+ink*shine*.065;
 float decoration=0.;float metal=0.;
 float rim=.26;
 float jewel=0.;float jewelHalo=0.;float gildedSweep=0.;
 if(part==0){
  if(style==20){
   // Puzzle Reliquary: engraved brass, double rims and violet faceted seals.
   vec3 brass=mix(ink,vec3(.7804,.6078,.3804),.65);
   vec2 q=vec2(halfSize.x-abs(p.x)-15.,p.y);
   body=mix(base,tint,.04)+ink*shine*.075;rim=.0;
   body+=brass*exp(-abs(distance+4.)*1.9)*.35;
   float diamond=abs(abs(q.x)/10.+abs(q.y)/19.-1.);
   float cross=min(line(q,vec2(0.,-19.),vec2(0.,19.)),line(q,vec2(-10.,0.),vec2(10.,0.)));
   body+=brass*(exp(-diamond*24.)*.85+exp(-cross*2.)*.4)*step(abs(q.y),20.)*step(abs(q.x),11.);
   body+=brass*exp(-abs(length(q)-6.)*2.)*.4;
   body+=brass*exp(-abs(abs(p.y)-halfSize.y+7.)*2.)*step(29.,halfSize.x-abs(p.x))*.55;
   decoration=exp(-dot(q,q)*.4)*(.65+.2*sin(time));
  }else if(style==19){
   // Orbital Glass: curved sapphire shoulder, inset rim and orbiting end lights.
   vec2 q=vec2(halfSize.x-abs(p.x)-15.,p.y);
   body=mix(base,tint,.04)+ink*shine*.14;rim=.55;
   decoration=exp(-abs(distance+3.)*1.7)*.18;
   decoration+=exp(-abs(p.y-halfSize.y+6.)*1.8)*step(26.,halfSize.x-abs(p.x))*.65;
   metal=exp(-abs(p.y+halfSize.y-3.)*1.8)*step(26.,halfSize.x-abs(p.x))*.55;
   float orbit=abs(length(q/vec2(8.,18.))-1.);
   decoration+=exp(-orbit*20.)*.65;
   vec2 light=q-vec2(8.*cos(time*.7),18.*sin(time*.7));
   metal+=(1.-smoothstep(1.,2.5,length(light)))*.85;
   float star=min(line(q,vec2(-6.,0.),vec2(6.,0.)),line(q,vec2(0.,-6.),vec2(0.,6.)));
   decoration+=exp(-star*2.)*exp(-length(q)*.12)*.8;
  }else if(style==18){
   // Amplifier Rack: speaker end caps, brass guards and red power lamps.
   vec3 brass=mix(tint,ink,.65);
   vec2 q=vec2(halfSize.x-abs(p.x),p.y);
   body=mix(base,ink,shine*.07);rim=.20;
   float cap=1.-smoothstep(23.,24.,q.x);
   float grille=step(.75,fract(q.x/3.))*step(.7,fract(p.y/3.));
   body+=ink*grille*cap*.08;
   for(int i=0;i<2;i++){
    vec2 c=q-vec2(12.,-11.+float(i)*22.);
    body+=brass*exp(-abs(length(c)-6.)*2.)*.65;
    decoration+=exp(-dot(c,c)*.8)*.45;
   }
   float guard=step(q.x,18.)*exp(-abs(abs(p.y)-halfSize.y+3.)*2.);
   guard+=step(abs(p.y),halfSize.y-3.)*step(halfSize.y-14.,abs(p.y))*exp(-abs(q.x-3.)*2.);
   body+=brass*min(1.,guard)*.8;
   body+=brass*exp(-abs(p.y+halfSize.y-4.)*2.)*step(25.,q.x)*.5;
   decoration+=exp(-abs(p.y-halfSize.y+4.)*2.)*step(25.,q.x)*.55;
  }else if(style==17){
   // Neon Pit Lane: lacquer, cyan/magenta rails and angled light fins.
   // Rotate the selected accent channels so both colors follow the palette.
   vec3 neon=tint.brg;
   vec2 q=vec2(halfSize.x-abs(p.x),p.y);
   body=mix(base,tint,.04)+ink*shine*.10;rim=.42;
   float span=step(23.,q.x);
   decoration=exp(-abs(p.y+halfSize.y-6.)*1.8)*span*.8;
   body+=neon*exp(-abs(p.y-halfSize.y+6.)*1.7)*span*.8;
   for(int i=0;i<2;i++){
    float x=8.+float(i)*5.;
    float fin=line(q,vec2(x,7.),vec2(x+4.,-7.));
    body+=mix(tint,neon,float(i))*exp(-fin*1.7)*.8;
   }
   metal=exp(-abs(p.y-halfSize.y+3.)*1.8)*span*step(.65,fract((p.x+halfSize.x)/19.))*.16;
  }else if(style==16){
   // Parcel Shelf: classic raised casework, brass shelf rail and end handles.
   vec2 q=vec2(halfSize.x-abs(p.x),p.y);
   body=mix(base,ink,.04*shine);rim=0.;
   float cap=1.-smoothstep(17.,18.,q.x);
   body=mix(body,mix(base,tint,.18),cap);
   float handle=abs(roundBox(vec2(q.x-9.,p.y),vec2(3.5,17.),1.));
   body=mix(body,mix(base,ink,.45),exp(-handle*2.)*.8);
   decoration=exp(-abs(p.y-halfSize.y+6.)*1.5)*step(23.,q.x)*.6;
   metal=exp(-abs(p.y+halfSize.y-5.)*1.8)*step(23.,q.x)*.18;
  }else if(style==15){
   // Spore Cradle: velvet body, cap lanterns and branching ivory root threads.
   vec2 q=vec2(halfSize.x-abs(p.x),p.y);
   body=mix(base,tint,.075)+ink*shine*.07;rim=.55;
   float stem=line(q,vec2(15.,-3.),vec2(15.,15.));
   float cap=length((q-vec2(15.,-6.))/vec2(11.,6.));
   float capMask=(1.-smoothstep(.85,1.05,cap))*step(p.y,-4.);
   body=mix(body,mix(tint,ink,.22+.25*shine),capMask);
   metal=exp(-stem*1.5)*step(abs(p.y-6.),10.)*.7;
   metal+=exp(-abs(p.y+3.)*1.7)*step(abs(q.x-15.),10.)*.55;
   decoration=exp(-dot((q-vec2(15.,1.))/vec2(16.,22.),(q-vec2(15.,1.))/vec2(16.,22.)))*(.10+.02*sin(time*.6));
   float rootY=halfSize.y-8.+sin(p.x*.018)*2.;
   metal+=exp(-abs(p.y-rootY)*1.6)*step(26.,q.x)*.38;
   metal+=exp(-abs(p.y-rootY+4.)*1.8)*step(26.,q.x)*.14;
   vec2 twig=vec2(mod(p.x+halfSize.x,23.)-11.,p.y-rootY);
   metal+=exp(-line(twig,vec2(0.,0.),vec2(7.,-6.))*2.)*step(26.,q.x)*.3;
   metal+=exp(-line(twig,vec2(4.,-4.),vec2(3.,-8.))*2.)*step(26.,q.x)*.2;
   vec2 spore=vec2(twig.x,p.y-halfSize.y+5.);
   decoration+=exp(-dot(spore,spore)*.5)*step(26.,q.x)*(.6+.2*sin(time*.6+p.x*.07));
   metal+=exp(-abs(distance+3.)*2.)*.12;
  }else if(style==14){
   // Containment Bay: instrument rack, vents, phosphor rail, small hazard caps.
   vec2 q=vec2(halfSize.x-abs(p.x),p.y);
   vec3 brass=mix(ink,vec3(.71,.68,.40),.22);
   float cap=1.-smoothstep(17.,20.,q.x);
   body=mix(base,tint,.045)+brass*shine*.11;
   body=mix(body,mix(base,brass,.17+shine*.16),cap);
   float vents=step(4.,q.x)*step(q.x,13.)*step(abs(p.y),18.)*step(.5,fract((p.y+20.)/5.));
   body=mix(body,base*.4,vents*.9);
   vec2 screw=vec2(q.x-10.,abs(p.y)-halfSize.y+11.);
   float stud=1.-smoothstep(1.,2.5,length(screw));
   body=mix(body,brass,stud*.8);
   float hazard=step(3.,q.x)*step(q.x,17.)*step(abs(p.y+halfSize.y-16.),3.)*step(.5,fract((q.x+p.y)/6.));
   decoration=hazard*.65;
   decoration+=exp(-abs(p.y-halfSize.y+7.)*1.3)*step(22.,q.x)*.8;
   decoration+=exp(-abs(p.y-halfSize.y+4.)*1.8)*step(.7,fract((p.x+halfSize.x)/13.))*step(22.,q.x)*(.5+.3*sin(time+p.x*.025));
   metal=exp(-abs(p.y+halfSize.y-7.)*1.9)*step(22.,q.x)*.4;
   metal+=exp(-abs(distance+3.)*2.)*.18;rim=.75;
  }else if(style==13){
   // Harbour Cabinet: walnut grain, brass corner straps and sage inlay.
   vec2 q=vec2(halfSize.x-abs(p.x),p.y);
   vec3 brass=mix(ink,vec3(.67,.47,.22),.28);
   vec3 walnut=mix(base,vec3(.17,.105,.055),.3);
   float grain=pow(.5+.5*sin(p.y*2.2+sin(p.x*.035)*1.3+sin(p.x*.009)*2.),9.);
   body=walnut+brass*(grain*.045+shine*.085);
   float strap=(1.-smoothstep(14.,16.,q.x));
   body=mix(body,brass*(.29+.27*shine),strap);
   float rail=exp(-abs(abs(p.y)-halfSize.y+3.)*1.9);
   body+=brass*rail*.5;
   vec2 pin=vec2(q.x-8.,abs(p.y)-halfSize.y+9.);
   float stud=1.-smoothstep(1.2,2.3,length(pin));
   body=mix(body,brass,stud*.8);
   body-=base*exp(-abs(pin.y)*3.)*step(abs(pin.x),1.3)*.5;
   decoration=exp(-abs(p.y-halfSize.y+7.)*1.8)*step(20.,q.x)*.18;
   float medallion=abs(q.x-8.)+abs(p.y);
   decoration+=(1.-smoothstep(3.,4.5,medallion))*.8;
   metal=exp(-abs(distance+2.5)*1.9)*.2;
   rim=.75;
  }else if(style==12){
   // Platform Twelve: twin cream rails, enamel bays and amber signal lamps.
   vec2 q=vec2(halfSize.x-abs(p.x),p.y);
   body=mix(base,tint,.035)+ink*shine*.095;
   float rails=exp(-abs(abs(p.y)-halfSize.y+8.)*1.6)*step(23.,q.x);
   metal=rails*.8;
   metal+=step(.78,fract((p.x+halfSize.x)/11.))*exp(-abs(p.y-halfSize.y+4.)*1.4)*step(23.,q.x)*.22;
   float signalCase=roundBox(vec2(q.x-13.,p.y),vec2(7.,24.),6.);
   body=mix(body,base*.65,(1.-smoothstep(-.5,.7,signalCase))*.8);
   metal+=exp(-abs(signalCase)*1.4)*.6;
   vec2 lamp=vec2(q.x-13.,abs(p.y)-14.);
   decoration=(1.-smoothstep(2.,3.5,length(lamp)))*(.85+.12*sin(time*.6));
   decoration+=exp(-length(lamp)*.5)*.18;
   metal+=exp(-abs(q.x-13.)*.6)*exp(-abs(abs(p.y)-2.)*1.6)*.3;
   metal+=exp(-abs(distance+3.)*1.8)*.13;
   rim=.9;
  }else if(style==11){
   // Blue Vault: machined silver caps, glass cells and an illuminated sill.
   vec2 q=vec2(halfSize.x-abs(p.x),p.y);
   float cap=1.-smoothstep(15.,20.,q.x);
   float upper=clamp(1.-(p.y+halfSize.y)/(halfSize.y*2.),0.,1.);
   vec3 steel=mix(base,ink,.08+.38*pow(upper,3.)+.15*step(.5,upper));
   body=mix(body,steel,cap);
   metal=exp(-abs(p.y+halfSize.y-3.)*1.5)*.65;
   metal+=cap*(.03*sin(p.y*2.)+.04);
   vec2 screw=vec2(q.x-8.,abs(p.y)-halfSize.y+10.);
   metal+=(1.-smoothstep(1.,2.5,length(screw)))*.4;
   decoration=exp(-abs(p.y-halfSize.y+4.)*1.4)*.8*step(20.,q.x);
   decoration+=exp(-abs(q.x-8.)*1.3)*step(abs(p.y),14.)*.65;
   float polish=exp(-pow((p.x-halfSize.x*sin(time*.45))/45.,2.));
   metal+=polish*exp(-abs(p.y+halfSize.y-5.)*1.2)*.3;
   decoration+=exp(-abs(distance+4.)*1.5)*.12;
   rim=.85;
  }else if(style==0){
   decoration=(1.-smoothstep(.4,1.3,abs(p.y-halfSize.y+6.)))*.6;
   decoration+=step(.88,fract((p.x+halfSize.x)/14.))*(1.-smoothstep(1.,2.,abs(p.y+halfSize.y-7.)))*.4;
   vec2 q=vec2(halfSize.x-abs(p.x),p.y);
   decoration+=exp(-line(q,vec2(9.,-halfSize.y+12.),vec2(25.,0.))*1.5)*.55;
   decoration+=exp(-line(q,vec2(25.,0.),vec2(9.,halfSize.y-12.))*1.5)*.55;
   decoration+=exp(-abs(length(q-vec2(25.,0.))-3.)*1.7)*.8;
   float pulse=exp(-pow((p.x-mix(-halfSize.x,halfSize.x,fract(time*.18)))/8.,2.));
   decoration+=pulse*exp(-abs(p.y-halfSize.y+6.)*.8)*.7;rim=.65;
  }else if(style==1){
   decoration=exp(-abs(p.y+halfSize.y-3.)*.75)*(.3+.1*sin(p.x*.012+time*.6));rim=.35;
   body+=ink*pow(clamp(1.-abs(p.y+halfSize.y*.38)/18.,0.,1.),3.)*.055;
   decoration+=exp(-abs(distance+5.)*1.1)*.13;
   decoration+=exp(-abs(p.y-halfSize.y+4.)*.8)*(.2+.1*sin(p.x*.018+time*.5));
   metal=exp(-pow((abs(p.x)-halfSize.x+13.)/5.,2.))*exp(-p.y*p.y*.008)*.2;rim=.5;
  }else if(style==2){
   decoration=(1.-smoothstep(.5,1.6,abs(p.y-halfSize.y+5.)))*.75;
   decoration+=step(.92,fract((p.x+p.y)/17.))*step(halfSize.x-30.,abs(p.x))*.35;
   metal=step(.96,fract(p.x/36.))*.04;
   vec2 q=vec2(halfSize.x-abs(p.x),p.y);
   decoration+=step(q.x,27.)*step(.7,fract((p.y+time*3.)/11.))*.22;
   decoration+=exp(-abs(distance+4.)*1.4)*.2;
   metal+=exp(-length(vec2(q.x-13.,abs(p.y)-halfSize.y+14.))*1.4)*.6;rim=.7;
  }else if(style==3){
   decoration=exp(-abs(abs(p.x)+abs(p.y)-halfSize.x-halfSize.y+15.)*.8)*.7;
   metal=(sin(p.x*.07+p.y*.16+time*.3)*.5+.5)*.055;rim=.45;
   body+=ink*smoothstep(-3.,0.,p.x*.18+p.y)*.03;
   decoration+=exp(-abs(abs(p.x)+abs(p.y)-halfSize.x-halfSize.y+25.)*1.3)*.3;
   decoration+=exp(-abs(p.y+halfSize.y-5.)*1.2)*(.25+.25*pow(.5+.5*sin(p.x*.012-time*.7),6.));rim=.8;
  }else if(style==4){
   float wave=sin(p.x*.025+time*.7)*3.+sin(p.x*.06-time*.4)*2.;
   decoration=exp(-abs(p.y-halfSize.y+9.+wave)*.5)*.35;
   metal=pow(.5+.5*sin(p.x*.02+p.y*.08+time*.6),4.)*.06;rim=.5;
   decoration+=exp(-abs(p.y-halfSize.y+15.+wave*.7)*.5)*.15;
   vec2 q=vec2(halfSize.x-abs(p.x),p.y);
   for(int i=0;i<3;i++){
    vec2 bubble=q-vec2(15.+float(i)*5.,-16.+float(i)*13.);
    decoration+=exp(-abs(length(bubble)-2.-float(i))*.9)*.35;
   }
   body+=mix(tint,ink,.65)*shine*.08;rim=.65;
  }else if(style==5){
   body+=ink*(hash(floor(p*1.5))-.5)*.025;
   decoration=(1.-smoothstep(.5,1.5,abs(p.y-halfSize.y+6.+sin(p.x*.04)*.5)))*.45;
   vec2 stamp=p-vec2(halfSize.x-17.,0.);decoration+=exp(-abs(length(stamp)-7.)*1.4)*.5;
   float spindle=exp(-pow((abs(p.x)-halfSize.x+10.)/4.,2.));
   body=mix(body,mix(base,ink,.15),spindle*.5);
   decoration+=exp(-abs(abs(p.x)-halfSize.x+16.)*1.5)*.3;
   float horizon=halfSize.y-12.+sin(p.x*.035)*2.+sin(p.x*.077)*1.1;
   metal+=exp(-abs(p.y-horizon)*1.2)*.08;
   decoration+=exp(-abs(max(abs(stamp.x),abs(stamp.y))-5.)*1.7)*.35;rim=.35;
  }else if(style==6){
   body+=ink*(hash(vec2(floor(p.y*2.),0.))-.5)*.04;
   decoration=exp(-abs(p.y-halfSize.y+6.)*.9)*(.6+.15*sin(time+p.x*.05));
   vec2 rivet=vec2(abs(p.x)-halfSize.x+13.,abs(p.y)-halfSize.y+13.);
   metal+=(1.-smoothstep(1.,3.,length(rivet)))*.25;rim=.4;
   decoration+=exp(-abs(distance+5.)*1.4)*.28;
   vec2 q=vec2(halfSize.x-abs(p.x),p.y);
   float vent=step(q.x,31.)*step(12.,q.x)*step(.56,fract((p.y+halfSize.y)/8.));
   body=mix(body,base*.5,vent*.5);
   decoration+=vent*(.11+.06*sin(time*2.+p.y*.14));
   metal+=exp(-abs(p.y+halfSize.y-5.)*1.8)*.2;rim=.75;
  }else if(style==7){
   body=mix(body,ink,.055+shine*.07);
   decoration=0.12*pow(.5+.5*sin(p.x*.06+sin(p.y*.12)+time*.4),5.);
   vec2 star=vec2(mod(p.x+17.,47.)-23.5,p.y-halfSize.y+12.);
   decoration+=exp(-(abs(star.x)+abs(star.y))*.9)*(.4+.2*sin(time*1.4+p.x));rim=.48;
   decoration+=exp(-abs(distance+4.)*.9)*.18;
   vec2 pearl=vec2(halfSize.x-abs(p.x)-17.,p.y);
   metal+=exp(-dot(pearl,pearl)*.025)*.16;
   body+=mix(ink,tint,.25)*pow(shine,2.)*.09;
  }else if(style==8){
   metal=step(.94,fract((p.x-p.y)*.09))*.05;
   decoration=exp(-abs(p.y+halfSize.y-4.)*1.3)*.4+exp(-abs(p.y-halfSize.y+5.)*1.3)*.25;rim=.38;
   float facet=clamp((p.y+halfSize.y)/(halfSize.y*2.),0.,1.);
   body+=ink*abs(facet-.5)*.055;
   decoration+=exp(-abs(abs(p.x)+abs(p.y)-halfSize.x-halfSize.y+19.)*1.1)*.4;
   metal+=exp(-pow((p.x-halfSize.x*sin(time*.22))/40.,2.))*exp(-abs(p.y+halfSize.y-3.))*.25;rim=.6;
  }else if(style==10){
   // Brass caps, inset stone, a traveling polish and a lantern-cut diamond.
   vec2 q=vec2(halfSize.x-abs(p.x),p.y);
   float cap=1.-smoothstep(19.,30.,q.x);
   float grain=sin(p.x*.09+p.y*.18+sin(p.y*.13)*2.);
   body+=ink*grain*.008;
   body=mix(body,mix(base,tint,.28)+ink*shine*.12,cap*.85);
   float curl=abs(length((q-vec2(19.,-8.))/vec2(1.,1.25))-8.);
   float engraving=exp(-curl*1.8)*step(-18.,p.y)*step(p.y,8.);
   engraving+=exp(-line(q,vec2(15.,0.),vec2(27.,halfSize.y-8.))*1.7);
   decoration=engraving*.32*cap;
   vec2 rivet=vec2(q.x-16.,abs(p.y)-halfSize.y+14.);
   metal+=(1.-smoothstep(1.,2.8,length(rivet)))*.36;
   decoration+=exp(-abs(distance+4.7)*1.4)*.24;
   gildedSweep=exp(-pow((p.x-mix(-halfSize.x-55.,halfSize.x+55.,fract(time*.105)))/35.,2.));
   decoration+=exp(-abs(p.y+halfSize.y-4.)*1.1)*(.16+.23*gildedSweep);
   vec2 gem=p-vec2(0.,halfSize.y-5.);
   jewel=1.-smoothstep(3.3,5.,abs(gem.x)+abs(gem.y));
   jewelHalo=exp(-length(gem)*.16)*(.7+.15*sin(time*1.6));
   decoration+=jewelHalo*.18;
   decoration+=exp(-abs(distance+7.)*1.2)*step(.7,fract((p.x+halfSize.x)/7.))*.16;
   body+=ink*pow(noise(p*.06),7.)*.018;
   rim=.8;
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
   decoration+=exp(-abs(distance+4.)*1.4)*.14;
   float vineCurve=halfSize.y-6.+sin(p.x*.019)*1.5;
   decoration+=exp(-abs(p.y-vineCurve)*1.4)*.16;
   vec2 moon=p-vec2(0.,halfSize.y-8.);
   float crescent=max(length(moon)-4.,-(length(moon-vec2(2.,-1.))-3.8));
   decoration+=(1.-smoothstep(-.4,.6,crescent))*.5;
   for(int i=0;i<3;i++){
    vec2 mote=q-vec2(26.+float(i)*4.,sin(time*.5+float(i)*2.)*22.);
    decoration+=exp(-dot(mote,mote)*.4)*(.15+.1*sin(time+float(i)));
   }
  }
 }else{
  body=mix(base,tint,.08+emphasis*.14)+ink*shine*.045;
  rim=.08+emphasis*.25;
  decoration=exp(-abs(p.y-halfSize.y+3.)*1.7)*(.25+.4*emphasis);
  if(style==20){
   vec3 brass=mix(ink,vec3(.7804,.6078,.3804),.65);
   body=mix(base,tint,.04+emphasis*.1);rim=0.;
   body+=brass*exp(-abs(distance+3.)*1.9)*.2;
   decoration=exp(-abs(p.y-halfSize.y+5.)*2.)*step(abs(p.x),halfSize.x-9.)*(.6+emphasis*.4);
  }else if(style==19){
   body=mix(base,tint,.06+emphasis*.1)+ink*shine*.13;rim=.4+emphasis*.4;
   decoration=exp(-abs(p.y-halfSize.y+5.)*1.8)*step(abs(p.x),halfSize.x-10.)*(.45+emphasis*.4);
   metal=exp(-abs(distance+3.)*1.8)*.18;
  }
  if(style==18){
   vec3 brass=mix(tint,ink,.65);
   body=mix(base,tint,.035+emphasis*.09)+ink*shine*.06;rim=.2+emphasis*.35;
   body+=brass*exp(-abs(p.y+halfSize.y-3.)*2.)*step(abs(p.x),halfSize.x-5.)*.45;
   float strip=step(abs(p.y-halfSize.y+8.),4.)*step(abs(p.x),halfSize.x-5.);
   body=mix(body,base*.65,strip);
   decoration=0.;
   for(int i=-1;i<=1;i++){
    vec2 knob=p-vec2(float(i)*6.,halfSize.y-8.);
    body+=brass*(1.-smoothstep(1.,1.6,length(knob)))*.7;
   }
   vec2 lamp=p-vec2(halfSize.x-8.,halfSize.y-8.);
   decoration=exp(-dot(lamp,lamp)*.6)*(.6+emphasis*.3);
  }
  if(style==17){
   body=mix(base,tint,.04+emphasis*.08)+ink*shine*.07;rim=.25+emphasis*.4;
   decoration=exp(-abs(p.y+halfSize.y-5.)*1.8)*step(abs(p.x),halfSize.x-8.)*(.35+emphasis*.35);
   body+=tint.brg*exp(-abs(p.y-halfSize.y+5.)*1.8)*step(abs(p.x),halfSize.x-8.)*(.45+emphasis*.4);
   for(int i=0;i<2;i++){
    float x=halfSize.x-10.-float(i)*4.;
    body+=tint.brg*exp(-line(p,vec2(x-2.,halfSize.y-10.),vec2(x,halfSize.y-15.))*2.)*.35;
   }
  }
  if(style==16){
   body=mix(base,tint,.035+emphasis*.12);rim=0.;
   decoration=exp(-abs(p.y-halfSize.y+6.)*2.)*step(abs(p.x),halfSize.x-7.)*(.25+emphasis*.55);
  }
  if(style==15){
   body=mix(base,tint,.08+emphasis*.14)+ink*shine*.07;rim=.35+emphasis*.4;
   float root=halfSize.y-7.+2.*pow(p.x/max(1.,halfSize.x),2.);
   decoration=exp(-abs(p.y-root)*1.7)*step(abs(p.x),halfSize.x-9.)*(.3+emphasis*.3);
   for(int i=-1;i<=1;i++){
    vec2 spore=p-vec2(float(i)*5.,halfSize.y-8.);
    decoration+=exp(-dot(spore,spore)*.9)*(.45+emphasis*.25);
   }
   metal=exp(-abs(distance+3.)*2.)*.12;
  }
  if(style==14){
   body=mix(base,tint,.045+emphasis*.1)+ink*shine*.08;
   rim=.45+emphasis*.4;
   vec2 display=p-vec2(0.,halfSize.y-8.);
   float plate=roundBox(display,vec2(max(2.,halfSize.x-9.),3.5),1.);
   body=mix(body,base*.5,1.-smoothstep(-.5,.5,plate));
   decoration=exp(-abs(plate)*2.)*.35;
   decoration+=step(abs(display.y),1.)*step(abs(display.x),halfSize.x-13.)*step(.45,fract((display.x+halfSize.x)/8.))*(.55+emphasis*.35);
   metal=exp(-abs(p.y+halfSize.y-3.)*1.8)*.25;
  }
  if(style==13){
   body=mix(base,tint,.06+emphasis*.12)+ink*shine*.07;
   rim=.35+emphasis*.45;
   metal=exp(-abs(distance+3.)*1.8)*.24;
   // A small horizontal brass drawer pull, under each application icon.
   float pull=line(p,vec2(-5.,halfSize.y-7.),vec2(5.,halfSize.y-7.));
   metal+=(1.-smoothstep(.5,1.4,pull))*.6;
   decoration=exp(-abs(p.y+halfSize.y-3.)*2.)*emphasis*.35;
  }
  if(style==12){
   body=mix(base,tint,.055)+ink*shine*.11;
   rim=.55+emphasis*.35;
   decoration=exp(-abs(p.y-halfSize.y+5.)*1.6)*(.3+emphasis*.5);
   metal=exp(-abs(p.y+halfSize.y-3.)*1.8)*.28;
  }
  if(style==11){
   body=mix(base,tint,.12)+ink*shine*.16;
   body+=ink*step(.5,1.-uv.y)*.035;
   rim=.5+emphasis*.4;
   decoration=exp(-abs(p.y-halfSize.y+4.)*1.7)*(.4+emphasis*.5);
  }
  if(style==10){
   rim=.2+emphasis*.6;
   decoration*=.7;
   decoration+=exp(-abs(distance+3.)*1.9)*emphasis*.18;
  }
 }
 vec3 surface=body+ink*metal+tint*decoration;
 surface=mix(surface,mix(tint,ink,.3),border*rim);
 if(style==20)surface=mix(surface,mix(ink,vec3(.7804,.6078,.3804),.65),border*(part==0?.85:.4+emphasis*.5));
 if(style==16){
  float bevel=1.-smoothstep(1.2,2.5,-distance);
  float upper=step(halfSize.x+p.x,halfSize.x-p.x)*step(halfSize.x+p.x,halfSize.y-p.y);
  upper=max(upper,step(halfSize.y+p.y,min(halfSize.x-p.x,halfSize.y-p.y)));
  if(part==1)upper=1.-upper;
  vec3 edgeColor=mix(base*.3,mix(base,vec3(1.),.65),upper);
  surface=mix(surface,edgeColor,bevel);
 }
 if(style==10&&part==0){
  surface+=mix(tint,ink,.65)*border*gildedSweep*.55;
  surface=mix(surface,mix(tint,ink,.55),jewel);
 }
 float alpha=mask*(part==1?.28+emphasis*.18:.9);
 vec3 rgb=surface*alpha;
 float outside=shadow*(1.-mask);
 if(style==10){
  float glow=(exp(-max(distance,0.)*.46)*(.035+emphasis*.08)+jewelHalo*.1)*(1.-mask);
  rgb+=tint*glow;
  outside+=glow;
 }
 alpha+=outside;
 if(reveal<.999){
  float cross=(edge>=2)?coord.x:coord.y;
  float along=(edge>=2)?coord.y*dimensions.y:coord.x*dimensions.x;
  if(edge==1||edge==2)cross=1.-cross;
  float front=(1.-reveal)*1.16-.08;
  float grain=noise(vec2(along*.10,time*.7))*0.06+sin(along*.052+time*2.)*.015;
  float burnEdge=cross+grain-front;
  float remaining=smoothstep(-.015,.018,burnEdge);
  float hot=exp(-abs(burnEdge)*85.)*smoothstep(0.,.08,reveal)*smoothstep(0.,.06,1.-reveal)*mask;
  rgb=rgb*remaining*(1.-exp(-max(burnEdge,0.)*30.)*.55);
  vec3 ember=mix(tint,vec3(1.,.32,.045),.45);
  rgb+=mix(ember,vec3(1.,.88,.5),.35)*hot*.85;
  alpha=clamp(alpha*remaining+hot*.65,0.,1.);
 }
 fragColor=vec4(rgb,alpha)*opacity;
})";
}

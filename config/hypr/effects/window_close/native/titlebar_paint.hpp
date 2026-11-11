// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "titlebar_layout.hpp"
#include <cairo/cairo.h>
#include <pango/pangocairo.h>
#include <string>

namespace WindowButtons::Titlebar {
using RGB=std::array<double,3>;
struct Palette {
    RGB background{.08,.11,.13},foreground{.94,.96,.98},accent{.22,.66,1};
};
inline RGB mix(RGB a,RGB b,double t){for(int i=0;i<3;++i)a[i]=a[i]*(1-t)+b[i]*t;return a;}
inline void color(cairo_t* cr,RGB c,double alpha=1){cairo_set_source_rgba(cr,c[0],c[1],c[2],alpha);}
inline void paint(cairo_t* cr,double width,double barHeight,int size,const std::string& title,
                  const Palette& palette,bool active,bool restore,int hovered,double rounding){
    const auto boxes=layout(width,barHeight,size);
    const double radius=std::clamp(rounding,0.,std::min(width/2,barHeight/2));
    const auto bg=active?mix(palette.background,palette.accent,.13):palette.background;
    // Only round the outer top corners; the bottom meets the client surface.
    cairo_new_path(cr);cairo_move_to(cr,0,barHeight);cairo_line_to(cr,0,radius);
    if(radius>0)cairo_arc(cr,radius,radius,radius,M_PI,1.5*M_PI);
    cairo_line_to(cr,width-radius,0);
    if(radius>0)cairo_arc(cr,width-radius,radius,radius,1.5*M_PI,2*M_PI);
    cairo_line_to(cr,width,barHeight);cairo_close_path(cr);
    color(cr,bg);cairo_fill(cr);
    color(cr,palette.accent,active?.75:.25);cairo_rectangle(cr,0,barHeight-1,width,1);cairo_fill(cr);
    if(boxes.title.w>4){
        auto text=pango_cairo_create_layout(cr);
        auto font=pango_font_description_from_string("Sans Medium");
        pango_font_description_set_absolute_size(font,std::clamp(size*.66,11.,18.)*PANGO_SCALE);
        pango_layout_set_font_description(text,font);pango_font_description_free(font);
        pango_layout_set_text(text,title.c_str(),int(title.size())); // Plain text, never markup.
        pango_layout_set_single_paragraph_mode(text,true);
        pango_layout_set_width(text,int(boxes.title.w*PANGO_SCALE));
        pango_layout_set_ellipsize(text,PANGO_ELLIPSIZE_END);
        int tw,th;pango_layout_get_pixel_size(text,&tw,&th);
        cairo_save(cr);cairo_rectangle(cr,boxes.title.x,0,boxes.title.w,barHeight);cairo_clip(cr);
        cairo_move_to(cr,boxes.title.x,std::round((barHeight-th)/2));
        color(cr,palette.foreground,active?1:.72);pango_cairo_show_layout(cr,text);
        cairo_restore(cr);g_object_unref(text);
    }
    for(int i=0;i<4;++i){
        const auto& b=boxes.buttons[i];if(b.w<=0)continue;
        cairo_save(cr);cairo_translate(cr,b.x,b.y);cairo_scale(cr,b.w/24,b.h/24);
        if(hovered==i){
            color(cr,i==3?RGB{.8,.17,.22}:palette.accent,i==3?.92:.28);
            cairo_rectangle(cr,0,0,24,24);cairo_fill(cr);
        }
        color(cr,hovered==3?RGB{1,1,1}:palette.foreground,active||hovered==i?1:.8);
        cairo_set_line_width(cr,1.8);cairo_set_line_cap(cr,CAIRO_LINE_CAP_ROUND);cairo_set_line_join(cr,CAIRO_LINE_JOIN_ROUND);
        if(i==0){
            for(int n=0;n<=32;++n){const double a=n*M_PI/16,r=(n%4==0||n%4==3)?8:6;
                if(!n)cairo_move_to(cr,12+r*std::cos(a),12+r*std::sin(a));
                else cairo_line_to(cr,12+r*std::cos(a),12+r*std::sin(a));}
            cairo_close_path(cr);cairo_new_sub_path(cr);cairo_arc(cr,12,12,2.5,0,2*M_PI);
        }else if(i==1){cairo_move_to(cr,6,16);cairo_line_to(cr,18,16);}
        else if(i==2){
            if(restore){cairo_move_to(cr,9,8);cairo_line_to(cr,9,5);cairo_line_to(cr,19,5);cairo_line_to(cr,19,15);cairo_line_to(cr,16,15);cairo_rectangle(cr,5,9,10,10);}
            else cairo_rectangle(cr,6,6,12,12);
        }else{cairo_move_to(cr,6,6);cairo_line_to(cr,18,18);cairo_move_to(cr,18,6);cairo_line_to(cr,6,18);}
        cairo_stroke(cr);cairo_restore(cr);
    }
}
}

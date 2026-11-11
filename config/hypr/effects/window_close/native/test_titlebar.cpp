// SPDX-License-Identifier: GPL-2.0-or-later
#include "titlebar_paint.hpp"
#include "policies.hpp"
#include <cassert>
#include <iostream>

int main(int argc,char** argv){
    using namespace WindowButtons;
    assert(Titlebar::height(18)==30);
    // Content starts at y=0; every button remains in the reserved negative-Y
    // strip, even for tiny windows, huge buttons and fractional output scales.
    size_t checks=0;
    for(int size=10;size<=64;++size)for(double width:{24.,85.,120.,640.,2560.,7680.})
        for(double scale:{1.,1.25,1.5,2.}){
            const auto height=Titlebar::height(size);
            const auto layout=Titlebar::layout(width,height,size);
            double right=0;
            for(int i=0;i<4;++i){const auto& b=layout.buttons[i];
                assert(b.x>=right-1e-8&&b.y>=0&&b.w>0&&b.h>0);
                assert(b.x+b.w<=width+1e-8&&b.y+b.h<=height);
                assert((b.y-height+b.h)*scale<=0); // Never overlaps client pixels.
                assert(Titlebar::hit(layout,b.x+b.w/2,b.y+b.h/2)==i);
                right=b.x+b.w;
            }
            assert(layout.title.x+layout.title.w<=layout.buttons[0].x+1e-8);
            assert(Titlebar::hit(layout,-1,0)==-1);
            assert(Titlebar::hit(layout,width+1,height)==-1);
            ++checks;
        }
    auto old=parseJson(R"({"mode":"auto","size":18,"anchor":"top-right","x":8,"y":8,"proximity":80})");
    auto rule=readRule(old.get());assert(rule.titlebar.value_or(true));
    rule.titlebar=false;auto encoded=ruleJson(rule);
    assert(readRule(encoded.get()).titlebar==false);
    for(auto bad:{json_object_new_int(0),json_object_new_string("false"),json_object_new_null()}){
        json_object_object_add(encoded.get(),"titlebar",bad);
        bool rejected=false;try{readRule(encoded.get());}catch(const std::runtime_error&){rejected=true;}
        assert(rejected);
    }
    // Render the production artwork, rather than a UI mock. Text includes
    // Unicode and markup-like characters and must stay inside its title slot.
    auto surface=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,1100,440);
    auto cr=cairo_create(surface);cairo_set_source_rgb(cr,.05,.05,.05);cairo_paint(cr);
    Titlebar::Palette palette{{.23,.17,.13},{.95,.9,.79},{.86,.71,.42}};
    int y=12;
    for(int size:{10,18,32,64}){
        cairo_save(cr);cairo_translate(cr,12,y);
        Titlebar::paint(cr,1076,Titlebar::height(size),size,"Fusion Files — This PC · café · 窗口 <b>plain text</b>",palette,true,true,3,8);
        cairo_restore(cr);y+=Titlebar::height(size)+22;
    }
    cairo_destroy(cr);cairo_surface_flush(surface);
    assert(cairo_surface_status(surface)==CAIRO_STATUS_SUCCESS);
    if(argc>1)assert(cairo_surface_write_to_png(surface,argv[1])==CAIRO_STATUS_SUCCESS);
    cairo_surface_destroy(surface);
    std::cout<<checks<<" title-bar geometry cases, rule compatibility and production artwork passed\n";
}

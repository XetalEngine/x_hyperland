// SPDX-License-Identifier: GPL-2.0-or-later
// An unfocused Wayland clipboard observer. Payloads go only to the owning UI's
// pipe; this process never saves or logs clipboard contents.
#include "wlr-data-control-client-protocol.h"
#include "formats.hpp"
#include <wayland-client.h>
#include <poll.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <chrono>
#include <map>
#include <memory>

using Clock=std::chrono::steady_clock;
struct Offer {zwlr_data_control_offer_v1* object;std::vector<std::string> formats;bool overflow=false;};
std::map<zwlr_data_control_offer_v1*,std::unique_ptr<Offer>> offers;
wl_display* display=nullptr;
wl_seat* seat=nullptr;
zwlr_data_control_manager_v1* manager=nullptr;
bool running=true;
int input=-1;
std::string mime,payload;
Clock::time_point deadline;
constexpr size_t IMAGE_LIMIT=8*1024*1024,TEXT_LIMIT=1024*1024;
void cancel(){if(input>=0)close(input);input=-1;payload.clear();mime.clear();}
void destroy(zwlr_data_control_offer_v1* offer){if(offer&&offers.erase(offer))zwlr_data_control_offer_v1_destroy(offer);}
void format(void* data,zwlr_data_control_offer_v1*,const char* value){
    auto* offer=static_cast<Offer*>(data);auto& list=offer->formats;
    if(list.size()<128&&std::strlen(value)<256)list.emplace_back(value);
    else offer->overflow=true;
}
const zwlr_data_control_offer_v1_listener offerListener{format};
void offered(void*,zwlr_data_control_device_v1*,zwlr_data_control_offer_v1* object){
    if(offers.size()>=128){running=false;return;}
    auto offer=std::make_unique<Offer>();offer->object=object;
    zwlr_data_control_offer_v1_add_listener(object,&offerListener,offer.get());offers.emplace(object,std::move(offer));
}
void selection(void*,zwlr_data_control_device_v1*,zwlr_data_control_offer_v1* object){
    cancel();
    auto it=offers.find(object);if(it==offers.end())return;
    const auto chosen=it->second->overflow?std::string{}:Clipboard::choose(it->second->formats);
    if(!chosen.empty()){
        int fds[2];
        if(pipe2(fds,O_CLOEXEC)==0){
            input=fds[0];fcntl(input,F_SETFL,fcntl(input,F_GETFL)|O_NONBLOCK);
            mime=chosen.starts_with("image/")?chosen:"text/plain;charset=utf-8";
            deadline=Clock::now()+std::chrono::seconds(4);
            zwlr_data_control_offer_v1_receive(object,chosen.c_str(),fds[1]);close(fds[1]);
        }
    }
    destroy(object);
}
void finished(void*,zwlr_data_control_device_v1*){running=false;}
void primary(void*,zwlr_data_control_device_v1*,zwlr_data_control_offer_v1* object){destroy(object);}
const zwlr_data_control_device_v1_listener deviceListener{offered,selection,finished,primary};
void seatCapabilities(void*,wl_seat*,uint32_t){}
void seatName(void*,wl_seat*,const char*){}
const wl_seat_listener seatListener{seatCapabilities,seatName};
void global(void*,wl_registry* registry,uint32_t name,const char* interface,uint32_t version){
    if(std::strcmp(interface,"wl_seat")==0&&!seat){
        seat=static_cast<wl_seat*>(wl_registry_bind(registry,name,&wl_seat_interface,1));
        wl_seat_add_listener(seat,&seatListener,nullptr);
    }
    if(std::strcmp(interface,"zwlr_data_control_manager_v1")==0&&!manager)
        manager=static_cast<zwlr_data_control_manager_v1*>(wl_registry_bind(registry,name,&zwlr_data_control_manager_v1_interface,std::min(version,2u)));
}
void removed(void*,wl_registry*,uint32_t){}
const wl_registry_listener registryListener{global,removed};
void receive(){
    char chunk[65536];
    while(input>=0){
        const auto count=read(input,chunk,sizeof(chunk));
        if(count>0){
            if(payload.size()+count>(mime.starts_with("image/")?IMAGE_LIMIT:TEXT_LIMIT)){cancel();return;}
            payload.append(chunk,size_t(count));continue;
        }
        if(count==0){
            if(!payload.empty()){
                // Canonical MIME followed by a byte count, then exactly that
                // many bytes. Never delimit payloads by newline.
                if(std::printf("%s %zu\n",mime.c_str(),payload.size())<0 ||
                   std::fwrite(payload.data(),1,payload.size(),stdout)!=payload.size() || std::fflush(stdout))running=false;
            }
            cancel();return;
        }
        if(errno==EINTR)continue;
        if(errno!=EAGAIN&&errno!=EWOULDBLOCK)cancel();
        return;
    }
}
int main(){
    display=wl_display_connect(nullptr);if(!display)return 1;
    auto registry=wl_display_get_registry(display);wl_registry_add_listener(registry,&registryListener,nullptr);
    if(wl_display_roundtrip(display)<0||!manager||!seat){wl_display_disconnect(display);return 2;}
    auto device=zwlr_data_control_manager_v1_get_data_device(manager,seat);
    zwlr_data_control_device_v1_add_listener(device,&deviceListener,nullptr);
    while(running){
        while(wl_display_prepare_read(display)!=0){if(wl_display_dispatch_pending(display)<0){running=false;break;}}
        if(!running)break;
        const int flushed=wl_display_flush(display);
        if(flushed<0&&errno!=EAGAIN){wl_display_cancel_read(display);break;}
        pollfd fds[]={{wl_display_get_fd(display),short(POLLIN|(flushed<0?POLLOUT:0)),0},{input,POLLIN,0}};
        const int result=poll(fds,2,input>=0?100: -1);
        if(result<0){wl_display_cancel_read(display);if(errno==EINTR)continue;break;}
        if(fds[0].revents&POLLIN){if(wl_display_read_events(display)<0)break;}
        else wl_display_cancel_read(display);
        if(fds[0].revents&(POLLERR|POLLHUP))break;
        // Selection changes cancel an obsolete read before it can be emitted.
        const int previous=input;
        if(wl_display_dispatch_pending(display)<0)break;
        if(input>=0&&input==previous&&fds[1].revents&(POLLIN|POLLHUP|POLLERR))receive();
        if(input>=0&&Clock::now()>deadline)cancel();
    }
    cancel();while(!offers.empty())destroy(offers.begin()->first);
    zwlr_data_control_device_v1_destroy(device);zwlr_data_control_manager_v1_destroy(manager);
    wl_seat_destroy(seat);wl_registry_destroy(registry);wl_display_disconnect(display);return 0;
}

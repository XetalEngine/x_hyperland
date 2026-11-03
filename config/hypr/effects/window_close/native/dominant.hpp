// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>

namespace WindowButtons {
// Count nearby colors together, then average only the winning bucket. Text,
// icons and antialiasing must not brighten the background as a mean would.
inline std::optional<std::array<double,3>> dominant(const uint8_t* rgba,size_t pixels){
    struct Bucket {uint32_t count=0,r=0,g=0,b=0;};
    std::array<Bucket,4096> bins{};
    size_t winner=0;
    for(size_t i=0;i<pixels;++i){
        const auto* p=rgba+4*i;if(p[3]<128)continue;
        const size_t index=(p[0]>>4)*256+(p[1]>>4)*16+(p[2]>>4);
        auto& bin=bins[index];++bin.count;bin.r+=p[0];bin.g+=p[1];bin.b+=p[2];
        if(bin.count>bins[winner].count)winner=index;
    }
    const auto& bin=bins[winner];if(!bin.count)return {};
    const double divisor=255.*bin.count;
    return std::array<double,3>{bin.r/divisor,bin.g/divisor,bin.b/divisor};
}
}

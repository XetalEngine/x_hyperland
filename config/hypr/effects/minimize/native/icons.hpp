// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstdint>
#include <format>
#include <string>
namespace Minimize {
inline std::string iconKey(const std::string& name) {
    uint64_t hash=14695981039346656037ULL;
    for(unsigned char ch:name){if(ch>='A' && ch<='Z')ch+=32;hash=(hash^ch)*1099511628211ULL;}
    return std::format("{:016x}.png",hash);
}
}

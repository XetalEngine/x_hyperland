// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <string>
#include <vector>
#include <algorithm>
namespace Clipboard {
inline std::string choose(const std::vector<std::string>& offers) {
    auto has=[&](const std::string& mime){return std::find(offers.begin(),offers.end(),mime)!=offers.end();};
    // Never turn a file cut/copy into text, or retain a password-manager offer.
    for(const auto& mime:offers)
        if(mime=="text/uri-list" || mime=="x-special/gnome-copied-files" ||
           mime=="application/x-kde-cutselection" || mime=="x-kde-passwordManagerHint" ||
           mime=="application/x-keepassxc" || mime=="application/x-kde-passwordManagerHint")return {};
    for(const auto* mime:{"image/png","image/jpeg","image/webp","text/plain;charset=utf-8","text/plain;charset=UTF-8","UTF8_STRING","text/plain"})
        if(has(mime))return mime;
    return {};
}
}

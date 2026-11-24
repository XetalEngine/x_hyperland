// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "policies.hpp"

namespace TitleProtection {
inline bool readEnabled(const std::filesystem::path& path) {
    if(!std::filesystem::exists(path))return true;
    if(std::filesystem::file_size(path)>1024)throw std::runtime_error("Window behavior settings are too large");
    std::ifstream file(path);if(!file)throw std::runtime_error("Cannot read window behavior settings");
    const std::string text((std::istreambuf_iterator<char>(file)),{});
    auto doc=WindowButtons::parseJson(text);
    if(json_object_object_length(doc.get())!=1)throw std::runtime_error("Invalid window behavior settings");
    return json_object_get_boolean(WindowButtons::field(doc.get(),"titlebar_protection",json_type_boolean));
}
}

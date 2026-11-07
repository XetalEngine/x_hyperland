// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 XetalEngine.
#pragma once
#include <cxxabi.h>
#include <cstdlib>
#include <memory>
#include <string>

namespace Minimize {
inline bool symbolMatches(const std::string& mangled, const std::string& expected) {
    // Hyprland pairs two separate nm outputs by line number.
    // Demangle the actual candidate instead of trusting that pairing.
    int status = -1;
    std::unique_ptr<char, decltype(&std::free)> name(
        abi::__cxa_demangle(mangled.c_str(), nullptr, nullptr, &status), &std::free);
    return status == 0 && name && std::string(name.get()).find(expected) != std::string::npos;
}
}

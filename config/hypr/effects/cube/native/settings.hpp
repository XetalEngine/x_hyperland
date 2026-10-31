// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 XetalEngine.
#pragma once
#include "math.hpp"
#include <json-c/json.h>
#include <filesystem>
#include <fstream>
#include <memory>
#include <regex>
#include <stdexcept>
#include <string>

namespace Cube {
// json-c has no process-global GType registrations. Settings and status remain
// safe when Hyprland unloads this shared library and loads a different build.
using Json = std::unique_ptr<json_object, decltype(&json_object_put)>;
struct Settings {
    bool rotateWorkspace = false;
    bool enabled = true, windows3d = true, skyMotion = true;
    double opacity = .85, zoom = .64, sensitivity = .35, duration = 220, skySpeed = 0, windowDepth = .3;
    int skyMode = 1, minimum = 60, spacing = 10, previewFps = 60;
    Color top = {.035, .04, .065, 1}, bottom = {.14, .075, .095, 1}, cap = {.09, .10, .14, 1}, edge = {.898, .224, .271, 1},
          windowColor = {.18, .19, .24, 1};
    std::string topImage, bottomImage, skyImage;
};
inline Settings readSettings(const std::filesystem::path &path) {
    std::ifstream file(path, std::ios::binary);
    if (!file)
        throw std::runtime_error("Cannot read Desktop Cube settings");
    std::string data(16385, '\0');
    file.read(data.data(), data.size());
    data.resize(file.gcount());
    if (data.size() > 16384 || data.find('\0') != std::string::npos)
        throw std::runtime_error("Invalid Desktop Cube settings size or text");
    std::unique_ptr<json_tokener, decltype(&json_tokener_free)> parser(json_tokener_new(), json_tokener_free);
    json_tokener_set_flags(parser.get(), JSON_TOKENER_STRICT | JSON_TOKENER_VALIDATE_UTF8);
    Json root(json_tokener_parse_ex(parser.get(), data.c_str(), data.size() + 1), json_object_put);
    if (json_tokener_get_error(parser.get()) != json_tokener_success || !json_object_is_type(root.get(), json_type_object))
        throw std::runtime_error("Invalid Desktop Cube JSON settings");
    auto j = root.get();
    json_object *fpsValue = nullptr;
    const bool hasFps = json_object_object_get_ex(j, "preview_fps", &fpsValue);
    json_object *animationValue = nullptr;
    const bool hasAnimation = json_object_object_get_ex(j, "workspace_animation", &animationValue);
    if (json_object_object_length(j) != 20 + int(hasFps) + int(hasAnimation))
        throw std::runtime_error("Incomplete Desktop Cube settings");
    auto member = [&](const char *key) {
        json_object *value = nullptr;
        if (!json_object_object_get_ex(j, key, &value))
            throw std::runtime_error(std::string("Missing setting: ") + key);
        return value;
    };
    auto string = [&](const char *key) {
        auto n = member(key);
        if (!json_object_is_type(n, json_type_string))
            throw std::runtime_error("Invalid cube string");
        return std::string(json_object_get_string(n), json_object_get_string_len(n));
    };
    Settings s;
    auto number = [&](const char *key, double lo, double hi) {
        auto n = member(key);
        if (!json_object_is_type(n, json_type_int) && !json_object_is_type(n, json_type_double))
            throw std::runtime_error(std::string("Invalid number: ") + key);
        double v = json_object_get_double(n);
        if (!std::isfinite(v) || v < lo || v > hi)
            throw std::runtime_error(std::string("Out of range: ") + key);
        return v;
    };
    auto boolean = [&](const char *key) {
        auto n = member(key);
        if (!json_object_is_type(n, json_type_boolean))
            throw std::runtime_error("Invalid cube switch");
        return bool(json_object_get_boolean(n));
    };
    auto integer = [&](const char *key, int lo, int hi) {
        auto n = number(key, lo, hi);
        if (n != std::floor(n))
            throw std::runtime_error("Cube option requires a whole number");
        return int(n);
    };
    auto color = [&](const char *key) {
        auto node = member(key);
        if (!json_object_is_type(node, json_type_array))
            throw std::runtime_error("Invalid cube color");
        auto v = node;
        if (json_object_array_length(v) != 4)
            throw std::runtime_error("Invalid cube color");
        Color c;
        for (int i = 0; i < 4; i++) {
            auto value = json_object_array_get_idx(v, i);
            if (!json_object_is_type(value, json_type_double) && !json_object_is_type(value, json_type_int))
                throw std::runtime_error("Invalid cube color");
            double n = json_object_get_double(value);
            if (!std::isfinite(n) || n < 0 || n > 1)
                throw std::runtime_error("Invalid cube color");
            c[i] = n;
        }
        return c;
    };
    auto image = [&](const char *key) {
        auto v = string(key);
        if (!v.empty() && !std::regex_match(v, std::regex("images/[a-f0-9]{64}\\.png")))
            throw std::runtime_error("Invalid cube artwork path");
        return v;
    };
    if (hasAnimation) {
        auto animation = string("workspace_animation");
        if (animation != "cube" && animation != "standard") throw std::runtime_error("Unknown workspace animation");
        s.rotateWorkspace = animation == "cube";
    }
    s.enabled = boolean("enabled");
    s.windows3d = boolean("windows_3d");
    s.skyMotion = boolean("sky_motion");
    s.opacity = number("wall_opacity", 0, 1);
    s.zoom = number("zoom", .25, .95);
    s.sensitivity = number("sensitivity", .05, 2);
    s.duration = integer("duration", 0, 1000);
    if (hasFps)
        s.previewFps = integer("preview_fps", 1, 144);
    s.skySpeed = number("sky_speed", -20, 20);
    s.minimum = integer("min_cube_size", 10, 100);
    s.spacing = integer("window_space", 0, 50);
    s.windowDepth = number("window_depth", 0, 1);
    s.top = color("sky_top");
    s.bottom = color("sky_bottom");
    s.cap = color("cap_color");
    s.edge = color("edge_color");
    s.windowColor = color("window_color");
    s.topImage = image("top_image");
    s.bottomImage = image("bottom_image");
    s.skyImage = image("sky_image");
    auto mode = string("sky_mode");
    if (mode != "gradient" && mode != "image" && mode != "sky")
        throw std::runtime_error("Unknown cube background");
    s.skyMode = mode == "sky" ? 3 : mode == "image" ? 2 : 1;
    return s;
}

} // namespace Cube

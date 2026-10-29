// SPDX-License-Identifier: GPL-2.0-or-later
// Cube geometry and 3D layer spacing adapted from Compiz cube.c and 3d.c.
// Copyright Compiz contributors; see README.md and COPYING.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <vector>
#include <set>

namespace Cube {
using Color = std::array<float, 4>;
constexpr double PI = 3.14159265358979323846;
struct V3 {
    double x = 0, y = 0, z = 0;
};
struct UV {
    double u = 0, v = 0;
};
inline UV pictureUV(double u, double v, double screenAspect, double imageAspect, double yaw, double pitch, bool moving) {
    // Keep ordinary pictures flat and aspect-correct. A moving picture gets
    // a little overscan, with bounded panning instead of a seam or stretched
    // edge when the cube makes a full turn. Static pictures retain their crop.
    const double width = std::min(1.0, screenAspect / imageAspect);
    const double height = std::min(1.0, imageAspect / screenAspect);
    const double scale = moving ? .8 : 1;
    return {.5 + width * ((u - .5) * scale + (moving ? .1 * std::sin(yaw) : 0)),
            .5 + height * ((v - .5) * scale - (moving ? .1 * std::sin(pitch) : 0))};
}
inline V3 rotate(V3 p, double yaw, double pitch) {
    double x = p.x * std::cos(yaw) + p.z * std::sin(yaw), z = -p.x * std::sin(yaw) + p.z * std::cos(yaw);
    return {x, p.y * std::cos(pitch) - z * std::sin(pitch), p.y * std::sin(pitch) + z * std::cos(pitch)};
}
inline double distance(int sides) {
    return .5 / std::tan(PI / std::max(4, sides));
}
inline double radius(int sides) {
    return .5 / std::sin(PI / std::max(4, sides));
}
inline int selected(double yaw, int initial, int count) {
    int offset = static_cast<int>(std::llround(-yaw / (2 * PI / count)));
    return ((initial + offset) % count + count) % count;
}
inline double snap(double yaw, int count) {
    return std::round(yaw / (2 * PI / count)) * (2 * PI / count);
}
inline double baseScale(int windows, int minimum, int spacing) {
    return std::max(minimum / 100.0, 1 - windows * (spacing / 100.0));
}
inline double windowScale(int rank, int windows, double base) {
    return windows > 0 ? base + (rank + 1) * (1 - base) / windows : base;
}
inline double thickness(double width, int windows, double base) {
    return windows > 0 ? std::min(width / 30.0, (1 - base) / windows) : 0;
}
inline double smooth(double t) {
    t = std::clamp(t, 0.0, 1.0);
    return t * t * (3 - 2 * t);
}
struct Workspace {
    int64_t id;
    int64_t monitor;
    bool special = false;
};
inline std::vector<int64_t> faces(const std::vector<Workspace> &all, int64_t monitor, int64_t current) {
    std::vector<int64_t> result;
    for (auto w : all)
        if (w.monitor == monitor && !w.special)
            result.push_back(w.id);
    if (std::find(result.begin(), result.end(), current) == result.end())
        result.push_back(current);
    std::sort(result.begin(), result.end());
    result.erase(std::unique(result.begin(), result.end()), result.end());
    while (result.size() < 4)
        result.push_back(0); // placeholders create a workspace only when selected
    return result;
}
inline int64_t unusedID(const std::vector<Workspace> &all) {
    std::set<int64_t> ids;
    for (auto w : all)
        ids.insert(w.id);
    int64_t id = 1;
    while (ids.contains(id))
        ++id;
    return id;
}
} // namespace Cube

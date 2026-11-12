// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../../effects/window_close/native/geometry.hpp"
#include "../../effects/window_close/native/policies.hpp"
#include <glib.h>
#include <array>
#include <cstdint>

namespace InitialMemory {
using WindowButtons::Rect;
using WindowButtons::Size;
struct Record {
    bool floating = false, modeSaved = true;
    int fullscreen = 0, clientFullscreen = 0;
    std::optional<Size> normalSize;
    std::optional<std::array<int, 2>> position;
};

// Match service.py's existing private SHA-256 identities; no migration or
// plaintext app names/titles in persistent state is needed.
inline std::string identity(const std::string& app, const std::string& role,
                            bool dialog, bool picker, bool transfer) {
    if (app.empty() || !g_utf8_validate(app.data(), app.size(), nullptr)) return {};
    auto folded = g_utf8_casefold(app.data(), app.size());
    std::string value(folded); g_free(folded);
    value += transfer ? ":transfer-queue" : picker ? ":picker" : (dialog ? ":dialog:" : ":window:") + role;
    auto digest = g_compute_checksum_for_string(G_CHECKSUM_SHA256, value.data(), value.size());
    std::string key(digest, 32); g_free(digest);
    return key;
}

inline std::array<int, 2> pair(json_object* object, const char* key, int low) {
    auto value = WindowButtons::field(object, key, json_type_array);
    if (json_object_array_length(value) != 2) throw std::runtime_error("Invalid memory rectangle");
    std::array<int, 2> result;
    for (size_t i = 0; i < 2; ++i) {
        auto number = json_object_array_get_idx(value, i);
        if (!json_object_is_type(number, json_type_int)) throw std::runtime_error("Invalid memory coordinate");
        auto n = json_object_get_int64(number);
        if (n < low || n > 32768) throw std::runtime_error("Memory coordinate out of range");
        result[i] = n;
    }
    return result;
}

inline std::optional<Record> read(const std::filesystem::path& path, const std::string& key) noexcept {
    try {
        if (key.empty() || !std::filesystem::is_regular_file(path)) return {};
        const auto size = std::filesystem::file_size(path);
        if (!size || size > 4 * 1024 * 1024) return {};
        std::ifstream input(path);
        std::string text(size, '\0');
        if (!input.read(text.data(), size)) return {};
        auto doc = WindowButtons::parseJson(text);
        if (json_object_get_int64(WindowButtons::field(doc.get(), "version", json_type_int)) != 1) return {};
        auto entries = WindowButtons::field(doc.get(), "windows", json_type_object);
        json_object* value = nullptr;
        if (!json_object_object_get_ex(entries, key.c_str(), &value) || !json_object_is_type(value, json_type_object)) return {};
        Record result;
        result.floating = json_object_get_boolean(WindowButtons::field(value, "floating", json_type_boolean));
        for (auto [name, destination] : {std::pair{"fullscreen", &result.fullscreen}, {"client_fullscreen", &result.clientFullscreen}}) {
            const auto n = json_object_get_int64(WindowButtons::field(value, name, json_type_int));
            if (n < 0 || n > 2) return {};
            *destination = n;
        }
        const auto oldSize = pair(value, "size", 1);
        pair(value, "area", 1);
        json_object* field = nullptr;
        if (json_object_object_get_ex(value, "mode_saved", &field))
            result.modeSaved = json_object_get_boolean(WindowButtons::field(value, "mode_saved", json_type_boolean));
        if (json_object_object_get_ex(value, "floating_size", &field)) {
            const auto size = pair(value, "floating_size", 1);
            result.normalSize = Size{double(size[0]), double(size[1])};
        } else if (result.floating && !result.fullscreen && !result.clientFullscreen)
            result.normalSize = Size{double(oldSize[0]), double(oldSize[1])};
        if (json_object_object_get_ex(value, "floating_position", &field))
            result.position = pair(value, "floating_position", -32768);
        return result;
    } catch (...) {
        // A corrupt/stale private record must never abort a compositor map.
        return {};
    }
}

struct Plan {
    Record saved;
    bool restoreMode = false;
    bool floating = false;
};
inline Plan plan(const Record& saved, bool explicitMode, bool floating) {
    const bool mode = saved.modeSaved && !explicitMode;
    return {saved, mode, mode ? saved.floating : floating};
}

// Work is logical monitor space (already scaled/rotated). Saved positions are
// relative to that work area; extents reserve room for a KDE titlebar/borders.
inline Rect fit(const Record& record, Rect work, Rect current, Size minimum = {}, Size maximum = {},
                bool fixed = false, Rect extents = {}) {
    const double x = work.x, y = work.y;
    work.x += extents.x; work.y += extents.y;
    work.w = std::max(1., work.w - extents.x - extents.w);
    work.h = std::max(1., work.h - extents.y - extents.h);
    auto size = fixed ? Size{current.w, current.h} : record.normalSize.value_or(Size{current.w, current.h});
    if (record.position) {
        current.x = x + (*record.position)[0]; current.y = y + (*record.position)[1];
    }
    if (fixed) {
        // Position only: a fixed-size app owns its dimensions, even if oversized.
        return {std::clamp(current.x, work.x, work.x + std::max(0., work.w - size.w)),
                std::clamp(current.y, work.y, work.y + std::max(0., work.h - size.h)), size.w, size.h};
    }
    const double maxW = std::max(1., std::min(work.w - 16, maximum.w > 0 ? maximum.w : work.w));
    const double maxH = std::max(1., std::min(work.h - 16, maximum.h > 0 ? maximum.h : work.h));
    const double w = std::floor(std::clamp(size.w, std::min(maxW, std::max(1., minimum.w)), maxW));
    const double h = std::floor(std::clamp(size.h, std::min(maxH, std::max(1., minimum.h)), maxH));
    return {std::round(std::clamp(current.x, work.x, work.x + work.w - w)),
            std::round(std::clamp(current.y, work.y, work.y + work.h - h)), w, h};
}
}

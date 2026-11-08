#pragma once
#include <string>
#include <vector>
#include <cstdint>

struct IconImage {
    int w = 0, h = 0;
    std::vector<uint8_t> rgba;
    bool valid() const { return w > 0 && h > 0 && rgba.size() == (size_t)w * h * 4; }
};

// Extract the application icon from a PE (.exe/.dll) file. Prefers the largest, deepest icon <= 256px.
bool extract_pe_icon(const std::string& path, IconImage& out);
// Load an .ico file (best entry) or any stb_image-supported image (.png/.jpg/.bmp).
bool load_icon_file(const std::string& path, IconImage& out);
// Any of the above based on extension.
bool load_icon_for_exe(const std::string& path, IconImage& out);
// Downscale (box filter) to at most max_dim on each side.
void shrink_icon(IconImage& img, int max_dim);

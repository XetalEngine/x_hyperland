#include "icons.h"
#include "util.h"
#include <cstring>
#include <algorithm>

#define STB_IMAGE_IMPLEMENTATION
#define STBI_ONLY_PNG
#define STBI_ONLY_JPEG
#define STBI_ONLY_BMP
#include <stb_image.h>

namespace {
uint16_t rd16(const uint8_t* p) { uint16_t v; memcpy(&v, p, 2); return v; }
uint32_t rd32(const uint8_t* p) { uint32_t v; memcpy(&v, p, 4); return v; }

// Decode one icon image (PNG or DIB with XOR/AND mask) from a buffer.
bool decode_icon_image(const uint8_t* d, size_t n, IconImage& out) {
    if (n < 8) return false;
    if (d[0] == 0x89 && d[1] == 'P' && d[2] == 'N' && d[3] == 'G') {
        int w, h, c;
        stbi_uc* px = stbi_load_from_memory(d, (int)n, &w, &h, &c, 4);
        if (!px) return false;
        out.w = w; out.h = h; out.rgba.assign(px, px + (size_t)w * h * 4);
        stbi_image_free(px);
        return true;
    }
    if (n < 40) return false;
    uint32_t hdr = rd32(d);
    if (hdr != 40) return false;
    int32_t bw = (int32_t)rd32(d + 4), bh = (int32_t)rd32(d + 8);
    uint16_t bpp = rd16(d + 14);
    uint32_t clr_used = rd32(d + 32);
    if (bw <= 0 || bh <= 0 || bw > 1024 || bh > 2048) return false;
    int h = bh / 2;          // XOR + AND mask stacked
    if (h <= 0) return false;
    size_t off = 40;
    std::vector<uint32_t> palette;
    if (bpp <= 8) {
        size_t cnt = clr_used ? clr_used : (1u << bpp);
        if (off + cnt * 4 > n) return false;
        for (size_t i = 0; i < cnt; i++) { const uint8_t* q = d + off + i * 4; palette.push_back((uint32_t)q[2] | ((uint32_t)q[1] << 8) | ((uint32_t)q[0] << 16) | 0xFF000000u); }
        off += cnt * 4;
    }
    size_t xor_stride = (((size_t)bw * bpp + 31) / 32) * 4;
    size_t and_stride = (((size_t)bw + 31) / 32) * 4;
    size_t xor_size = xor_stride * h;
    if (off + xor_size > n) return false;
    const uint8_t* xr = d + off;
    const uint8_t* an = (off + xor_size + and_stride * h <= n) ? d + off + xor_size : nullptr;
    out.w = bw; out.h = h; out.rgba.assign((size_t)bw * h * 4, 0);
    bool any_alpha = false;
    for (int y = 0; y < h; y++) {
        const uint8_t* row = xr + (size_t)(h - 1 - y) * xor_stride;
        for (int x = 0; x < bw; x++) {
            uint8_t r = 0, g = 0, b = 0, a = 255;
            if (bpp == 32) { b = row[x*4]; g = row[x*4+1]; r = row[x*4+2]; a = row[x*4+3]; if (a) any_alpha = true; }
            else if (bpp == 24) { b = row[x*3]; g = row[x*3+1]; r = row[x*3+2]; }
            else if (bpp == 16) { uint16_t v = rd16(row + x*2); r = (uint8_t)(((v >> 10) & 31) * 255 / 31); g = (uint8_t)(((v >> 5) & 31) * 255 / 31); b = (uint8_t)((v & 31) * 255 / 31); }
            else {
                uint32_t idx = 0;
                if (bpp == 8) idx = row[x];
                else if (bpp == 4) idx = (row[x/2] >> ((x & 1) ? 0 : 4)) & 0xF;
                else if (bpp == 1) idx = (row[x/8] >> (7 - (x & 7))) & 1;
                uint32_t c = idx < palette.size() ? palette[idx] : 0;
                r = c & 0xFF; g = (c >> 8) & 0xFF; b = (c >> 16) & 0xFF;
            }
            uint8_t* o = &out.rgba[((size_t)y * bw + x) * 4];
            o[0] = r; o[1] = g; o[2] = b; o[3] = a;
        }
    }
    if ((bpp != 32 || !any_alpha) && an) {
        for (int y = 0; y < h; y++) {
            const uint8_t* row = an + (size_t)(h - 1 - y) * and_stride;
            for (int x = 0; x < bw; x++) {
                bool transparent = (row[x/8] >> (7 - (x & 7))) & 1;
                out.rgba[((size_t)y * bw + x) * 4 + 3] = transparent ? 0 : 255;
            }
        }
    }
    return true;
}

struct IconEntry { int w, h, bpp; uint32_t size; uint32_t id_or_offset; };
int score_entry(const IconEntry& e) {
    int w = e.w == 0 ? 256 : e.w;
    if (w > 256) return -1;
    return w * 64 + std::min(e.bpp, 32);   // bigger first, then deeper
}

// ---- PE parsing ----
struct Section { uint32_t va, vsize, raw, rawsize; };
struct PE {
    const std::vector<uint8_t>& d;
    std::vector<Section> secs;
    uint32_t rsrc_rva = 0, rsrc_size = 0;
    explicit PE(const std::vector<uint8_t>& data) : d(data) {}
    bool parse() {
        if (d.size() < 0x40 || d[0] != 'M' || d[1] != 'Z') return false;
        uint32_t pe = rd32(&d[0x3C]);
        if (pe + 24 > d.size() || memcmp(&d[pe], "PE\0\0", 4) != 0) return false;
        uint16_t nsec = rd16(&d[pe + 6]);
        uint16_t optsize = rd16(&d[pe + 20]);
        size_t opt = pe + 24;
        if (opt + optsize > d.size()) return false;
        uint16_t magic = rd16(&d[opt]);
        size_t dd = magic == 0x20b ? opt + 112 : opt + 96;
        if (dd + 8 * 3 > d.size()) return false;
        rsrc_rva = rd32(&d[dd + 8 * 2]); rsrc_size = rd32(&d[dd + 8 * 2 + 4]);
        size_t st = opt + optsize;
        for (int i = 0; i < nsec; i++) {
            size_t s = st + (size_t)i * 40; if (s + 40 > d.size()) break;
            secs.push_back({ rd32(&d[s + 12]), rd32(&d[s + 8]), rd32(&d[s + 20]), rd32(&d[s + 16]) });
        }
        return rsrc_rva != 0;
    }
    bool rva2off(uint32_t rva, size_t& off) const {
        for (auto& s : secs) {
            uint32_t sz = std::max(s.vsize, s.rawsize);
            if (rva >= s.va && rva < s.va + sz) { off = s.raw + (rva - s.va); return off < d.size(); }
        }
        return false;
    }
    // Resource directory walkers. Offsets are relative to the resource section start.
    struct Entry { uint32_t id; uint32_t off; bool is_dir; };
    bool dir_entries(size_t rsrc_off, uint32_t dir_off, std::vector<Entry>& out) const {
        size_t p = rsrc_off + dir_off; if (p + 16 > d.size()) return false;
        uint16_t nn = rd16(&d[p + 12]), ni = rd16(&d[p + 14]);
        size_t e = p + 16;
        for (uint32_t i = 0; i < (uint32_t)nn + ni; i++, e += 8) {
            if (e + 8 > d.size()) return false;
            uint32_t id = rd32(&d[e]), o = rd32(&d[e + 4]);
            out.push_back({ id, o & 0x7FFFFFFF, (o & 0x80000000u) != 0 });
        }
        return true;
    }
    // Follow (type -> name -> lang) and return data pointer/size for the first language.
    bool leaf_data(size_t rsrc_off, uint32_t name_dir_off, const uint8_t*& ptr, uint32_t& size) const {
        std::vector<Entry> langs; if (!dir_entries(rsrc_off, name_dir_off, langs) || langs.empty()) return false;
        Entry l = langs[0];
        if (l.is_dir) return false;
        size_t de = rsrc_off + l.off; if (de + 16 > d.size()) return false;
        uint32_t rva = rd32(&d[de]); size = rd32(&d[de + 4]);
        size_t off; if (!rva2off(rva, off) || off + size > d.size()) return false;
        ptr = &d[off]; return true;
    }
};
}

bool extract_pe_icon(const std::string& path, IconImage& out) {
    std::vector<uint8_t> d;
    if (!util::read_file_bytes(path, d, 256u * 1024 * 1024)) return false;
    PE pe(d);
    if (!pe.parse()) return false;
    size_t rsrc_off; if (!pe.rva2off(pe.rsrc_rva, rsrc_off)) return false;
    std::vector<PE::Entry> types; if (!pe.dir_entries(rsrc_off, 0, types)) return false;
    const PE::Entry* t_icon = nullptr; const PE::Entry* t_group = nullptr;
    for (auto& t : types) { if (t.id == 3 && t.is_dir) t_icon = &t; if (t.id == 14 && t.is_dir) t_group = &t; }
    if (!t_icon || !t_group) return false;
    std::vector<PE::Entry> groups; if (!pe.dir_entries(rsrc_off, t_group->off, groups) || groups.empty()) return false;
    // Windows uses the first group icon in the directory as the app icon
    const PE::Entry& g = groups[0];
    if (!g.is_dir) return false;
    const uint8_t* gd; uint32_t gsz;
    if (!pe.leaf_data(rsrc_off, g.off, gd, gsz) || gsz < 6) return false;
    uint16_t count = rd16(gd + 4);
    IconEntry best{}; int best_score = -1;
    for (uint16_t i = 0; i < count; i++) {
        const uint8_t* e = gd + 6 + (size_t)i * 14; if (6 + (size_t)(i + 1) * 14 > gsz) break;
        IconEntry ie{ e[0], e[1], rd16(e + 6), rd32(e + 8), rd16(e + 12) };
        int sc = score_entry(ie); if (sc > best_score) { best_score = sc; best = ie; }
    }
    if (best_score < 0) return false;
    std::vector<PE::Entry> icons; if (!pe.dir_entries(rsrc_off, t_icon->off, icons)) return false;
    for (auto& ic : icons) {
        if (ic.id != best.id_or_offset || !ic.is_dir) continue;
        const uint8_t* id; uint32_t isz;
        if (!pe.leaf_data(rsrc_off, ic.off, id, isz)) return false;
        return decode_icon_image(id, isz, out);
    }
    return false;
}

bool load_icon_file(const std::string& path, IconImage& out) {
    std::vector<uint8_t> d;
    if (!util::read_file_bytes(path, d, 64u * 1024 * 1024)) return false;
    if (d.size() >= 6 && rd16(&d[0]) == 0 && rd16(&d[2]) == 1) {   // ICO
        uint16_t count = rd16(&d[4]);
        IconEntry best{}; int best_score = -1;
        for (uint16_t i = 0; i < count; i++) {
            size_t e = 6 + (size_t)i * 16; if (e + 16 > d.size()) break;
            IconEntry ie{ d[e], d[e+1], rd16(&d[e+6]), rd32(&d[e+8]), rd32(&d[e+12]) };
            int sc = score_entry(ie); if (sc > best_score) { best_score = sc; best = ie; }
        }
        if (best_score < 0 || best.id_or_offset + best.size > d.size()) return false;
        return decode_icon_image(&d[best.id_or_offset], best.size, out);
    }
    int w, h, c;
    stbi_uc* px = stbi_load_from_memory(d.data(), (int)d.size(), &w, &h, &c, 4);
    if (!px) return false;
    out.w = w; out.h = h; out.rgba.assign(px, px + (size_t)w * h * 4);
    stbi_image_free(px);
    return true;
}

bool load_icon_for_exe(const std::string& path, IconImage& out) {
    if (util::ends_with_ci(path, ".exe") || util::ends_with_ci(path, ".dll")) return extract_pe_icon(path, out);
    if (util::ends_with_ci(path, ".ico") || util::ends_with_ci(path, ".png") || util::ends_with_ci(path, ".jpg") || util::ends_with_ci(path, ".bmp")) return load_icon_file(path, out);
    return false;
}

void shrink_icon(IconImage& img, int max_dim) {
    if (!img.valid() || (img.w <= max_dim && img.h <= max_dim)) return;
    int f = (std::max(img.w, img.h) + max_dim - 1) / max_dim;
    int nw = img.w / f, nh = img.h / f;
    std::vector<uint8_t> o((size_t)nw * nh * 4);
    for (int y = 0; y < nh; y++) for (int x = 0; x < nw; x++) {
        uint32_t acc[4] = {0,0,0,0};
        for (int dy = 0; dy < f; dy++) for (int dx = 0; dx < f; dx++) {
            const uint8_t* p = &img.rgba[((size_t)(y*f+dy) * img.w + (x*f+dx)) * 4];
            for (int c = 0; c < 4; c++) acc[c] += p[c];
        }
        for (int c = 0; c < 4; c++) o[((size_t)y * nw + x) * 4 + c] = (uint8_t)(acc[c] / (f * f));
    }
    img.w = nw; img.h = nh; img.rgba.swap(o);
}

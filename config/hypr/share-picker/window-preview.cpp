// Local, in-memory Wayland window thumbnails. No files or portal requests.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <wayland-client.h>
#include "hyprland-toplevel-export-v1-client.h"
#include <QImage>
#include <QBuffer>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sys/mman.h>
#include <unistd.h>

struct Capture {
    wl_display* display = nullptr;
    wl_shm* shm = nullptr;
    hyprland_toplevel_export_manager_v1* manager = nullptr;
    hyprland_toplevel_export_frame_v1* frame = nullptr;
    wl_buffer* buffer = nullptr;
    void* pixels = MAP_FAILED;
    size_t bytes = 0;
    uint32_t width = 0, height = 0, stride = 0, format = 0, flags = 0;
    uint32_t bufferWidth = 0, bufferHeight = 0, bufferStride = 0, bufferFormat = 0;
    size_t* streamBytes = nullptr;
    bool done = false, ready = false;
};

static void global(void* data, wl_registry* registry, uint32_t id, const char* name, uint32_t version) {
    auto& c = *static_cast<Capture*>(data);
    if (!strcmp(name, "wl_shm"))
        c.shm = static_cast<wl_shm*>(wl_registry_bind(registry, id, &wl_shm_interface, 1));
    else if (!strcmp(name, "hyprland_toplevel_export_manager_v1"))
        c.manager = static_cast<hyprland_toplevel_export_manager_v1*>(wl_registry_bind(
            registry, id, &hyprland_toplevel_export_manager_v1_interface, std::min(version, 2u)));
}
static void removed(void*, wl_registry*, uint32_t) {}
static const wl_registry_listener registryListener{global, removed};

static void buffer(void* data, hyprland_toplevel_export_frame_v1*, uint32_t format, uint32_t w, uint32_t h, uint32_t stride) {
    auto& c = *static_cast<Capture*>(data);
    c.format = format; c.width = w; c.height = h; c.stride = stride;
}
static void damage(void*, hyprland_toplevel_export_frame_v1*, uint32_t, uint32_t, uint32_t, uint32_t) {}
static void flags(void* data, hyprland_toplevel_export_frame_v1*, uint32_t value) { static_cast<Capture*>(data)->flags = value; }
static void ready(void* data, hyprland_toplevel_export_frame_v1*, uint32_t, uint32_t, uint32_t) {
    auto& c = *static_cast<Capture*>(data); c.done = c.ready = true;
}
static void failed(void* data, hyprland_toplevel_export_frame_v1*) { static_cast<Capture*>(data)->done = true; }
static void dmabuf(void*, hyprland_toplevel_export_frame_v1*, uint32_t, uint32_t, uint32_t) {}
static void releaseBuffer(Capture& c) {
    if (c.buffer) wl_buffer_destroy(c.buffer);
    if (c.pixels != MAP_FAILED) munmap(c.pixels, c.bytes);
    if (c.streamBytes && c.pixels != MAP_FAILED) *c.streamBytes -= c.bytes;
    c.buffer = nullptr; c.pixels = MAP_FAILED; c.bytes = 0;
}
static void bufferDone(void* data, hyprland_toplevel_export_frame_v1*) {
    auto& c = *static_cast<Capture*>(data);
    const size_t bytes = size_t(c.stride) * c.height;
    if (!c.width || !c.height || c.width > 16384 || c.height > 16384 ||
        c.stride < c.width * 4 || bytes > 256 * 1024 * 1024 || !c.shm) { c.done = true; return; }
    if (c.buffer && c.bufferWidth == c.width && c.bufferHeight == c.height && c.bufferStride == c.stride && c.bufferFormat == c.format) {
        hyprland_toplevel_export_frame_v1_copy(c.frame, c.buffer, 1);
        return;
    }
    releaseBuffer(c);
    if (c.streamBytes && *c.streamBytes + bytes > 256 * 1024 * 1024) { c.done = true; return; }
    c.bytes = bytes;
    int fd = memfd_create("xetal-window-preview", MFD_CLOEXEC);
    if (fd < 0) { c.done = true; return; }
    if (ftruncate(fd, c.bytes)) { close(fd); c.done = true; return; }
    c.pixels = mmap(nullptr, c.bytes, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (c.pixels == MAP_FAILED) { close(fd); c.done = true; return; }
    if (c.streamBytes) *c.streamBytes += c.bytes;
    auto pool = wl_shm_create_pool(c.shm, fd, c.bytes);
    c.buffer = wl_shm_pool_create_buffer(pool, 0, c.width, c.height, c.stride, c.format);
    wl_shm_pool_destroy(pool); close(fd);
    c.bufferWidth = c.width; c.bufferHeight = c.height; c.bufferStride = c.stride; c.bufferFormat = c.format;
    hyprland_toplevel_export_frame_v1_copy(c.frame, c.buffer, 1);
}
static const hyprland_toplevel_export_frame_v1_listener frameListener{
    buffer, damage, flags, ready, failed, dmabuf, bufferDone
};

static QImage image(const Capture& c, bool live = false) {
    QImage::Format format;
    switch (c.format) {
    case WL_SHM_FORMAT_ARGB8888: format = QImage::Format_ARGB32_Premultiplied; break;
    case WL_SHM_FORMAT_XRGB8888: format = QImage::Format_RGB32; break;
    case WL_SHM_FORMAT_ABGR8888: format = QImage::Format_RGBA8888_Premultiplied; break;
    case WL_SHM_FORMAT_XBGR8888: format = QImage::Format_RGBX8888; break;
    case WL_SHM_FORMAT_XRGB2101010: format = QImage::Format_RGB30; break;
    case WL_SHM_FORMAT_XBGR2101010: format = QImage::Format_BGR30; break;
    case WL_SHM_FORMAT_ARGB2101010: format = QImage::Format_A2RGB30_Premultiplied; break;
    case WL_SHM_FORMAT_ABGR2101010: format = QImage::Format_A2BGR30_Premultiplied; break;
    default: return {};
    }
    QImage result(static_cast<const uchar*>(c.pixels), c.width, c.height, c.stride, format);
    result = result.scaled(640, 400, Qt::KeepAspectRatio, live ? Qt::FastTransformation : Qt::SmoothTransformation);
    if (c.flags & 1) {
#if QT_VERSION >= QT_VERSION_CHECK(6, 9, 0)
        result = result.flipped(Qt::Vertical);
#else
        result = result.mirrored(false, true);
#endif
    }
    return result;
}

#include "window-stream.h"

int main(int argc, char** argv) {
    if (argc == 2 && !strcmp(argv[1], "--stream")) return streamPreviews();
    if (argc != 2) return 2;
    char* end = nullptr;
    auto address = strtoull(argv[1], &end, 0);
    if (!address || !end || *end) return 2;
    alarm(3); // A disconnected or stalled compositor cannot leave preview workers behind.
    Capture c;
    c.display = wl_display_connect(nullptr);
    if (!c.display) return 3;
    auto registry = wl_display_get_registry(c.display);
    wl_registry_add_listener(registry, &registryListener, &c);
    if (wl_display_roundtrip(c.display) < 0 || !c.manager || !c.shm) return 3;
    c.frame = hyprland_toplevel_export_manager_v1_capture_toplevel(c.manager, 0, uint32_t(address));
    hyprland_toplevel_export_frame_v1_add_listener(c.frame, &frameListener, &c);
    while (!c.done && wl_display_dispatch(c.display) >= 0) {}
    QImage result = c.ready ? image(c) : QImage();
    int status = 4;
    if (!result.isNull()) {
        QByteArray encoded; QBuffer output(&encoded); output.open(QIODevice::WriteOnly);
        if (result.save(&output, "PNG") && fwrite(encoded.constData(), 1, encoded.size(), stdout) == size_t(encoded.size())) status = 0;
    }
    if (c.frame) hyprland_toplevel_export_frame_v1_destroy(c.frame);
    releaseBuffer(c);
    hyprland_toplevel_export_manager_v1_destroy(c.manager);
    wl_shm_destroy(c.shm); wl_registry_destroy(registry); wl_display_disconnect(c.display);
    return status;
}

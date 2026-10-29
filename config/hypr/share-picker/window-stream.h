// Persistent task-switcher capture. One Wayland connection, reusable SHM pipeline,
// bounded output, and raw thumbnail pixels instead of spawning PNG encoders.
// Stdin lines: FPS ADDRESS... (up to 24); EOF stops capture immediately.
// Stdout: little-endian XTPF + uint64 address + uint32 width,height,byteCount,
// followed by premultiplied BGRA pixels. No screenshot files are written.
#pragma once
#include <QtEndian>
#include <array>
#include <chrono>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <sstream>
#include <string>
#include <vector>

static int streamPreviews() {
    using Clock = std::chrono::steady_clock;
    const auto origin = Clock::now();
    auto seconds = [&] { return std::chrono::duration<double>(Clock::now() - origin).count(); };
    struct Target { uint64_t address; double due = 0; };
    struct Slot { Capture capture; uint64_t address = 0; double started = 0; };
    Capture connection;
    connection.display = wl_display_connect(nullptr);
    if (!connection.display) return 3;
    auto *registry = wl_display_get_registry(connection.display);
    wl_registry_add_listener(registry, &registryListener, &connection);
    if (wl_display_roundtrip(connection.display) < 0 || !connection.manager || !connection.shm) {
        wl_display_disconnect(connection.display); return 3;
    }
    std::array<Slot, 8> pipeline;
    size_t totalBytes = 0;
    for (auto& slot : pipeline) {
        slot.capture.display = connection.display; slot.capture.shm = connection.shm;
        slot.capture.manager = connection.manager; slot.capture.streamBytes = &totalBytes;
    }
    std::vector<Target> wanted;
    QByteArray output;
    std::string input;
    double fps = 60;
    bool stopped = false;
    signal(SIGPIPE, SIG_IGN);
    fcntl(STDIN_FILENO, F_SETFL, fcntl(STDIN_FILENO, F_GETFL) | O_NONBLOCK);
    fcntl(STDOUT_FILENO, F_SETFL, fcntl(STDOUT_FILENO, F_GETFL) | O_NONBLOCK);
    auto freeFrame = [](Slot& slot) {
        if (slot.capture.frame) hyprland_toplevel_export_frame_v1_destroy(slot.capture.frame);
        slot.capture.frame = nullptr; slot.capture.done = slot.capture.ready = false; slot.address = 0;
    };
    while (!stopped && !wl_display_get_error(connection.display)) {
        if (wl_display_dispatch_pending(connection.display) < 0) break;
        const auto now = seconds();
        for (auto& slot : pipeline) {
            if (!slot.address) continue;
            auto& c = slot.capture;
            if (!c.done && now - slot.started < 2.2) continue;
            const bool requested = std::any_of(wanted.begin(),wanted.end(),[&](auto& t){ return t.address == slot.address; });
            if (c.ready && requested && output.size() < 10 * 1024 * 1024) {
                auto thumbnail = image(c, true).convertToFormat(QImage::Format_ARGB32_Premultiplied);
                if (!thumbnail.isNull()) {
                    const uint32_t length = thumbnail.width() * thumbnail.height() * 4;
                    char header[24]; memcpy(header,"XTPF",4);
                    qToLittleEndian<uint64_t>(slot.address,header+4);
                    qToLittleEndian<uint32_t>(thumbnail.width(),header+12);
                    qToLittleEndian<uint32_t>(thumbnail.height(),header+16);
                    qToLittleEndian<uint32_t>(length,header+20);
                    output.append(header,sizeof(header));
                    output.append(reinterpret_cast<const char*>(thumbnail.constBits()),length);
                }
            } else if (!c.ready) {
                for (auto& target : wanted) if (target.address == slot.address) target.due = now + 2.;
            }
            freeFrame(slot);
        }
        // Oldest-due scheduling is fair across visible windows, without dividing
        // the requested FPS among them. Slow sources do not block other pipeline.
        if (output.size() < 2 * 1024 * 1024) for (auto& slot : pipeline) {
            if (slot.address) continue;
            Target* next = nullptr;
            for (auto& target : wanted) {
                if (target.due > now || (next && target.due >= next->due)) continue;
                if (std::any_of(pipeline.begin(),pipeline.end(),[&](const auto& s){ return s.address == target.address; })) continue;
                next = &target;
            }
            if (!next) break;
            slot.address = next->address; slot.started = now;
            next->due += 1. / fps;
            if (next->due < now) next->due = now + 1. / fps;
            slot.capture.flags = 0;
            slot.capture.frame = hyprland_toplevel_export_manager_v1_capture_toplevel(connection.manager,0,uint32_t(slot.address));
            hyprland_toplevel_export_frame_v1_add_listener(slot.capture.frame,&frameListener,&slot.capture);
        }
        if (wl_display_flush(connection.display) < 0 && errno != EAGAIN) break;
        pollfd fds[]{{wl_display_get_fd(connection.display), POLLIN, 0},
                     {STDIN_FILENO, POLLIN, 0}, {STDOUT_FILENO, short(output.isEmpty() ? 0 : POLLOUT), 0}};
        if (poll(fds,3,2) < 0) { if (errno == EINTR) continue; break; }
        if (fds[1].revents & (POLLIN | POLLHUP)) {
            char block[4096]; ssize_t count;
            while ((count = read(STDIN_FILENO,block,sizeof(block))) > 0) input.append(block,size_t(count));
            if (!count || input.size() > 16384) stopped = true;
            size_t end;
            while ((end = input.find('\n')) != std::string::npos) {
                std::istringstream line(input.substr(0,end)); input.erase(0,end+1);
                int rate = 0; line >> rate;
                std::vector<Target> targets;
                std::string token;
                bool valid = rate >= 1 && rate <= 144;
                while (line >> token) {
                    char* tail = nullptr;
                    const auto address = strtoull(token.c_str(),&tail,16);
                    if (!address || !tail || *tail || targets.size() >= 24) { valid = false; break; }
                    if (std::none_of(targets.begin(),targets.end(),[&](auto& t){ return t.address == address; })) {
                        auto previous = std::find_if(wanted.begin(),wanted.end(),[&](auto& t){ return t.address == address; });
                        targets.push_back({address, previous == wanted.end() ? 0 : previous->due});
                    }
                }
                if (valid) { wanted = std::move(targets); fps = rate; }
            }
        }
        if (fds[0].revents & (POLLERR | POLLHUP)) break;
        if (fds[0].revents & POLLIN) if (wl_display_dispatch(connection.display) < 0) break;
        if (!output.isEmpty() && fds[2].revents & POLLOUT) {
            const auto written = write(STDOUT_FILENO,output.constData(),output.size());
            if (written > 0) output.remove(0,written);
            else if (written < 0 && errno != EAGAIN && errno != EINTR) break;
        }
        if (fds[2].revents & (POLLERR | POLLHUP)) break;
    }
    for (auto& slot : pipeline) { freeFrame(slot); releaseBuffer(slot.capture); }
    hyprland_toplevel_export_manager_v1_destroy(connection.manager);
    wl_shm_destroy(connection.shm); wl_registry_destroy(registry); wl_display_disconnect(connection.display);
    return 0;
}

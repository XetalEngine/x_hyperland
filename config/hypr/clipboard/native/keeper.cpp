// SPDX-License-Identifier: GPL-2.0-or-later
// Keep the current regular clipboard alive without logging or saving its data.
#include "wlr-data-control-client-protocol.h"
#include "formats.hpp"
#include <wayland-client.h>
#include <poll.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/file.h>
#include <sys/random.h>
#include <cerrno>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <chrono>
#include <map>
#include <memory>

namespace {
using Clock = std::chrono::steady_clock;
constexpr size_t LIMIT = 16 * 1024 * 1024, IMAGE_LIMIT = 8 * 1024 * 1024, TEXT_LIMIT = 1024 * 1024;
constexpr size_t MAX_FORMATS = 128, MAX_WRITES = 16;
constexpr auto TIMEOUT = std::chrono::seconds(4);
using Bytes = std::shared_ptr<const std::string>;
struct Offer { zwlr_data_control_offer_v1* object; std::vector<std::string> formats; bool overflow = false; };
struct Read {
    int fd = -1; std::string mime, bytes;
    ~Read() { if (fd >= 0) close(fd); }
};
struct Capture {
    zwlr_data_control_offer_v1* offer = nullptr;
    wl_callback* barrier = nullptr;
    std::vector<std::unique_ptr<Read>> reads;
    std::string chosen; size_t size = 0;
    Clock::time_point deadline = Clock::now() + TIMEOUT;
    ~Capture() {
        if (barrier) wl_callback_destroy(barrier);
        if (offer) zwlr_data_control_offer_v1_destroy(offer);
    }
};
struct Source { zwlr_data_control_source_v1* object; std::map<std::string, Bytes> formats; };
struct Write {
    int fd; Bytes bytes; size_t offset = 0; uint64_t id;
    Clock::time_point deadline = Clock::now() + TIMEOUT;
    ~Write() { close(fd); }
};
wl_display* display = nullptr;
wl_seat* seat = nullptr;
zwlr_data_control_manager_v1* manager = nullptr;
zwlr_data_control_device_v1* device = nullptr;
std::map<zwlr_data_control_offer_v1*, std::unique_ptr<Offer>> offers;
std::map<zwlr_data_control_source_v1*, std::unique_ptr<Source>> sources;
std::map<int, std::unique_ptr<Write>> writes;
std::unique_ptr<Capture> capture;
std::string marker;
uint64_t generation = 0, nextWrite = 0;
bool running = true;

void destroyOffer(zwlr_data_control_offer_v1* object) {
    if (object && offers.erase(object)) zwlr_data_control_offer_v1_destroy(object);
}
void format(void* data, zwlr_data_control_offer_v1*, const char* mime) {
    auto& offer = *static_cast<Offer*>(data);
    if (std::strlen(mime) >= 256 || !*mime) { offer.overflow = true; return; }
    if (std::find(offer.formats.begin(), offer.formats.end(), mime) != offer.formats.end()) return;
    if (offer.formats.size() < MAX_FORMATS) offer.formats.emplace_back(mime);
    else offer.overflow = true;
}
const zwlr_data_control_offer_v1_listener offerListener{format};
void offered(void*, zwlr_data_control_device_v1*, zwlr_data_control_offer_v1* object) {
    if (offers.size() >= MAX_FORMATS) { running = false; return; }
    auto offer = std::make_unique<Offer>(); offer->object = object;
    zwlr_data_control_offer_v1_add_listener(object, &offerListener, offer.get());
    offers.emplace(object, std::move(offer));
}
void selection(void*, zwlr_data_control_device_v1*, zwlr_data_control_offer_v1* object) {
    ++generation; capture.reset();
    const auto found = offers.find(object);
    if (found == offers.end()) return; // An explicit clear stays cleared.
    auto& offer = *found->second;
    const auto chosen = offer.overflow ? std::string{} : Clipboard::choose(offer.formats);
    if (chosen.empty() || std::find(offer.formats.begin(), offer.formats.end(), marker) != offer.formats.end()) {
        destroyOffer(object); return;
    }
    auto pending = std::make_unique<Capture>(); pending->chosen = chosen;
    pending->offer = object;
    // Capture every advertised representation before taking ownership. Keeping
    // only the history's plain-text representation would break rich-text paste.
    for (const auto& mime : offer.formats) {
        int fds[2];
        if (pipe2(fds, O_CLOEXEC) < 0) { offers.erase(object); return; }
        const int flags = fcntl(fds[0], F_GETFL);
        if (flags < 0 || fcntl(fds[0], F_SETFL, flags | O_NONBLOCK) < 0) {
            close(fds[0]); close(fds[1]); offers.erase(object); return;
        }
        auto read = std::make_unique<Read>(); read->fd = fds[0]; read->mime = mime;
        zwlr_data_control_offer_v1_receive(object, mime.c_str(), fds[1]); close(fds[1]);
        pending->reads.push_back(std::move(read));
    }
    offers.erase(object); capture = std::move(pending);
}
void finished(void*, zwlr_data_control_device_v1*) { running = false; }
void primary(void*, zwlr_data_control_device_v1*, zwlr_data_control_offer_v1* object) { destroyOffer(object); }
const zwlr_data_control_device_v1_listener deviceListener{offered, selection, finished, primary};
void send(void* data, zwlr_data_control_source_v1*, const char* mime, int fd) {
    const auto& formats = static_cast<Source*>(data)->formats;
    const auto found = formats.find(mime);
    size_t retained = 0;
    for (const auto& [_, write] : writes) retained += write->bytes->size();
    if (found == formats.end() || writes.size() >= MAX_WRITES || retained + found->second->size() > LIMIT) {
        close(fd); return;
    }
    const int flags = fcntl(fd, F_GETFL);
    if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0 || fcntl(fd, F_SETFD, FD_CLOEXEC) < 0) {
        close(fd); return;
    }
    auto write = std::make_unique<Write>(); write->fd = fd; write->bytes = found->second; write->id = ++nextWrite;
    writes.emplace(fd, std::move(write));
}
void cancelled(void*, zwlr_data_control_source_v1* object) {
    if (sources.erase(object)) zwlr_data_control_source_v1_destroy(object);
}
const zwlr_data_control_source_v1_listener sourceListener{send, cancelled};
void publish(void*, wl_callback* callback, uint32_t) {
    if (!capture || capture->barrier != callback) return;
    capture->barrier = nullptr; wl_callback_destroy(callback);
    // The sync barrier drains queued selection changes before we publish a
    // completed snapshot. A replaced, cleared or incomplete copy is discarded.
    auto source = std::make_unique<Source>();
    source->object = zwlr_data_control_manager_v1_create_data_source(manager);
    for (auto& read : capture->reads) source->formats.emplace(read->mime, std::make_shared<const std::string>(std::move(read->bytes)));
    for (const auto& [mime, _] : source->formats) zwlr_data_control_source_v1_offer(source->object, mime.c_str());
    zwlr_data_control_source_v1_offer(source->object, marker.c_str());
    zwlr_data_control_source_v1_add_listener(source->object, &sourceListener, source.get());
    zwlr_data_control_device_v1_set_selection(device, source->object);
    sources.emplace(source->object, std::move(source)); capture.reset();
}
const wl_callback_listener barrierListener{publish};
void receive(Read& input) {
    char bytes[65536];
    const size_t limit = input.mime == capture->chosen ? (input.mime.starts_with("image/") ? IMAGE_LIMIT : TEXT_LIMIT) : IMAGE_LIMIT;
    while (input.fd >= 0) {
        const auto count = read(input.fd, bytes, sizeof(bytes));
        if (count > 0) {
            if (input.bytes.size() + count > limit || capture->size + count > LIMIT) { capture.reset(); return; }
            input.bytes.append(bytes, size_t(count)); capture->size += count; continue;
        }
        if (count == 0) { close(input.fd); input.fd = -1; return; }
        if (errno == EINTR) continue;
        if (errno != EAGAIN && errno != EWOULDBLOCK) capture.reset();
        return;
    }
}
void transmit(Write& output) {
    while (output.offset < output.bytes->size()) {
        const auto count = write(output.fd, output.bytes->data() + output.offset, output.bytes->size() - output.offset);
        if (count > 0) { output.offset += size_t(count); continue; }
        if (count < 0 && errno == EINTR) continue;
        if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return;
        writes.erase(output.fd); return;
    }
    writes.erase(output.fd);
}
void global(void*, wl_registry* registry, uint32_t name, const char* interface, uint32_t version) {
    if (!seat && std::strcmp(interface, "wl_seat") == 0)
        seat = static_cast<wl_seat*>(wl_registry_bind(registry, name, &wl_seat_interface, 1));
    if (!manager && std::strcmp(interface, "zwlr_data_control_manager_v1") == 0)
        manager = static_cast<zwlr_data_control_manager_v1*>(wl_registry_bind(registry, name, &zwlr_data_control_manager_v1_interface, std::min(version, 2u)));
}
void removed(void*, wl_registry*, uint32_t) {}
const wl_registry_listener registryListener{global, removed};
void seatCapabilities(void*, wl_seat*, uint32_t) {}
void seatName(void*, wl_seat*, const char*) {}
const wl_seat_listener seatListener{seatCapabilities, seatName};
}

int main() {
    // A second UI or a live repair must not run a competing clipboard owner.
    const char* runtime = std::getenv("XDG_RUNTIME_DIR"), *instance = std::getenv("HYPRLAND_INSTANCE_SIGNATURE");
    if (!runtime || !instance || std::strchr(instance, '/')) return 2;
    const auto lockPath = std::string(runtime) + "/hypr/" + instance + "/fusion-clipboard-keeper.lock";
    const int lock = open(lockPath.c_str(), O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (lock < 0) return 2;
    if (flock(lock, LOCK_EX | LOCK_NB) < 0) return errno == EWOULDBLOCK ? 0 : 2;
    unsigned char random[16];
    if (getrandom(random, sizeof(random), 0) != sizeof(random)) return 2;
    marker = "application/x-fusion-clipboard-";
    for (auto byte : random) { char hex[3]; std::snprintf(hex, sizeof(hex), "%02x", byte); marker += hex; }
    std::signal(SIGPIPE, SIG_IGN); // A paste receiver can close its pipe early.
    display = wl_display_connect(nullptr); if (!display) return 1;
    auto registry = wl_display_get_registry(display); wl_registry_add_listener(registry, &registryListener, nullptr);
    if (wl_display_roundtrip(display) < 0 || !manager || !seat) { wl_display_disconnect(display); return 2; }
    wl_seat_add_listener(seat, &seatListener, nullptr);
    device = zwlr_data_control_manager_v1_get_data_device(manager, seat);
    zwlr_data_control_device_v1_add_listener(device, &deviceListener, nullptr);
    while (running) {
        while (wl_display_prepare_read(display) != 0) {
            if (wl_display_dispatch_pending(display) < 0) { running = false; break; }
        }
        if (!running) break;
        const int flushed = wl_display_flush(display);
        if (flushed < 0 && errno != EAGAIN) { wl_display_cancel_read(display); break; }
        const auto revision = generation;
        std::vector<pollfd> fds{{wl_display_get_fd(display), short(POLLIN | (flushed < 0 ? POLLOUT : 0)), 0}};
        size_t reads = 0;
        if (capture) for (const auto& read : capture->reads) { fds.push_back({read->fd, POLLIN, 0}); ++reads; }
        std::vector<std::pair<int, uint64_t>> pendingWrites;
        for (const auto& [fd, output] : writes) { fds.push_back({fd, POLLOUT, 0}); pendingWrites.emplace_back(fd, output->id); }
        const int result = poll(fds.data(), fds.size(), capture || !writes.empty() ? 100 : -1);
        if (result < 0) { wl_display_cancel_read(display); if (errno == EINTR) continue; break; }
        if (fds[0].revents & POLLIN) { if (wl_display_read_events(display) < 0) break; }
        else wl_display_cancel_read(display);
        if (fds[0].revents & (POLLERR | POLLHUP)) break;
        if (wl_display_dispatch_pending(display) < 0) break;
        for (size_t i = 0; i < reads && capture && generation == revision; ++i)
            if (fds[i + 1].revents & (POLLIN | POLLHUP | POLLERR)) receive(*capture->reads[i]);
        for (size_t i = 0; i < pendingWrites.size(); ++i) {
            const auto [fd, id] = pendingWrites[i]; const auto found = writes.find(fd);
            if (found != writes.end() && found->second->id == id && fds[1 + reads + i].revents) transmit(*found->second);
        }
        if (capture && Clock::now() > capture->deadline) capture.reset();
        if (capture && !capture->barrier && std::all_of(capture->reads.begin(), capture->reads.end(), [](const auto& read) { return read->fd < 0; })) {
            auto chosen = std::find_if(capture->reads.begin(), capture->reads.end(), [](const auto& read) { return read->mime == capture->chosen; });
            if (chosen == capture->reads.end() || (*chosen)->bytes.empty()) capture.reset();
            else {
                capture->barrier = wl_display_sync(display);
                wl_callback_add_listener(capture->barrier, &barrierListener, nullptr);
            }
        }
        for (auto it = writes.begin(); it != writes.end();)
            if (Clock::now() > it->second->deadline) it = writes.erase(it); else ++it;
    }
    capture.reset(); writes.clear();
    while (!offers.empty()) destroyOffer(offers.begin()->first);
    while (!sources.empty()) cancelled(nullptr, sources.begin()->first);
    zwlr_data_control_device_v1_destroy(device); zwlr_data_control_manager_v1_destroy(manager);
    wl_seat_destroy(seat); wl_registry_destroy(registry); wl_display_disconnect(display); close(lock);
    return 1; // Reconnect after an unexpected transport failure; UI exit stops retries.
}

// File drag feedback for the pinned compositor, which does not negotiate
// wl_data_offer.set_actions. Only Fusion's explicitly marked drags opt in.
// Use the public Wayland protocol observer and resource lifetime notifications;
// no function hooks, private data offsets, clipboard changes or file operations.
#pragma once
#include <wayland-server-core.h>
#include <wayland-server-protocol.h>
#include <string_view>
#include <chrono>

namespace FileDragActions {
inline wl_protocol_logger* logger = nullptr;
inline wl_display* server = nullptr;
inline wl_event_source* refresh = nullptr;
inline wl_fixed_t pointerX = 0, pointerY = 0;
struct Resource {
    wl_resource* value = nullptr;
    wl_listener destroyed{};
    Resource() {
        wl_list_init(&destroyed.link);
        destroyed.notify = [](wl_listener* listener, void*) {
            Resource* self = wl_container_of(listener, self, destroyed);
            self->reset();
        };
    }
    void reset(wl_resource* next = nullptr) {
        wl_list_remove(&destroyed.link); wl_list_init(&destroyed.link);
        value = next;
        if (value) wl_resource_add_destroy_listener(value, &destroyed);
    }
};
inline Resource source, offer, device;
inline uint32_t sourceActions = 0, targetActions = 0, preferred = 0, last = UINT32_MAX;
inline bool accepted = false, sending = false, dropped = false;

inline void clear() {
    if (refresh) { wl_event_source_remove(refresh); refresh = nullptr; }
    source.reset(); offer.reset(); device.reset();
    sourceActions = targetActions = preferred = 0; last = UINT32_MAX;
    accepted = dropped = false;
}
inline void report() {
    if (!source.value || dropped || sending) return;
    const auto available = accepted && offer.value ? sourceActions & targetActions : 0;
    const uint32_t action = (preferred & available) ? preferred
        : available & WL_DATA_DEVICE_MANAGER_DND_ACTION_COPY ? WL_DATA_DEVICE_MANAGER_DND_ACTION_COPY
        : available & WL_DATA_DEVICE_MANAGER_DND_ACTION_MOVE ? WL_DATA_DEVICE_MANAGER_DND_ACTION_MOVE : 0;
    if (last == action) return;
    last = action; sending = true;
    if (wl_resource_get_version(source.value) >= WL_DATA_SOURCE_ACTION_SINCE_VERSION)
        wl_data_source_send_action(source.value, action);
    if (offer.value && wl_resource_get_version(offer.value) >= WL_DATA_OFFER_ACTION_SINCE_VERSION)
        wl_data_offer_send_action(offer.value, action);
    sending = false;
}
inline void observe(void*, wl_protocol_logger_type direction, const wl_protocol_logger_message* message) {
    if (sending) return;
    const std::string_view type = wl_resource_get_class(message->resource), name = message->message->name;
    const auto* args = message->arguments;
    if (direction == WL_PROTOCOL_LOGGER_REQUEST && type == "wl_data_device" && name == "start_drag") {
        clear();
        auto* resource = reinterpret_cast<wl_resource*>(args[0].o);
        if (!resource) return;
        auto data = CWLDataSourceResource::fromResource(resource);
        if (!data) return;
        const auto mimes = data->mimes();
        if (std::ranges::find(mimes, "application/x-hyperfusion-file-drag") == mimes.end()) return;
        source.reset(resource); sourceActions = data->actions();
        report(); return;
    }
    if (!source.value) return;
    if (direction == WL_PROTOCOL_LOGGER_EVENT && type == "wl_keyboard" && name == "modifiers" &&
        device.value && offer.value && !dropped && !refresh) {
        // Re-negotiate even when the user changes Ctrl/Shift without moving.
        // The idle callback runs after the keyboard event reaches the client.
        refresh = wl_event_loop_add_idle(wl_display_get_event_loop(server), [](void*) {
            refresh = nullptr;
            if (!source.value || !device.value || !offer.value || dropped) return;
            const auto now = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now().time_since_epoch()).count();
            wl_data_device_send_motion(device.value, uint32_t(now), pointerX, pointerY);
        }, nullptr);
    }
    if (direction == WL_PROTOCOL_LOGGER_EVENT && type == "wl_data_device") {
        if (name == "enter") {
            offer.reset(reinterpret_cast<wl_resource*>(args[4].o)); device.reset(message->resource);
            pointerX = args[2].f; pointerY = args[3].f;
            targetActions = preferred = 0; accepted = false; last = UINT32_MAX;
            report();
        } else if (name == "leave" && device.value == message->resource) {
            accepted = false; report(); offer.reset(); device.reset();
        } else if (name == "drop" && device.value == message->resource) {
            report(); dropped = true; // Keep the completed action through transfer/finish.
        } else if (name == "motion" && device.value == message->resource) {
            pointerX = args[1].f; pointerY = args[2].f;
        }
    } else if (direction == WL_PROTOCOL_LOGGER_REQUEST && message->resource == offer.value) {
        if (name == "set_actions") {
            targetActions = args[0].u & 3;
            preferred = args[1].u;
            if (preferred != 1 && preferred != 2) preferred = 0;
            report();
        } else if (name == "accept") {
            accepted = args[1].s != nullptr;
            // Older targets do not negotiate actions; copying is non-destructive.
            if (wl_resource_get_version(offer.value) < 3) targetActions = preferred = 1;
            report();
        }
    } else if (direction == WL_PROTOCOL_LOGGER_EVENT && message->resource == source.value &&
               (name == "cancelled" || name == "dnd_finished")) clear();
}
inline void start(wl_display* display) { server = display; logger = wl_display_add_protocol_logger(display, observe, nullptr); }
inline void stop() {
    if (logger) wl_protocol_logger_destroy(logger);
    logger = nullptr; clear(); server = nullptr;
}
}

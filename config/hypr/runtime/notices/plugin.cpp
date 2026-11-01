// Hyprland 0.56.2 still supports our managed .conf profile. Acknowledge only
// its migration reminder, before startup notifications reach the first frame.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/event/EventBus.hpp>
#include <hyprland/src/i18n/Engine.hpp>
#include <hyprland/src/notification/NotificationOverlay.hpp>

#include <stdexcept>

namespace {
CHyprSignalListener startListener;

void acknowledgeConfigNotice() {
    const auto message = I18n::i18nEngine()->localize(I18n::TXT_KEY_NOTIF_OUTDATED_CONFIG);
    if (message.empty())
        return;
    for (const auto& notice : Notification::overlay()->getNotifications()) {
        if (notice->icon() == ICON_WARNING && notice->text() == message)
            Notification::overlay()->dismissNotification(notice);
    }
}
}

APICALL EXPORT std::string PLUGIN_API_VERSION() { return HYPRLAND_API_VERSION; }

APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE) {
    if (std::string(__hyprland_api_get_hash()) != __hyprland_api_get_client_hash())
        throw std::runtime_error("Hyper Fusion startup notices need rebuilding for this Hyprland ABI");
    // Config plugins load after the executor registers its startup checks, but
    // before the first render. No function hooks, timers or notification reset.
    startListener = Event::bus()->m_events.start.listen(acknowledgeConfigNotice);
    acknowledgeConfigNotice(); // Also covers loading during a profile update.
    return {"Hyper Fusion startup notices", "Acknowledge the pinned release's config-format reminder", "XetalEngine", "1.0"};
}

APICALL EXPORT void PLUGIN_EXIT() { startListener.reset(); }

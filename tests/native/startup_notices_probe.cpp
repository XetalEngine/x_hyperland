// Test-only observer: inject unrelated diagnostics and inspect the first frame.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/event/EventBus.hpp>
#include <hyprland/src/i18n/Engine.hpp>
#include <hyprland/src/notification/NotificationOverlay.hpp>
#include <format>

namespace {
CHyprSignalListener start, render;
SP<SHyprCtlCommand> command;
int frames = 0, firstConfig = -1, firstGui = -1, maxConfig = 0, maxGui = 0;
struct Counts { int config = 0, gui = 0, warning = 0, error = 0; };
Counts counts() {
    Counts result;
    const auto config = I18n::i18nEngine()->localize(I18n::TXT_KEY_NOTIF_OUTDATED_CONFIG);
    const auto gui = I18n::i18nEngine()->localize(I18n::TXT_KEY_NOTIF_NO_GUIUTILS);
    for (const auto& n : Notification::overlay()->getNotifications()) {
        result.config += n->icon() == ICON_WARNING && n->text() == config;
        result.gui += n->icon() == ICON_WARNING && n->text() == gui;
        result.warning += n->icon() == ICON_WARNING && n->text() == "Fusion unrelated warning";
        result.error += n->icon() == ICON_ERROR && n->text() == config;
    }
    return result;
}
}
APICALL EXPORT std::string PLUGIN_API_VERSION() { return HYPRLAND_API_VERSION; }
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE handle) {
    if (std::string(__hyprland_api_get_hash()) != __hyprland_api_get_client_hash())
        throw std::runtime_error("Test probe ABI mismatch");
    start = Event::bus()->m_events.start.listen([] {
        Notification::overlay()->addNotification("Fusion unrelated warning", CHyprColor{}, 30000, ICON_WARNING);
        // Even an error with identical text must survive the production filter.
        Notification::overlay()->addNotification(I18n::i18nEngine()->localize(I18n::TXT_KEY_NOTIF_OUTDATED_CONFIG), CHyprColor{}, 30000, ICON_ERROR);
    });
    render = Event::bus()->m_events.render.pre.listen([](PHLMONITOR) {
        const auto c = counts();
        if (frames++ == 0) { firstConfig = c.config; firstGui = c.gui; }
        maxConfig = std::max(maxConfig, c.config); maxGui = std::max(maxGui, c.gui);
    });
    command = HyprlandAPI::registerHyprCtlCommand(handle, {"fusion-notices-probe", true,
        [](eHyprCtlOutputFormat, std::string) {
            const auto c = counts();
            return std::format("{{\"frames\":{},\"first_config\":{},\"first_gui\":{},\"max_config\":{},\"max_gui\":{},\"config\":{},\"gui\":{},\"warning\":{},\"error\":{}}}",
                frames, firstConfig, firstGui, maxConfig, maxGui, c.config, c.gui, c.warning, c.error);
        }});
    return {"Startup notice test probe", "Observe notification rendering", "XetalEngine", "1.0"};
}
APICALL EXPORT void PLUGIN_EXIT() { start.reset(); render.reset(); command.reset(); }

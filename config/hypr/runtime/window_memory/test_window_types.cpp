#include "../window_types.hpp"
#include <cassert>
#include <unordered_map>
#include <vector>

int main() {
    std::unordered_map<std::string, uint32_t> atoms;
    const std::vector<std::string> types = {"NORMAL", "DIALOG", "UTILITY", "DESKTOP", "DOCK", "TOOLBAR",
        "MENU", "SPLASH", "DROPDOWN_MENU", "POPUP_MENU", "TOOLTIP", "NOTIFICATION", "COMBO", "DND"};
    for (size_t i = 0; i < types.size(); ++i) atoms["_NET_WM_WINDOW_TYPE_" + types[i]] = i + 1;
    assert(WindowTypes::managedX11(false, {}, atoms));  // legacy, untyped app
    assert(WindowTypes::managedX11(false, std::vector<uint32_t>{9999}, atoms)); // extension type
    assert(!WindowTypes::managedX11(true, {}, atoms));
    for (uint32_t id = 1; id <= types.size(); ++id) {
        assert(WindowTypes::managedX11(false, std::vector<uint32_t>{id}, atoms) == (id <= 3));
        assert(!WindowTypes::managedX11(true, std::vector<uint32_t>{id}, atoms));
        // Menus sometimes also advertise NORMAL as a compatibility fallback.
        assert(WindowTypes::managedX11(false, std::vector<uint32_t>{id, 1}, atoms) == (id <= 3));
        assert(WindowTypes::managedX11(false, std::vector<uint32_t>{1, id}, atoms) == (id <= 3));
    }
    const auto before = atoms;
    assert(WindowTypes::managedX11(false, {}, atoms));
    assert(atoms == before); // lookup must not insert atoms
    atoms.clear();
    assert(WindowTypes::managedX11(false, {}, atoms));
    assert(atoms.empty());
    assert(WindowTypes::managedWayland(true, false));
    assert(!WindowTypes::managedWayland(false, true));
    assert(!WindowTypes::managedWayland(true, true));
    assert(!WindowTypes::managedWayland(false, false));
}

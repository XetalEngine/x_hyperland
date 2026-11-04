"""Ownership of files supplied by a desktop release.

Code, build inputs, templates and assets belong to the release. Only the
settings below merge with personal edits. Paths absent from both release
inventories are never adopted just because they are inside the profile.
"""

# Generated output, hardware-specific state and personal app selections belong
# to the recipient. Fresh-install pins must never be imposed by an update.
KEEP = frozenset({
    'control_center/displays.conf', 'control_center/workspaces.conf',
    'theme/custom-presets.json', 'theme/hyprlock-raw.conf', 'theme/startup-raw.conf',
    'wallpaper/selection.json', 'wallpaper/hyprpaper.conf', 'wallpaper/profiles.json',
    'waybar/style.css', 'waybar/updates.css', 'swaync/style.css', 'theme/current.colors',
    'theme/kitty-colors.conf', 'dolphin/config/kdeglobals',
    'dolphin/data/user-places.xbel', 'dolphin/config/user-dirs.dirs',
    'dolphin/data/konsole/Xetal-Dolphin.profile', 'dolphin/data/konsole/Xetal-Dolphin.colorscheme',
    'launcher/favorites.json', 'launcher/bar-pins.json', 'launcher/shortcuts.json',
    'launcher/favorite-layout.json', 'launcher/floating-sizes.json', 'launcher/window.json',
    'effects/window_close/rules.json',
})

# Keep this list with the settings code: adding a new editable file requires
# declaring it here. State/cache directories are excluded separately by the
# update engine, and therefore need no per-file entries.
PREFERENCES = frozenset({
    'hyprland.conf', 'hyprlock.conf', 'keybindings.conf', 'kitty.conf', 'xdph.conf',
    'control_center/appearance.conf', 'control_center/input.conf', 'control_center/theme.conf',
    'cursors/settings.json', 'desktop_menu/config.json',
    'desktop/config/mimeapps.list', 'desktop/environment.conf',
    'dolphin/config/dolphinrc', 'dolphin/config/kservicemenurc',
    'effects/burn/settings.conf', 'effects/cube/settings.json', 'effects/minimize/settings.conf',
    'effects/window_close/settings.conf', 'effects/window_close/drag-settings.json', 'effects/wobbly/settings.json',
    'file_jobs/preferences.json',
    'file_manager/automount.json',
    'recording/settings.json',
    'startup/fastfetch.jsonc', 'startup/kitty.conf', 'startup/projects.json', 'startup/window-rules.conf',
    'swaync/config.json', 'switcher/preferences.json', 'terminal_fetch/settings.json',
    'theme/state.json', 'wallpaper/default.json', 'waybar/config.json', 'waybar/options.json',
    'workspaces/rules.json',
})


def policy(name):
    if name in KEEP or name.startswith('launcher/icons/'): return 'keep'
    if name in PREFERENCES: return 'preferences'
    return 'release'

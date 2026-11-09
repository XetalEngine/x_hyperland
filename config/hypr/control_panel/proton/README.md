# Proton in Hyper Fusion

Open **Control Panel → Software & maintenance → Proton**, or run
`~/.config/hypr/scripts/control-panel.sh --section proton`.

This is the native Qt integration of XetalProton. Its downloader, launcher,
prefix configuration, dependency records and executable icon reader are included
in this directory. It builds as part of Control Panel and follows its active
theme, file dialogs and default file manager. The original application remains
usable; close its editor before changing shared settings in Control Panel.

## Getting started

1. Under **Downloads → Available**, select a provider and **Load releases**.
   Select a compatible build and **Download & install**. UMU is prepared
   automatically. Steam is optional.
2. Click **New** to create a prefix and select its Proton version. A prefix has
   its own Windows files, registry and installed dependencies. Create separate
   prefixes for independent applications, or share one for a launcher and game.
3. **Add shortcut** selects an installer or Windows program. The default is to
   launch it immediately; disable that in Settings if desired. Installers write
   into the selected prefix's `pfx/drive_c`.
4. Add the installed application's executable to the library. Double-click to
   launch it, or **Edit** its runner, arguments and compatibility options.

The first UMU launch can download its runtime. **Processes & logs** shows its
progress and errors. Windows applications and downloads keep running when the
Control Panel window is closed or minimized; reopening returns to the same
session. Logging out ends the panel and cancels its in-progress tool download.
Recoverable downloads can be resumed by selecting the same release again.

## Feature coverage

| Area | Controls |
| --- | --- |
| Prefixes | Create, import, rename, choose storage root, measure disk usage, open C: or prefix folder, remove from list, optionally delete managed prefix files |
| Library | Add, drag and drop, launch, run once, edit, duplicate, remove, executable icons and icon override, icon size, optional launch after adding |
| Prefix tools | Initialize/update, winecfg, regedit, Windows Control Panel, a direct Task Manager button and per-app context action, Explorer, cmd, graceful stop and force-stop wineserver |
| Launch settings | Per-prefix Proton and per-shortcut override, three verbs, optional UMU runtime, all original graphics/CPU/input/logging options, GameMode/gamescope/custom wrappers, custom environment |
| Commands | Read-only preview, clipboard copy, executable `.sh` export |
| Browser sign-in | Per-app custom URL schemes, URL argument template, optional normal arguments, Hyprland default handlers, output privacy, handler repair and exports |
| Downloads | All 13 original providers, search, variants, prereleases, CPU compatibility, older release pages, upstream notes, progress, cancel, retry/resume, checksum verification and staged archive extraction |
| Installed tools | Open files, choose default for a prefix, remove unused app-managed tools; selected tools and running prefixes prevent removal |
| Updates | Background check on first opening with installed tools; manual refresh; install newer matching variants alongside existing versions without changing prefix selections |
| Dependencies | All original Winetricks components, category/search filters, per-prefix records, availability in the selected Proton, installation, retry, stop and logs |
| Processes | Per-launch logs, running/exit state, terminate and force stop; simultaneous launches receive separate log files |
| Steam | Optional discovery of existing tools and prefixes; disabled by default |

Companion downloads such as Luxtorpeda, Steam Tinker Launch, Boxtron and Roberta
retain their upstream purpose; they are not offered as Windows Proton runners.
Prefixes separate application environments; they are not a security sandbox.

## Browser sign-in and app links

Select an **installed application's executable** in Library and choose
**Browser sign-in…**, or right-click its shortcut. Enable **Receive browser
sign-in links**, then enter the scheme used by the application. For example,
`grasshopper://auth/callback` uses the scheme `grasshopper`. Multiple schemes
can be separated by commas or spaces. Standard web/file schemes are reserved.

The default URL argument is `{url}`. Apps that expect a named argument can use
`--url={url}`. This is one argument, passed intact without shell interpretation.
The checkboxes control whether normal launch arguments are included, whether
the app remains the default for these links in Hyprland, and whether app output
and Proton debug logs are hidden. Callback output is always hidden. Keep output
privacy enabled for sign-in apps because they may print credentials. Existing
processes retain their original logging behavior until their next launch.

Save registers the handlers. Launch the app through this panel or an exported
script, then start sign-in **inside the app**. Complete it in your Linux browser
and allow the browser's open-application prompt. The callback uses the runner,
prefix and command recorded at the app's last launch, even if the shortcut was
subsequently edited. The app still validates its authentication state; a success
tab from an older login attempt cannot authenticate a newer attempt.

**Repair link handlers** restores saved associations. Disabling the feature or
removing the shortcut removes its handlers, restoring earlier defaults only
while this panel still owns them. Duplicated shortcuts start with handlers
disabled. Only one shortcut can claim a scheme as its default.

Generated desktop entries live under the Hyprland profile's
`desktop/data/applications`; defaults use `hyprland-mimeapps.list` in the active
config home and existing isolated Hyprland app profiles. Shared `mimeapps.list`
and KDE preferences are not changed. Private manifests and launch snapshots
live in XetalProton's `desktop-handlers` directory. No background service is
installed, and link handling works while Control Panel is closed.

For shortcuts with browser sign-in enabled, **Export .sh** uses the installed
handler helper and saved manifest, repairs associations at launch and accepts
additional app arguments. Keep the shortcut and Hyper Fusion profile installed.
Other shortcuts continue to export standalone Proton commands.

The **Task Manager** toolbar button uses the selected app's prefix, Proton
override and runtime choice, or the selected prefix's defaults if no app is
selected. The same action is available in the app's right-click menu.

## Data and updates

Existing `~/.config/XetalProton/config.json` and
`~/.local/share/XetalProton/` are used directly. The original `XDG_CONFIG_HOME`,
`XDG_DATA_HOME` and `XETALPROTON_HOME` overrides still work. No migration, reset or
copy of personal prefixes is performed. Control Panel detects concurrent config
changes and preserves unknown configuration fields when saving. Invalid config
files are reported and never overwritten with defaults.

Desktop installation and updates deliver source and rebuild Control Panel.
Proton, UMU, runtime containers, Windows software, prefixes, logs and caches stay
in private XetalProton storage. Tool releases download from the original public
upstreams; neither binaries nor credentials are included in the desktop source.
The publisher's KVM service is unrelated to this downloader.

## Build and verification

The backend needs C++20, libcurl >= 7.85, libarchive, OpenSSL Crypto and threads.
The page uses the existing Qt Widgets/Concurrent stack. JSON and image-reader
headers are vendored, so building this integration makes no source downloads
and needs neither ImGui, GLFW nor Vulkan development libraries. Setup supplies
the additional development packages and `cabextract` for Winetricks.

```sh
cmake -S config/hypr/control_panel/backend -B config/hypr/control_panel/.build \
  -DBUILD_PROTON_TESTS=ON
cmake --build config/hypr/control_panel/.build \
  --target CachyOsTools proton_core_tests proton_page_tests --parallel 4
ctest --test-dir config/hypr/control_panel/.build/proton --output-on-failure
```

The offline backend checks cover archives, checksums, download recovery,
cancellation, update matching, removal, prefix locks and command construction.
Qt tests exercise prefix separation with real child processes, the native
shortcut editor, dependencies, configuration preservation and export.
Handler tests cover real callback argv forwarding, launch snapshots, default
restoration, external edits, rejected schemes, prefix locks and write rollback.
The HTTPS recovery test binds a temporary local socket.

Optional network checks use disposable storage:

```sh
config/hypr/control_panel/.build/proton/proton_core_tests --upstream
xvfb-run -a config/hypr/control_panel/.build/proton/proton_core_tests --proton-smoke
```

`--upstream` checks the provider feeds and installs/runs UMU's help command.
`--proton-smoke` downloads a real Proton and runtime and runs `cmd.exe` in a new
temporary prefix. It does not qualify individual Windows applications or games.
`XETALPROTON_OFFLINE=1` disables the page's automatic initial update check for
isolated GUI tests; manually requested network operations remain available.

## Origin

`ORIGIN.json` records the supplied XetalProton revision and original source
hashes. The Qt frontend replaces the original ImGui presentation. Backend changes
validate environment variable names for exported commands and give each launch
its own log filename. The native controller adds atomic configuration saves,
preservation/conflict checks, asynchronous removal, and constrained prefix
deletion. Icon extraction runs off the UI thread.

Control Panel's integration uses its existing [GPLv3](../LICENSE). Bundled
`nlohmann/json` 3.11.3 retains its MIT notice in
`third_party/nlohmann/LICENSE.MIT`; `stb_image.h` includes its complete
MIT/public-domain license. Downloaded tools retain their upstream terms.

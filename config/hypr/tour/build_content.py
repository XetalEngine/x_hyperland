#!/usr/bin/env python3
"""Author and bundle the offline tour. No network or installed preferences needed."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CHAPTERS = [
    ('start','Start here','01','Small steps you can try now'),
    ('windows','Windows & workspaces','02','Make space for your work'),
    ('design','Make it yours','03','A desktop with your personality'),
    ('files','Files & the desktop','04','Find, organize, and move things'),
    ('capture','Capture & share','05','Show what happened'),
    ('settings','Everyday settings','06','Sound, screens, and connections'),
    ('system','Tools & recovery','07','Look after your system'),
    ('kvm','Virtual machines','08','Another computer, on your terms'),
]
LESSONS = []


def lesson(id, chapter, title, summary, where, steps, *, level='Beginner', keys='',
           note='', tryit='', related='', tags='', image='', clip='', sources=''):
    LESSONS.append(dict(id=id, chapter=chapter, title=title, summary=summary, where=where,
        steps=steps, level=level, keys=keys.split('|') if keys else [], note=note, tryit=tryit,
        related=related.split(), tags=tags, image=image, clip=clip, sources=sources.split(),
        minutes=max(1,round(sum(len(s.split()) for s in [summary,*steps,note,tryit])/130))))


lesson('window-modes','start','First: choose how windows behave',
    'A workspace is one screenful of windows. Each workspace can use its own mode. Start with these four.',
    'Taskbar → mode button between Keys and Update',[
    'KDE — the default: overlapping windows with title bars. Click the bar’s gear. Set Apply to: All windows of this app · remembered. Tick Add a title bar above the app to add it; untick to remove it. Click Apply.',
    'Individual — each app keeps its own window behavior. Hold Super over a window to reveal its extra controls.',
    'Force tiling — windows fit beside each other. Open another app and the layout makes room for it.',
    'Force floating — windows overlap and can be placed freely. Hold Super and drag with the left mouse button to move one.',
    'Click the mode button to cycle in that order. To choose directly, right-click a workspace number → Force window layout.'],
    keys='Super + left drag|Super + right drag',
    note='Super is usually the Windows-logo key. Modes stay saved for each workspace. To restore a hidden KDE title bar, hold Super over the app, click its gear, tick the box again, then Apply.',
    tryit='Try the four modes, then return to KDE. Move a window with Super + left drag. Resize it with Super + right drag.',
    related='move-window window-controls window-gear workspace-force',tags='KDE individual four modes force tiling floating keys update title bar per app resize',
    image='workspace-force.webp',sources='workspaces/README.md waybar/options/workspace_menu.h effects/window_close/window_settings.py keybindings.conf')

lesson('move-window','windows','Move and resize windows with Super',
    'Hold Super and drag: the left mouse button moves; the right mouse button resizes.',
    'Point inside a window → hold Super + a mouse button',[
    'Put the pointer inside the window.',
    'To move it: hold Super and the left mouse button. Drag the window to its new place.',
    'To resize it: hold Super and the right mouse button. Drag to make the window bigger or smaller.',
    'Release the mouse button, then Super. In Force tiling, a moved window rejoins the layout when dropped.'],
    keys='Super + left drag|Super + right drag',tryit='Move a window, then make it larger with Super + right drag.',
    related='window-modes tile-float',image='tile-float.webp',clip='tile-float',sources='keybindings.conf workspaces/README.md')

lesson('media-download','capture','Save a YouTube song or video',
    'Choose MP3 for sound, or MP4 for video with sound.',
    'Super + Ctrl + P → Media downloader',[
    'Copy the YouTube link from your browser’s address bar.',
    'Press Super + Ctrl + P. Click Paste in the downloader.',
    'Click MP3 · Music or MP4 · Video. Check the Save to folder shown below.',
    'Click Download MP3 or Download MP4. When it finishes, click Open file to play it, or Open folder to find it.'],
    keys='Super + Ctrl + P',related='file-browser recording',tags='youtube music mp3 mp4 download video audio',
    image='media-download.webp',sources='keybindings.conf media/app.py media/backend.py')

lesson('welcome','start','Welcome to Hyper Fusion',
    'Learn one small action at a time. Keep this guide open while you try it.',
    'Taskbar → Apps · Super + D → welcome dashboard',[
    'Super is usually the Windows-logo key. Hold it while pressing the other key shown in a shortcut.',
    'Click Apps, type an app’s name, then click its result to open it.',
    'Start the guided tour with the four window modes. Click Next after each lesson.',
    'Use the search box here whenever you forget a step. Press Super + D to reopen the welcome dashboard.'],
    keys='Super + D',related='window-modes apps settings-map',image='desktop.webp',sources='keybindings.conf startup/README.md')

lesson('apps','start','Find and launch your apps',
    'The Apps menu combines search, categories, favorites, and your own shortcuts. The icons and panels follow your selected designs.',
    'Taskbar → Apps',[
    'Press Super + R or Super + Space, then type a name. Select a result to launch it. Use categories for browsing and Favorites for the things you open daily.',
    'A normal Apps-menu launch requests tiling. Ctrl-click launches a floating window. A workspace that forces tiled or floating windows can override that request.',
    'Right-click an app for its shortcut menu. You can pin it, customize its icon, assign a hotkey, edit its properties, or create your own shortcut.',
    'Favorite groups organize your personal layout. Changes here belong to this Fusion menu; an edited shortcut does not replace the application itself.'],
    keys='Super + R|Super + Space',tryit='Launch Fusion Files normally, then try Ctrl-clicking its entry on a workspace without a forced layout.',related='shortcuts-editor workspace-force file-browser',image='apps.webp',sources='launcher/app.py launcher/shortcuts.py runtime/window_memory/README.md')

lesson('shortcuts-editor','start','Make a shortcut work your way',
    'Give an app a useful name, a recognizable icon, a working folder, and a keyboard shortcut. Optional administrator and terminal settings live in its properties.',
    'Apps → right-click an app → Properties / Assign hotkey',[
    'Edit Name and Command. Browse for an executable when needed. Quote paths containing spaces; the command should point to the actual program.',
    'Choose an icon, description, and optional working folder. Enable terminal launch for tools that need a terminal, and keep the terminal open if you want to read their output.',
    'Use Always start floating for shortcut launches that honor its saved preference, such as a pinned launcher or hotkey. Apps-menu click behavior and workspace overrides are explained in the related lessons.',
    'Run as administrator routes the command through Fusion’s authentication flow. Authentication can be required by the system’s policy; do not prepend a password or embed one in the command.',
    'Save the shortcut, then test it. Hotkeys can be reviewed and changed in Fusion Settings → Hotkeys. Super + Escape opens the configured system monitor by default.'],
    keys='Super + Escape',note='Administrator mode is for applications that actually need elevated access. A saved shortcut is not a promise of permanent password-free authorization.',related='hotkeys workspace-force',tags='sudo root taskman admin custom app properties pin',image='shortcut.webp',sources='launcher/shortcuts.py launcher/hotkey_dialog.py keybindings.conf')

lesson('dashboard','start','Your welcome dashboard',
    'System information, an animated console, desktop health checks, and project cubes share the Welcome workspace. The Tour and Send Feedback buttons are always easy to find here.',
    'Super + D',[
    'Press Super + D to show the dashboard on the active monitor. Press it again to return to your work. Its windows are reused, and closed dashboard panels can be recreated.',
    'Take the Tour opens this local guide. Send Feedback opens the Echo instructions and a copyable report template. Neither button sends a message for you.',
    'The fusion-check panel shows desktop health checks at login. Review any failures before relying on the affected feature.',
    'Project cubes open their individual websites. The dashboard hides before opening a browser so it does not cover the destination.',
    'Show this dashboard at login controls automatic display at the next login. Turning it off keeps Super + D available.'],
    keys='Super + D',related='welcome settings-map',image='welcome.webp',sources='startup/README.md startup/projects.py')

lesson('settings-map','start','Which settings window do I need?',
    'Fusion Settings handles how the desktop feels. Control Panel handles system tools. KVM Settings handles your virtual machines.',
    'Apps → Fusion Settings / Control Panel / KVM',[
    'Fusion Settings: hotkeys, audio, network, Bluetooth, displays, input, themes, icons, context menus, default apps, calendar, recorder, system controls, and terminal welcome.',
    'Control Panel: storage, backups, boot appearance, packages, system information, maintenance, shell and startup tools. Its search finds tools by name or purpose.',
    'KVM Settings: choose a VM edition, prepare a guest, edit hardware, run preflight checks, and launch Virtual GPU, Single GPU, or Dual GPU sessions.',
    'Most editors separate previews from Apply. Discard restores a draft; Reload rereads saved settings. Read each page’s status before closing an unfinished edit.'],
    keys='Super + K',related='theme-presets control-panel vm-start',image='settings.webp',sources='control_center/app.py control_panel/tools.json kvm/app.py')

lesson('window-controls','windows','Hold Super. Meet your window controls.',
    'Fusion adds controls to managed windows—even applications with no convenient title bar. Hold Super while your pointer is over a window to reveal them.',
    'Hover a window + hold Super · Fusion Settings → Hotkeys → Window buttons…',[
    'Keep Super held and move to the controls. Minimize sends the app to its Fireball slot. Close asks the app to close normally, including its own unsaved-work prompts.',
    'Tile joins the window to the shared tiling layout. Restore can return a tiled or maximized window to its remembered floating size. Maximize uses the available area. Available controls depend on the window’s current mode.',
    'The gear edits visibility, placement, size, and background for this window or app. Releasing Super normally hides the buttons. Moving or resizing hides them temporarily until the movement settles.',
    'If they do not appear, check the global enable setting and the hovered workspace’s Force modifier buttons setting. Workspace Off hides even the gear while Super is held.'],
    keys='Hold Super|Super + Z|Super + C',tryit='Open a practice window, hold Super, and use Minimize. Restore it from the dock.',related='window-gear workspace-force minimize',tags='artificial titlebar decorations maximize restore close tile missing buttons',image='window-controls.webp',clip='window-controls',sources='effects/window_close/README.md effects/window_close/page.py')

lesson('window-gear','windows','Customize controls for one app—or a whole workspace',
    'The gear offers a live preview on the target window. You decide whether a change is temporary or remembered.',
    'Hold Super over a window → gear',[
    'Choose the destination before applying: this live window, all windows of this app, or the workspace when its shared controls are enabled. A window-only override ends when that window closes.',
    'Choose modifier-only, always visible, nearby-pointer, or Off. Adjust button size, corner or edge, inset, and pointer distance. The gear stays discoverable with Super unless the workspace explicitly forces controls Off.',
    'Auto background follows the window beneath the buttons. Manual color and Pick from screen let you choose a different background. The live preview is temporary until Apply.',
    'Use inherited settings removes the selected override after Apply. Closing the editor discards an unapplied preview. Workspace choices take priority over app and live-window choices.'],
    level='Intermediate',note='For a workspace’s shared controls, right-click its number → Force modifier buttons → Settings…; this also works when the workspace is empty.',related='workspace-force window-rules',image='window-gear.webp',sources='effects/window_close/README.md workspaces/README.md')

lesson('tile-float','windows','Tile, float, move, and resize',
    'Tiled windows share the workspace. Floating windows have independent sizes and positions. You can use both in a normal workspace.',
    'Window controls · Fusion Settings → Hotkeys → Window hover',[
    'Super + V toggles floating. Super + J changes the tiling split. Pseudotiling (Super + P) lets a tiled window keep a preferred size within its tile.',
    'Hold Super and drag with the left mouse button to move a window. Use the right mouse button with Super to resize. The exact gesture settings can be customized.',
    'Super + arrow moves focus. Super + Shift + arrow moves a window. Super + Ctrl + arrow resizes it in steps.',
    'Super + Shift + F toggles fullscreen. Super + F brings a floating window forward; Super + B sends it back. These are different operations.',
    'When Force tiled or Force floating is set on the workspace, its policy wins. Choose Individual before switching one window’s mode.'],
    keys='Super + V|Super + Shift + F|Super + left drag|Super + right drag',related='workspace-force window-controls monitors',image='tile-float.webp',clip='tile-float',sources='keybindings.conf workspaces/README.md')

lesson('workspaces','windows','Workspaces—and why the + button stops working',
    'A workspace is a separate arrangement of windows. Cube mode deliberately gives every monitor a fixed set of four workspace faces.',
    'Taskbar → numbered workspace buttons · Theme → Window effects → Desktop Cube + 3D',[
    'With Cube enabled, each monitor has local faces 1–4. Super + 1–4 switches the monitor under the pointer; Super + Shift + 1–4 moves the active window. Super + mouse wheel cycles faces.',
    'The taskbar + and remove controls are unavailable because adding or removing a face would break the fixed four-face arrangement. Number shortcuts 5–0 do nothing in this mode. This is expected.',
    'For freely added workspaces, open Desktop Cube + 3D and disable Cube. The + and remove controls return, together with normal global workspace numbers and shortcuts.',
    'Special workspaces such as Welcome and Stash remain separate from cube faces. Existing excess workspaces may be folded into face four when Cube is enabled; disabling it can restore their original placement if you have not moved them manually.'],
    keys='Super + 1–4|Super + Shift + 1–4|Super + wheel',tryit='With Cube enabled, switch between faces 1 and 2. Notice the + control is unavailable.',related='cube workspace-force magic',tags='plus new workspace add grey disabled four sides 3d cube ceiling',image='cube.webp',clip='cube',sources='effects/cube/README.md scripts/workspace.py scripts/new-workspace.py')

lesson('workspace-force','windows','Force a window layout for one workspace',
    'Make one workspace a tiled workbench and another a floating canvas. These choices apply to existing, newly opened, and incoming windows.',
    'Right-click a numbered taskbar workspace',[
    'Force window layout offers KDE, Individual, Force tiling, and Force floating. KDE adds title bars; Individual lets each app use its own behavior.',
    'Force tiling fits windows together. Force floating lets them overlap. Choosing Individual keeps the current arrangement and allows normal mode changes again.',
    'Force modifier buttons is independent: Individual uses app/window preferences, On shows shared controls, and Off hides all artificial controls even under Super. Native app title-bar buttons are unaffected.',
    'With controls On, the gear edits shared workspace appearance. Settings… in the submenu opens the same editor even for an empty workspace. Switching back to Individual preserves your existing app choices.',
    'These overrides persist across logins. Cube’s displayed face number maps to the actual workspace, so use the right-click menu on the intended monitor.'],
    level='Intermediate',tryit='On an empty workspace, choose Force floating, open two practice windows, then return to KDE.',related='window-rules window-gear workspaces',tags='force layout tiling floating override precedence right click workspace controls always on',image='workspace-force.webp',clip='workspace-force',sources='workspaces/README.md waybar/options/workspace_menu.h')

lesson('window-rules','windows','Remember behavior with Window Rules',
    'Rules describe future windows by application and, optionally, title. They can also give matching apps their own controls.',
    'Fusion Settings → Hotkeys → Window buttons… → Window Rules',[
    'Add a rule and select or enter the application class. Matches are case-sensitive. Use * for any text and ? for one character; leave the title blank to match all windows of that app.',
    'Choose behavior such as floating, workspace, size, or position. Size and position apply to floating windows. Keep a rule narrow when an app has several different kinds of window.',
    'Later matching rules win. Workspace Force tiled / Force floating takes priority over a rule’s mode. Workspace controls On / Off also takes priority over rule button settings.',
    'Apply the changes. Behavior rules take effect when matching windows next open; button changes apply immediately. Reopen a practice window to verify the rule.'],
    level='Advanced',related='workspace-force window-gear tile-float',tags='class title wildcard regex match behavior precedence app rule remembered geometry',image='rules.webp',clip='window-rules',sources='window_rules/page.py window_rules/model.py')

lesson('switcher','windows','Switch apps: Super + Tab',
    'Reach an open app without looking for it on the desktop.',
    'Super + Tab',[
    'Hold Super and tap Tab. The task switcher appears.',
    'Keep holding Super. Tap Tab again until the app you want is highlighted. Add Shift to go backward.',
    'Release Super to open that app’s window, even if it is on another screen or workspace.'],
    keys='Super + Tab|Super + Shift + Tab',tryit='Switch to Files, then switch back to this guide.',
    related='minimize workspaces',image='switcher.webp',sources='switcher/README.md keybindings.conf')

lesson('magic','windows','Keep a spare window in Stash',
    'Stash is a special scratch workspace for windows you want nearby without occupying your regular layout.',
    'Super + Shift + S / Super + S',[
    'Focus a practice window and press Super + Shift + S to send it to Stash.',
    'Press Super + S to show or hide Stash. The app keeps running while hidden, and the taskbar retains its Stash entry while it contains windows.',
    'Bring a window back with your ordinary move-to-workspace shortcut. Stash is separate from Cube’s four faces; it is also different from minimizing to the dock.'],
    keys='Super + Shift + S|Super + S',related='workspaces minimize switcher',image='workspaces.webp',sources='keybindings.conf README.txt')

lesson('monitors','windows','Work comfortably across monitors',
    'Each output can have its own workspace view, wallpaper, and minimized-window dock. Keep the pointer’s monitor in mind when using Cube shortcuts.',
    'Fusion Settings → Displays',[
    'Arrange monitors to match their physical positions, then choose resolution, refresh rate, scale, rotation, and other available display options.',
    'Use the display page’s preview and confirmation flow. If a new configuration is unreadable, let its timed recovery revert the change instead of confirming it.',
    'Super + Alt + Left/Right moves a window to the previous or next monitor. In Cube mode, workspace switching uses the monitor under the mouse.',
    'An edge dock appears as your pointer approaches its own monitor’s boundary. Left and right proximity also work along shared display boundaries.'],
    level='Intermediate',keys='Super + Alt + Left|Super + Alt + Right',related='workspaces minimize',image='displays.webp',sources='control_center/display_page.py control_center/display_guard.py effects/cube/README.md')

lesson('theme-presets','design','Choose a theme without losing your personality',
    'A preset can style the entire desktop or only the pieces you select. Binary Knife Dark is the fresh-install starting point.',
    'Fusion Settings → Theme → Presets',[
    'Select a design and a color mode, then review the components selected for application. Use a full preset when you want a coordinated look.',
    'For a partial change, select only the components you want. A color change can leave your chosen dock, icons, wallpaper, or launcher design independent.',
    'Apply the preset and let the desktop finish refreshing. Save a custom preset to keep a combination you want to revisit.',
    'The tour uses the desktop palette when opened from Welcome. Its screenshots show example designs; controls and locations remain the same across themes.'],
    related='mix-match icons waybar wallpaper',image='themes.webp',clip='theme-icons',sources='theme/presets.py theme/preset_page.py')

lesson('mix-match','design','Mix your favorite pieces',
    'You can borrow one theme’s taskbar, another’s dock, and a third set of icons. Matching is a choice.',
    'Fusion Settings → Theme → Mix & match',[
    'Select a component such as Waybar style, dock design, navigation, launcher, or another available surface. Preview a style and apply the combination you want.',
    'Follow desktop theme keeps a component linked to the active design. An explicit design stays pinned until you change it or apply a preset that includes that component.',
    'The file-transfer, task-switcher, cursor, wallpaper-selector, and icon pages provide their own previews and controls. Use those pages for detailed behavior.',
    'Save your result as a custom preset. Check its component choices before reapplying it later.'],
    related='theme-presets waybar minimize icons',image='mix-match.webp',sources='theme/mix_page.py theme/presets.py')

lesson('waybar','design','Style and organize the taskbar',
    'Waybar is the taskbar. Each theme offers its own design with Full, Partial, and centered-workspace layout variants.',
    'Right-click taskbar → options · Theme → Mix & match',[
    'Choose a taskbar design independently from the desktop colors. Full uses a continuous panel; Partial separates groups into pieces; the centered variation places workspace controls in the middle.',
    'Use the taskbar’s context menu to choose visible modules and other available options. Workspace-specific commands appear when you right-click a workspace number.',
    'Update Ready indicates a desktop update. Hide Update Ready hides its indicator; Show Update Ready brings it back. Hiding the indicator does not install or remove an update.',
    'System and media modules open their relevant tools. The session/power control opens the compact power menu. Pin your frequently used shortcuts where supported.'],
    related='workspaces workspace-force updates power',tags='waybar taskbar panel full partial center separate modules cpu ram update ready',image='taskbar.webp',sources='waybar/options/workspace_menu.h theme/mix_page.py')

lesson('wallpaper','design','Change your wallpaper: Super + W',
    'Pick a picture, then choose which screen should use it.',
    'Super + W → wallpaper selector',[
    'Press Super + W to open the wallpaper selector.',
    'Scroll through the pictures, or type in Search. Press Enter on your chosen picture; in Frame Lab or Orbit Atlas, you can also click Use wallpaper.',
    'Choose the screen in the display picker and confirm. Press Escape when you are finished.',
    'For your own pictures, use Add / remove folders. Your wallpaper choice stays saved after login.'],
    keys='Super + W',related='wallpaper-motion theme-presets',image='wallpapers.webp',sources='wallpaper/README.md theme/page.py')

lesson('wallpaper-motion','design','Animated wallpapers, transitions, and slideshows',
    'Build a collection that changes over time, or keep one animated scene. The library and the desktop are separate views.',
    'Wallpaper selector · Theme → Wallpapers',[
    'Preview the selected media before applying it. Video previews and desktop playback use the supported local media backend; unsupported or missing files need to be replaced.',
    'Choose a transition and slideshow timing from the available controls. Use your own folders rather than moving the original collection behind a saved path.',
    'For multiple monitors, confirm the target display before applying. The theme’s wallpapers can be mixed with another theme’s interface.',
    'If a video stutters, try a lower-resolution clip or a still picture. A preview is a useful way to compare options before changing the whole desktop.'],
    level='Intermediate',related='wallpaper monitors',image='wallpapers.webp',sources='wallpaper/README.md theme/page.py')

lesson('icons','design','System Icons, Other Icons, and Individual Icons',
    'Fusion has an original system icon set for every desktop design. You can also use an installed or imported full icon pack.',
    'Fusion Settings → Theme → Icons',[
    'System Icons shows visual cards for the Fusion sets. Follow desktop theme keeps them coordinated, or select a different design independently.',
    'Other Icons chooses the installed app-icon pack and offers import for an extracted, self-contained icon theme. Use this set for System Icons too if you want the complete aftermarket look.',
    'Individual Icons lets you select a role, choose an image, borrow one icon from another Fusion design, or reset its override.',
    'Apply to update the launcher, desktop, Fusion Files, file dialogs, and other integrated tools. Changing artwork keeps the shortcut’s application and command intact.'],
    related='mix-match desktop-icons file-browser',image='icons.webp',clip='theme-icons',tags='papirus aftermarket custom override individual system icons import pack',sources='icon_themes/page.py icon_themes/model.py')

lesson('minimize','design','Put an app in the minimize dock',
    'Minimize tucks a window away. The app keeps running.',
    'Super + Z · Fusion Settings → Theme → Window effects → Minimize',[
    'Click a window, then press Super + Z. Or click its − button. The window moves into the minimize dock.',
    'If the dock hides, move the pointer to its screen edge. With Opposite Waybar selected, use the edge opposite your taskbar.',
    'Click the app’s dock icon to bring its window back.',
    'To customize it, press Super + K → Theme → Window effects → Minimize. Choose a dock design, position, and hiding effect. Click Apply Minimize.'],
    keys='Super + Z',tryit='Minimize Files, reveal the dock, then click Files to restore it.',
    related='window-controls mix-match workspaces',image='dock.webp',clip='minimize',sources='effects/minimize/README.md effects/minimize/model.py')

lesson('cube','design','Turn the desktop cube',
    'The cube’s four sides are four workspaces. Turn it to reach another set of windows.',
    'Ctrl + Alt + left mouse drag',[
    'Put the pointer on the screen you want to turn.',
    'Hold Ctrl and Alt. Hold the left mouse button too, then drag left or right.',
    'Release to land on the nearest side. Press Escape or right-click to cancel a turn.',
    'To change its look, press Super + K → Theme → Window effects → Desktop Cube + 3D. Enable Cube there if the gesture is off.'],
    keys='Ctrl + Alt + left drag|Escape',tryit='Turn to side 2, then turn back to side 1.',
    related='workspaces effects monitors',image='cube.webp',clip='cube',sources='effects/cube/README.md effects/cube/page.py')

lesson('effects','design','Wobble, burn, and pointer effects',
    'Window effects have individual controls. Choose the motion you enjoy, and keep the rest calm.',
    'Theme → Window effects',[
    'Wobbly Windows changes how a moved window flexes. Preview the effect on a practice window and adjust the available strength and timing controls.',
    'Burn animates closing a window. It is separate from the minimize Fireball and from the dock’s Burn away hiding style.',
    'Mouse effects and cursors offer their own styles and behavior. Use a clear pointer and modest effects if detailed work or recording needs visual precision.',
    'Apply one group at a time so you can judge its effect. Disabling an effect does not uninstall your apps or change their files.'],
    related='cube minimize window-controls',image='effects.webp',sources='effects/wobbly/README.md effects/burn/README.md cursors/README.md')

lesson('terminal','design','Give your terminal a welcome',
    'Fusion’s terminal welcome can show selected system information with a changeable logo, colored to match the desktop.',
    'Fusion Settings → Terminal',[
    'Choose whether the welcome appears in new Fusion terminals. Select a logo and review its preview.',
    'Enable only the information you want: system, hardware, shell, desktop, and other available fields. Refresh information updates the preview.',
    'Save terminal to use these choices for new terminals. Existing terminal output is not rewritten. Theme colors and the selected logo can be mixed independently.'],
    keys='Super + Q|Super + Enter',related='theme-presets hotkeys',image='terminal.webp',sources='terminal_fetch/page.py keybindings.conf')

lesson('file-browser','files','Find your way around Fusion Files',
    'Folders on the left. Files in the middle. Start with Home or This PC.',
    'Super + E · Apps → Fusion Files',[
    'Press Super + E to open your default file manager. On a fresh install, that is Fusion Files. Click Home, Downloads, or Documents on the left.',
    'Double-click a folder to open it. Click the back arrow to return. Press Ctrl + L to type a folder path.',
    'Click This PC for drives. Your system and mounted drives come first, followed by connected removable devices, Wine/Steam drives, and unmounted devices.',
    'Press Ctrl + T for another tab. Press Ctrl + F to search for a file or words inside it.',
    'Click ⋮ → Configure Fusion Files… → Browsing to change previews and thumbnails. Under Appearance, follow the current desktop theme or choose a theme just for Files. Click Save.'],
    keys='Super + E|Ctrl + L|Ctrl + T|Ctrl + F',tryit='Open Downloads in one tab and Documents in another. Switch between them.',
    related='file-transfers archives picker',image='fresh-files.png',clip='files',sources='file_manager/README.md keybindings.conf')

lesson('desktop-icons','files','Turn the desktop into a useful workspace',
    'Desktop icons can show real files and folders with saved positions, selection, drag-and-drop, and full file actions.',
    'Right-click empty desktop space',[
    'Enable Show Desktop icons. Use Arrange icons to choose rows or columns, automatic alignment, and automatic arrangement. Free positioning is available when arrangement is off.',
    'Double-click to open an item. Select several items for a group operation. Rename, copy, cut, paste, and move to Trash from the context menu or supported keys.',
    'Enable the optional Trash icon if you want a permanent target. It represents the trash location; it is not an ordinary folder called Trash on your desktop.',
    'Configure the desktop context menu to choose its actions and appearance. Icon design comes from Theme → Icons. A custom shortcut image can remain its own choice.'],
    related='archives file-transfers icons',image='desktop-icons.webp',sources='desktop_menu/README.md desktop_menu/desktop_icons.py')

lesson('archives','files','Right-click actions and Ark archives',
    'The file context menu brings installed archive actions to Fusion Files and the desktop. Its contents depend on the selected files.',
    'Right-click a file or folder · Fusion Settings → Context Menu',[
    'Select the items you want to archive. Right-click and choose the available compress/archive action supplied by Ark. Choose a name and format in its dialog.',
    'For an existing archive, use the relevant extract action or Open with Ark. Check the destination folder before extracting many files.',
    'If an action is missing, confirm Ark is installed and its service action is enabled in the file-menu configuration. Empty-space desktop menus and file-selection menus are separate contexts.',
    'The configuration page can organize the desktop menu and its actions. Test changes on ordinary sample files before relying on a customized workflow.'],
    related='desktop-icons file-browser',image='context-menu.webp',sources='file_manager/README.md desktop_menu/README.md control_center/context_menu_page.py')

lesson('file-transfers','files','Copy folders without babysitting them',
    'Fusion starts copying right away and counts files in the background. A problem with one file does not hold up the others.',
    'Fusion Files → select files or folders → Ctrl + C',[
    'Select a file or folder. Press Ctrl + C. Open the destination folder and press Ctrl + V. Use Ctrl + X instead of Ctrl + C to move it.',
    'Watch the transfer card for file counts, speed, and progress. Pause and Resume let you take a break without starting over.',
    'If Items needing attention appears, click a row. Choose Retry, Skip item, or Replace… after checking the names. Other files keep copying.',
    'For a move between drives, Fusion checks the copied data before removing the originals. Wait for Move complete; skipped files stay in their old folder.',
    'Use Review queue to see any unfinished items. Save report… keeps their details so you can check them later.'],
    keys='Ctrl + C|Ctrl + X|Ctrl + V',tryit='Copy a small practice folder. Open the copy and check that your files are there.',
    related='file-browser picker',image='transfer.webp',tags='copy engine transfer pause resume queue conflicts verify move folders',
    sources='file_manager/README.md file_manager/transfer_worker.py file_manager/transfer_pending.py')

lesson('picker','files','Open and save dialogs that feel familiar',
    'Fusion file dialogs reuse the places and navigation you know from the file manager.',
    'An app’s Open / Save / Download action',[
    'Choose a destination with the sidebar or path bar, then enter a filename. Check the file-type filter if a file seems missing.',
    'Use Save or Open to confirm, or Cancel to return without completing the operation. Confirm a replacement only if you intend to overwrite that file.',
    'A browser’s Show in folder and the recorder’s saved notification can open Fusion Files with the relevant item selected.',
    'Some applications use their own dialogs. Which dialog appears depends on the app’s toolkit and portal support.'],
    related='file-browser recording',image='picker.webp',sources='file_manager/README.md file_manager/picker.cpp')

lesson('default-apps','files','Choose what opens your files',
    'Choose a browser, file manager, media player, or app for a particular file type. Review the association before saving it.',
    'Fusion Settings → Default Apps · Control Panel → Default Apps',[
    'Choose a role such as browser or file manager, then pick an installed app. The detailed view also searches file types, extensions, and link protocols.',
    'Save the association and open a sample file to test it. Super + E and desktop folder actions follow the selected file manager.',
    'Use Undo where offered to restore the previous association. These standard account-level file associations can also affect other desktop sessions for this account.'],
    level='Intermediate',related='file-browser settings-map',image='default-apps.webp',sources='control_panel/README.md control_center/default_apps_page.py')

lesson('screenshots','capture','Take a screenshot',
    'Capture a small region to explain a detail, or take a whole-display screenshot for context.',
    'Print / Shift + Print · Fusion Settings → System',[
    'Press Print for an area capture and select the region. Press Shift + Print for the configured screen-capture action.',
    'System’s quick actions also expose capture controls, including capture of all displays. Follow the resulting save/copy notification.',
    'For a bug report, include the whole affected window and its error message. Crop out personal messages or account details before sharing.'],
    keys='Print|Shift + Print',related='recording feedback-help',image='system.webp',sources='scripts/screenshot.sh control_center/system_page.py keybindings.conf')

lesson('recording','capture','Record your screen: Alt + F9',
    'Press once to start. Press again to stop and save an MP4.',
    'Alt + F9 · Super + K → Recorder',[
    'First, press Super + K and click Recorder. Choose your save folder, quality, FPS, and sound: desktop, microphone, or none. Click Apply recording options.',
    'Put the pointer on the screen you want to record. Press Alt + F9. Look for the REC timer in the taskbar.',
    'Do what you want to show. The recorder stays on that screen even if your pointer moves elsewhere.',
    'Press Alt + F9 again to stop. Click Show in folder in the saved notification to find your video.'],
    keys='Alt + F9',tryit='Record five seconds of moving a window. Stop, then play the saved video.',
    related='recording-options screenshots',image='recorder.webp',clip='recorder',tags='capture video screencast record screen alt f9 mp4 fps',sources='recording/README.md recording/page.py')

lesson('recording-options','capture','Tune recordings and find a failed capture',
    'Choose a balance of quality, file size, and capture load. The filename preview shows how each recording will be named.',
    'Fusion Settings → Recorder',[
    'Use filename tokens such as {date}, {time}, and {monitor}. MP4 is added automatically; existing recordings keep their names and new duplicates receive a number.',
    'Desktop audio records the selected output’s monitor source; microphone records the default input. These are separate choices, not an automatic mix of both.',
    'Automatic encoding tries available hardware options before CPU encoding. A high requested FPS does not guarantee that the display or GPU can produce that many unique frames.',
    'If saving fails, read the recovery location in the status/notification. The private capture directory can contain the recording and capture.log. Keep it until the video is recovered; temporary saving needs room for the intermediate capture and final file.'],
    level='Intermediate',related='recording audio feedback-help',image='recorder.webp',clip='recorder',sources='recording/README.md recording/page.py')

lesson('audio','settings','Sound, microphone, and media',
    'Choose where sound goes and which microphone is active. The recorder uses the devices selected when recording begins.',
    'Super + A · Fusion Settings → Audio',[
    'Pick the output device and adjust its volume. Choose the input device and microphone level separately. Check mute controls when a call or recording is silent.',
    'Use application-stream controls when you need to adjust one app without changing everything else. Available devices depend on connected hardware.',
    'Media keys control playback and volume. The taskbar’s media area reflects supported players. Use Recorder’s audio choice to decide what a capture includes.'],
    keys='Super + A',related='recording bluetooth-network',image='audio.webp',sources='control_center/audio_page.py keybindings.conf')

lesson('bluetooth-network','settings','Connect Wi-Fi, wired networks, and Bluetooth',
    'Network and Bluetooth pages keep common connection tasks close to the desktop.',
    'Fusion Settings → Network / Bluetooth',[
    'Use Network to view connections and connect to an available wired or wireless network. Supply credentials only in the connection dialog.',
    'Bluetooth lists available and paired devices. Enable discovery, select the device, and complete any pairing confirmation requested by both sides.',
    'If a device is missing, check its power, discovery mode, and the relevant radio toggle. Airplane-mode or hardware switches can disable a radio outside these pages.',
    'For VPNs or more detailed connection properties, use the available connection-management actions.'],
    keys='Super + Ctrl + N',related='audio monitors',image='network.webp',sources='control_center/app.py keybindings.conf')

lesson('hotkeys','settings','Edit shortcuts—and keep a way back',
    'Fusion’s hotkey editor keeps labels, categories, conflict checks, and a protected cancellation binding together.',
    'Super + K → Hotkeys',[
    'Find a binding by its label or category. Select it, record or enter the new combination, and review the command or action before saving.',
    'Resolve conflicts reported by the editor. During shortcut capture, Escape cancels the capture mode. Apply validates the configuration and keeps a backup of the previous version.',
    'App hotkeys can use saved shortcut properties, including administrator mode. Super + Escape initially opens the configured system monitor and can be customized like other app actions.',
    'This guide lists shipped defaults. If you changed a binding, the Hotkeys page is the authority for your current setup. Keyboard layouts may label punctuation keys differently.'],
    keys='Super + K|Escape',related='shortcuts-editor window-controls',image='hotkeys.webp',sources='control_center/keys.py control_center/app.py keybindings.conf')

lesson('input','settings','Keyboard, mouse, and touchpad feel',
    'Tune the controls to your hands, including pointer behavior and the keyboard options exposed by the desktop.',
    'Fusion Settings → Input',[
    'Review keyboard layout, repeat behavior, pointer sensitivity, scrolling, and touchpad options available for your devices.',
    'Change one group at a time, apply, and try it in a familiar window. Keep your previous values in mind when experimenting.',
    'Window drag and resize behavior has additional controls under Window buttons. Cursor design and pointer effects live under Theme.'],
    related='hotkeys window-controls effects',image='input.webp',sources='control_center/preferences_page.py effects/window_close/page.py')

lesson('power','settings','Notifications, locking, and session power',
    'The desktop offers quick power controls and a fuller System page with live resource information and capture actions.',
    'Taskbar → session/power · Apps → Session power · Fusion Settings → System',[
    'Use the compact taskbar menu for session actions. Open System for resource cards, task monitor, screenshots, notifications, and power controls.',
    'Super + N opens notification history. Super + L locks the screen. Super + M opens logout confirmation.',
    'Suspend, restart, power off, and log out affect your current work. Save documents and finish or stop guest VMs before confirming a session-ending action.',
    'Calendar and clock controls help keep appointments nearby. The available calendar features live in Fusion Settings → Calendar.'],
    keys='Super + N|Super + L|Super + M',related='screenshots vm-stop',image='system.webp',sources='control_center/system_page.py control_center/logout.py keybindings.conf')

lesson('control-panel','system','Find tools in Control Panel',
    'Use Control Panel for software, drives, network settings, and system tools.',
    'Apps → search Control Panel → open it',[
    'Click Apps, type Control Panel, then click the result.',
    'Type what you need in the search box. Try Network for connections, Packages for software, or System Tweaks for performance settings.',
    'Click a tool. Read its short description, choose your setting, then use its Apply or Save button.',
    'Click Control Panel in the top breadcrumb to return to the tool list. Use the star on a tool to keep it in Favorites.'],
    tryit='Search for System Overview and open it to see your computer’s details.',
    related='settings-map updates backups',image='control-panel.webp',tags='cachyos tools administrator system overview hardware disks packages',sources='control_panel/tools.json control_panel/README.md')

lesson('updates','system','Desktop updates versus system packages',
    'Hyper Fusion updates and distribution package updates are different jobs. The taskbar’s Update Ready item refers to the desktop updater.',
    'Taskbar → Update Ready · Control Panel → Package Updates',[
    'Open the desktop update prompt to review and apply a prepared Fusion update. Personal settings are preserved by the updater’s file policy; follow its result and recovery messages.',
    'Hide Update Ready only changes indicator visibility. Right-click the taskbar to show it again. It is not a way to disable or complete an update.',
    'Use your distribution’s package tools for operating-system packages. Control Panel exposes supported managers and repair tools; availability differs across Arch, Fedora, and Debian.',
    'Finish a running update before restarting or starting another package operation. If a refresh fails, keep the exact error and use Logs & Reports or send feedback.'],
    level='Intermediate',related='control-panel feedback-help backups',image='updates.webp',sources='updates/update_engine.py updates/file_policy.py control_panel/tools.json')

lesson('backups','system','Backups, restore points, and System ISO',
    'Choose the recovery tool that fits the job: files, a filesystem restore point, or a bootable system image.',
    'Control Panel → System Backup / System Restore / Restore Points / System ISO',[
    'System Backup selects sources and destinations; System Restore reads a backup back into place. Keep a copy on another physical device when possible.',
    'Restore Points uses supported Btrfs/Snapper snapshots. A snapshot on the same disk does not protect against loss of that disk.',
    'System ISO builds a bootable image of a selected system with exclusions and installer options. Review personal data and excluded paths before creating an image you intend to share.',
    'Drives & Storage includes operations such as writing an ISO to USB. Confirm the exact target drive and its contents before any destructive operation. Read the tool’s review and recovery steps.'],
    level='Advanced',related='control-panel grub feedback-help',image='system-iso.webp',sources='control_panel/README.md control_panel/tools.json')

lesson('grub','system','Design the screen before your desktop',
    'GRUB Boot Editor includes boot entries and an Appearance editor with bundled designs, pictures, menu placement, and lettering.',
    'Control Panel → GRUB Boot Editor → Appearance',[
    'Choose a design, then use Picture, Menu, and Colors to adjust it. The preview is an example; firmware resolution can affect the final spacing.',
    'Review & apply creates backups before final confirmation. Read the exact files being changed, their backup paths, and the recovery instructions.',
    'Take a picture of the recovery screen or save its instructions somewhere you can access without this installation. Then confirm Apply for the next boot.',
    'Use Reload design to reread the applied appearance. Undo appearance and system-appearance actions have their own review flow. Boot-entry edits are separate from appearance changes.'],
    level='Advanced',note='A preview alone changes no boot files. Keep the displayed backup paths and recovery commands before you apply.',related='backups control-panel',image='grub.webp',sources='grub/README.md control_panel/README.md')

lesson('feedback-help','system','Troubleshoot with a useful report',
    'A clear description and a short clip make a problem much easier to reproduce. Start with the smallest action that shows it.',
    'Welcome → Send Feedback · Control Panel → Logs & Reports',[
    'Write what you expected, what happened instead, and the exact steps. Include the app, desktop version, distribution, and whether it happens every time.',
    'For layout problems, note the monitor, Cube mode, and any Force window layout or Force modifier buttons choices. For theme problems, list the component designs you mixed.',
    'Capture the affected window with Print or a short Alt + F9 recording. Read the message before dismissing it; include relevant log excerpts rather than every file on your machine.',
    'Open Send Feedback in this guide for the Echo friend instructions and copyable template. Review attachments for passwords, tokens, and private content before sending.'],
    related='screenshots recording workspace-force',image='feedback.webp',tags='bug broken report help support feedback echo xetal problem',sources='control_panel/tools.json recording/README.md')

lesson('vm-editions','kvm','Choose Basic free or Enhanced free',
    'KVM Settings is included with the desktop. Editions choose the VM components and the account requirements for using them.',
    'KVM Settings → Paths & tools → KVM components',[
    'Basic free uses stock upstream QEMU and OVMF with system KVM. No Echo account is required, and it does not include the optional custom AMD module.',
    'Enhanced free is the Xetallic build 1963 edition. It uses the custom components and requires an eligible Echo account. Select Switch to Enhanced and complete Login when requested.',
    'Use Switch to Basic to return to the stock edition. Let the component installer finish and review status before launching. Your guest disks are separate from the component selection.',
    'Xetallic MAX is a coming-soon placeholder for a future NOS MAX edition. It is not an available launch choice today.'],
    level='Intermediate',related='vm-login vm-start vm-components',image='kvm-editions.webp',sources='kvm/edition_info.py kvm/edition_ui.py kvm/editions.py')

lesson('vm-login','kvm','Echo login in KVM Settings',
    'Enhanced free checks account access when you launch. The account area beside Save current setup shows your current status.',
    'KVM Settings → Login / account status',[
    'Click Login and authenticate with Echo. Check Logged in as to confirm the intended account. Account access checks can reject banned or ineligible accounts.',
    'Saving your VM setup does not make that account session permanent. Reopening KVM Settings requires another Login; remembered credentials may make entry easier.',
    'Logout ends the current KVM Settings account session. Download Echo opens the client download page if you want the full chat application.',
    'Basic free remains available without an Echo account. If login or service access fails, read the exact message and retry after checking connectivity rather than changing guest disks.'],
    level='Intermediate',related='vm-editions vm-components feedback-help',image='kvm-account.webp',sources='kvm/account_ui.py kvm/echo_account.py kvm/runtime_access.py')

lesson('vm-start','kvm','Your first VM: start with Virtual GPU',
    'Virtual GPU runs the guest in a window while Linux keeps its graphics card. It is a useful place to verify a new VM setup.',
    'Apps → KVM Settings → Wizard → Virtual GPU',[
    'Choose the Windows or Mac profile you are preparing and use Wizard to fill in the required setup. Supply the appropriate installer and guest disk; the desktop does not provide an operating-system license.',
    'Review CPU, memory, storage, firmware, and TPM choices. Keep enough host memory and CPU capacity for Linux to remain usable.',
    'In Paths & tools, install missing components for the selected edition. Complete Echo Login if using Enhanced free.',
    'Run Preflight check, fix reported missing files or setup problems, and inspect Preview command if you need details. Launch VM when checks are ready.',
    'Use Open console if the viewer is not visible. Shut down the guest normally when finished, then Save current setup or Save preset for a named configuration.'],
    level='Intermediate',related='vm-modes vm-components vm-stop',image='kvm-virtual.webp',clip='kvm',sources='kvm/app.py kvm/backend/vmstart2.py')

lesson('vm-modes','kvm','Virtual GPU, Single GPU, or Dual GPU?',
    'These modes have different relationships with the host’s graphics hardware. Choose the least disruptive mode that fits your guest.',
    'KVM Settings → Single GPU / Virtual GPU / Dual GPU',[
    'Virtual GPU runs in a viewer window. Linux keeps its GPU, and start/revert host scripts—including host reboot steps—are skipped for that run.',
    'Single GPU passes the selected graphics device to the guest. The host display can become unavailable while the guest owns it, so verify the release and recovery procedure before using it.',
    'Dual GPU keeps a host GPU while passing another to the guest. Correct device selection, IOMMU grouping, drivers, and an appropriate display/Looking Glass arrangement matter.',
    'Changing a launch mode does not remove the need for preflight checks. Review shared disk, firmware, NVRAM, and TPM identity before experimenting with the same guest across modes.'],
    level='Advanced',related='vm-start vm-passthrough vm-stop',image='kvm-virtual.webp',sources='kvm/app.py kvm/backend/vmstart2.py')

lesson('vm-components','kvm','Components, paths, firmware, and the AMD module',
    'Paths & tools shows what is installed, what is available, and which paths a launch will use. Components and guest state have different jobs.',
    'KVM Settings → Paths & tools',[
    'Check for updates and install the required components. Wait for download and verification to finish before starting a VM. Open components shows the installed component location.',
    'QEMU runs the guest; OVMF supplies UEFI firmware. Support files, virtual TPM tools, OpenCore, and Looking Glass serve specific parts of supported configurations.',
    'Guest disks, NVRAM variables, and TPM state belong to the VM’s private workspace. Back them up together when preserving guest identity; replacing a component is not a guest backup.',
    'The custom AMD KVM module is optional and specific to compatible hardware and kernel builds. A kernel mismatch or missing matching module must be resolved before selecting that module.',
    'Editing a path updates the corresponding launch argument. Prefer the managed component choices; rerun Preflight check after changing paths or editions.'],
    level='Advanced',related='vm-editions vm-start vm-config',image='kvm-editions.webp',sources='kvm/packages.py kvm/module_tool.py kvm/app.py')

lesson('vm-config','kvm','CPU, storage, network, and saved presets',
    'The editor groups VM hardware and identity so you can tune one area at a time and inspect the resulting command.',
    'KVM Settings → Hardware / Configuration / Advanced',[
    'CPU pinning and features control the guest’s CPU presentation and host scheduling choices. Memory defines guest RAM. Avoid allocating everything the host needs.',
    'Disks & storage selects guest drives; PCI & USB selects attached devices. Machine & network controls machine and connection options. Confirm device identity rather than relying only on a list position.',
    'SMBIOS identity and TPM affect how the guest identifies itself. Firmware variables and TPM state can matter for operating-system activation and disk encryption.',
    'Save current setup updates the current configuration. Save preset creates a named choice you can revisit. Preview command helps explain what the current settings will launch.',
    'Make a backup of guest data before major storage or identity changes. A saved settings preset is not a backup of a running VM’s disk contents.'],
    level='Advanced',related='vm-components vm-passthrough vm-stop',image='kvm-hardware.webp',sources='kvm/backend/vmstart2.py kvm/checkpoint.py')

lesson('vm-passthrough','kvm','Prepare hardware passthrough carefully',
    'Passing a physical GPU or PCI device gives the guest direct hardware access. Preflight and the launch/revert procedure are essential parts of this workflow.',
    'KVM Settings → PCI & USB devices / Launch procedure / Preflight check',[
    'Verify firmware virtualization/IOMMU support, the intended device and its group, and which GPU continues serving the host. Keep a recovery path before detaching the only display GPU.',
    'Review launch and revert steps in the editor. Confirm required packages, device bindings, ROM/firmware paths, and any helper setup before launching.',
    'For a windowed console, begin with Virtual GPU. For a passed-through display, use the configured physical output or supported Looking Glass arrangement.',
    'If preflight reports an error, resolve that specific requirement. Do not run arbitrary copied hardware scripts to bypass a failed check.'],
    level='Advanced',related='vm-modes vm-stop vm-components',image='kvm-hardware.webp',sources='kvm/app.py kvm/gpu_rom.py kvm/runtime_probe.py')

lesson('vm-stop','kvm','Stop a guest and diagnose a launch',
    'A launch log and preflight result are more useful than guessing. Normal guest shutdown gives the VM and host cleanup a chance to finish.',
    'KVM Settings → launch page',[
    'Use the guest’s own shutdown or Shut down guest first. Wait for Guest stopped and cleanup status before another launch or a host power action.',
    'Restart guest requests a restart. Force off is an emergency stop and can lose unsaved guest data; use it only when normal shutdown fails.',
    'If no viewer appears, check whether the guest is still running and use Open console. Read the launch log for the actual error before changing the configuration.',
    'For account failures, check Login. For missing files, check Paths & tools. For a custom-module failure, check the selected kernel/module compatibility. For passthrough problems, review Preflight and the revert procedure.',
    'Send a concise error excerpt and the edition/launch mode in feedback. Exclude passwords, account tokens, and personal guest disk contents.'],
    level='Intermediate',related='vm-login vm-components feedback-help',image='kvm-virtual.webp',sources='kvm/app.py kvm/vm_session.py')


def content():
    # The shipped key labels are taken from the same default file as the editor.
    shortcuts=[];meta=None
    for line in (ROOT/'keybindings.conf').read_text().splitlines():
        if line.startswith('# @hotkey '):
            meta=json.loads(line[len('# @hotkey '):]);continue
        if meta and re.match(r'^bind\w*\s*=',line):
            parts=line.split('=',1)[1].split(',',3)
            mods,key=parts[0].strip().replace('$mainMod','SUPER'),parts[1].strip()
            key={'code:61':'/','mouse:272':'left mouse','mouse:273':'right mouse','Return':'Enter','mouse_down':'wheel down','mouse_up':'wheel up'}.get(key,key)
            combo=' + '.join([*(m.title() for m in mods.split()),key])
            if not meta.get('protected') and not meta['label'].startswith(('exec ','Open selected application')):
                shortcuts.append({'keys':combo,'title':meta['label'],'category':meta['category']})
            meta=None
    tools=json.loads((ROOT/'control_panel/tools.json').read_text())
    return dict(version=1,chapters=[dict(id=a,title=b,number=c,summary=d) for a,b,c,d in CHAPTERS],
        lessons=LESSONS,shortcuts=shortcuts,tools=tools,
        route=['window-modes','recording','cube','move-window','media-download','wallpaper','switcher','minimize','file-transfers','control-panel','file-browser'],
        readingTheme='binaryknife',readingPalettes=json.loads((ROOT/'theme/palettes.json').read_text())['binaryknife'],
        feedback={'username':'xetal','download':'https://www.xetal.net/community/site/?p=echo'})


def build():
    target=Path(__file__).parent/'data.js'
    target.write_text('window.FUSION_TOUR = '+json.dumps(content(),ensure_ascii=False,separators=(',',':'))+';\n')
    print(f'{len(LESSONS)} lessons bundled in {target.name}')


if __name__=='__main__':build()

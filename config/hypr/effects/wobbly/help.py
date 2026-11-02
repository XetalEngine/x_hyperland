"""Window types and predicates implemented by both Wobbly matchers."""
from html import escape
from .model import TYPES

TYPE_HELP = {
    'Normal':'Ordinary application windows, such as browsers, terminals and file managers.',
    'Dialog':'Dialogs with a parent, such as Open, Save, Preferences and confirmation windows.',
    'Utility':'Small utility or tool-palette windows.',
    'Toolbar':'Detached application toolbars.',
    'Menu':'Detached or tear-off menu windows.',
    'Splash':'Application startup or loading screens.',
    'DropdownMenu':'Menus opened from a menu bar.',
    'PopupMenu':'Context menus, usually opened with a right click.',
    'Tooltip':'Small hover tips.',
    'Notification':'Notification windows.',
    'Combo':'The popup list of a combo box.',
    'Dnd':'A drag-and-drop feedback window.',
    'Unknown':'An X11 override-redirect window without a recognized type.',
    'Dock':'Dock or panel windows advertised as X11 window types.',
    'Desktop':'X11 desktop/background windows.',
    'Any':'Any eligible application window, regardless of its type.',
}

def window_help():
    rows=''.join(f'<tr><td><b>{name}</b></td><td>{escape(TYPE_HELP[name])}</td></tr>' for name in TYPES)
    return f'''<h2>Which windows?</h2><p>Use these case-sensitive names in any window field.
    The application supplies its window type; a title containing “Menu” does not make a window a Menu.</p>
    <table cellspacing="9">{rows}</table>
    <h3>Combining matches</h3><p><b>|</b> means OR; <b>&amp;</b> means AND;
    <b>!</b> excludes a match. Parentheses group expressions. AND has priority over OR.</p>
    <p><code>Normal | Dialog<br>(Normal | Dialog) &amp; !class=kitty<br>
    Any &amp; floating=1<br>Normal &amp; title=*Settings*</code></p>
    <h3>Other supported filters</h3><p><b>type=Normal</b> is the same as <b>Normal</b>.
    <b>class=</b>, <b>title=</b> and <b>role=</b> accept <b>*</b> (any text) and <b>?</b> (one character).
    Classes and titles are case-sensitive. Role is supplied by X11 applications.</p>
    <p><b>floating=</b>, <b>xwayland=</b>, <b>override_redirect=</b> and <b>rgba=</b> accept 0 or 1.
    rgba matches a window with effective opacity below 100%. <b>state=</b> accepts normal, maximized or fullscreen.
    <b>xid=</b> accepts an X11 window ID, such as 1234 or 0x1234.</p>
    <h3>What each field does</h3><p><b>Move</b> selects windows that bend during enabled drag gestures.
    <b>Grab</b> adds a spring impulse when those windows are grabbed.
    <b>Map</b> and <b>Focus</b> select windows for the corresponding effect.</p>
    <p>An empty field matches nothing. Choosing Focus effect: Shiver also requires a Focus windows match.</p>
    <h3>Wayland and XWayland</h3><p>Native Wayland top-level windows are Normal or Dialog.
    Wayland popups are part of their parent; layer-shell panels, notifications and backgrounds are not independent wobble windows.
    XWayland windows can advertise all the types listed above. Only visible, mapped application windows are eligible;
    fullscreen windows, the lock screen and windows without surfaces are excluded even with Any.</p>'''

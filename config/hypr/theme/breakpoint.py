"""Charcoal glass and restrained crimson accents for Xetal BreakPoint."""
import re


def qt_style(p):
    from designs import qt_style as base_style
    base=base_style(p).replace('"Noto Sans"','"Inter"')
    base=re.sub(r'border-radius:(1[3-9]|[2-9][0-9])px', 'border-radius:12px', base)
    return base+f'''
    /* Silver labels, burgundy selections, crimson only for focus and controls. */
    QLabel#eyebrow {{font-family:"JetBrains Mono"; color:{p['PlaceholderText']};}}
    QLabel#brand, QLabel#title, QLabel#dialogTitle, QLabel#section {{color:{p['Text']};}}
    QPushButton {{border-color:{p['Midlight']}; border-radius:8px;}}
    QPushButton:hover {{background:{p['Mid']}; border-color:{p['Accent']}; color:{p['Text']};}}
    QPushButton:checked, QPushButton#primary, QPushButton#primary:hover,
    QPushButton#share, QPushButton#format:checked {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']};}}
    QPushButton#danger, QPushButton#logout {{background:{p['Highlight']}; color:{p['Text']}; border-color:{p['Accent']};}}
    QPushButton#launcherNav {{border:1px solid transparent; border-radius:8px;}}
    QPushButton#launcherNav:checked {{background:{p['Highlight']}; color:{p['Text']}; border:1px solid {p['Accent']};}}
    QPushButton#launcherNav:hover {{background:{p['Mid']}; border-color:{p['Midlight']};}}
    QLineEdit#appSearch {{border-radius:8px; padding:7px 12px;}}
    QLineEdit#appSearch:focus {{border-color:{p['Accent']};}}
    QTabBar::tab {{border-radius:6px; padding:8px 12px;}}
    QTabBar::tab:selected {{background:{p['Highlight']}; color:{p['Text']}; border-bottom:2px solid {p['Accent']};}}
    QGroupBox {{background:{p['Window']}; border:1px solid {p['Midlight']}; border-radius:12px;}}
    QMenu {{border-radius:12px;}}
    QMenu::item:selected {{background:{p['Highlight']}; color:{p['Text']};}}
    QToolTip {{background:{p['ToolTipBase']}; color:{p['Text']}; border-radius:8px;}}
    QProgressBar::chunk {{background:{p['Accent']};}}
    '''


def waybar_style(p):
    return f'''
    /* BreakPoint: preserve modules, icon identity, placement and user options. */
    * {{font-family:"Inter", "FiraCode Nerd Font", sans-serif;}}
    window#waybar {{background:alpha({p['Window']},0.94); color:{p['Text']}; border-bottom:1px solid {p['Midlight']};}}
    window#waybar.bottom {{border-bottom:none; border-top:1px solid {p['Midlight']};}}
    .modules-left, .modules-center, .modules-right {{padding:3px 5px;}}
    #custom-launcher, #custom-keys, #clock, #audio, #new-workspace,
    #workspaces button, #xetal-pins .pin {{background:alpha({p['AlternateBase']},0.94); color:{p['Text']}; border-radius:5px;}}
    #custom-launcher {{padding:0 12px;}}
    #workspaces button {{border-bottom:2px solid transparent;}}
    #workspaces button.active {{background:{p['Highlight']}; color:{p['Text']}; border-bottom-color:{p['Accent']};}}
    #workspaces button:hover, #custom-launcher:hover, #custom-keys:hover,
    #new-workspace:hover, #xetal-pins .pin:hover {{background:{p['Mid']}; color:{p['Text']};}}
    #workspaces .taskbar-window.active {{background:alpha({p['Accent']},0.12);}}
    #cpu, #memory, #custom-temperature, #disk, #clock, #mpris {{font-family:"JetBrains Mono", "FiraCode Nerd Font", monospace; color:{p['PlaceholderText']};}}
    #bluetooth, #custom-lan, #custom-wifi, #custom-internet, #custom-vpn,
    #pulseaudio, #custom-notifications, #custom-power, #idle_inhibitor,
    #custom-internet.online, #custom-vpn.connected {{color:{p['Text']};}}
    #custom-temperature.critical, #pulseaudio.muted, #custom-power:hover {{color:{p['Accent']};}}
    #workspaces button.urgent {{background:{p['Highlight']}; color:{p['Text']}; border-bottom-color:{p['Accent']};}}
    #workspaces button.workspace-remove {{background:transparent; color:{p['Accent']}; border:none;}}
    #workspaces button.workspace-remove:hover {{background:{p['Highlight']}; color:{p['Text']};}}
    #pulseaudio-slider trough {{background:{p['Midlight']};}}
    #pulseaudio-slider highlight {{background:{p['Accent']};}}
    #pulseaudio-slider slider {{background:{p['Text']};}}
    tooltip, menu {{background:alpha({p['Window']},0.94); color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:12px;}}
    tooltip label {{color:{p['Text']};}}
    menuitem {{color:{p['Text']}; border-radius:6px;}}
    menuitem:hover {{background:{p['Highlight']}; color:{p['Text']};}}
    '''


def notification_style(p):
    return f'''
    * {{font-family:"Inter",sans-serif;}}
    .control-center {{background:alpha({p['Window']},0.94); color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:12px; padding:8px;}}
    .notification {{background:alpha({p['Window']},0.94); color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:12px; margin:8px;}}
    .notification-content {{padding:12px;}}
    .notification-default-action {{border-radius:12px;}}
    .notification-action, .close-button {{background:{p['AlternateBase']}; color:{p['Text']}; border-radius:8px; margin:4px;}}
    .notification-action:hover, .notification-default-action:hover, .close-button:hover {{background:{p['Highlight']};}}
    .summary {{color:{p['Text']}; font-weight:600;}}
    .body, .time {{color:{p['PlaceholderText']};}}
    .widget-title, .widget-dnd {{background:{p['AlternateBase']}; color:{p['Text']}; border-radius:12px; margin:8px; padding:10px;}}
    .widget-title > button {{background:{p['Highlight']}; color:{p['Text']}; border:1px solid {p['Accent']}; border-radius:8px;}}
    '''


def compositor(colors):
    return f'''
# BreakPoint defaults; explicit Window effects remain authoritative.
general:col.active_border = rgb({colors['Accent'][1:]})
general:col.inactive_border = rgb({colors['Midlight'][1:]})
general:border_size = 2
general:gaps_in = 8
general:gaps_out = 8
decoration:rounding = 12
decoration:shadow:enabled = true
decoration:shadow:range = 18
decoration:shadow:render_power = 3
decoration:shadow:color = rgba(00000066)
decoration:blur:enabled = true
decoration:blur:size = 3
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.03
animations {{
    bezier = breakpointEase, 0.2, 0.8, 0.2, 1
    animation = windows, 1, 1.8, breakpointEase
    animation = windowsIn, 1, 1.8, breakpointEase, popin 96%
    animation = windowsOut, 1, 1.5, breakpointEase, popin 96%
    animation = border, 1, 1.5, breakpointEase
    animation = fade, 1, 1.8, breakpointEase
    animation = fadeIn, 1, 1.8, breakpointEase
    animation = fadeOut, 1, 1.5, breakpointEase
    animation = layers, 1, 1.8, breakpointEase
    animation = layersIn, 1, 1.8, breakpointEase, fade
    animation = layersOut, 1, 1.5, breakpointEase, fade
    animation = fadeLayersIn, 1, 1.8, breakpointEase
    animation = fadeLayersOut, 1, 1.5, breakpointEase
    animation = workspaces, 1, 1.8, breakpointEase, slidefade 8%
    animation = workspacesIn, 1, 1.8, breakpointEase, slidefade 8%
    animation = workspacesOut, 1, 1.8, breakpointEase, slidefade 8%
}}
windowrule = match:class ^(xetal-launcher|xetal-switcher|xetal-share-picker|xetal-media|xetal-logout|xetal-image-viewer|xetal-auth|xetal-file-progress|hypr-control|hypr-theme)$, rounding 12
layerrule = match:namespace ^(waybar|swaync-control-center|swaync-notification-window)$, blur on
'''

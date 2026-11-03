"""Tidal Glass: pearl surfaces, refracted aqua light and quiet ocean depth."""


def gradient(p, first='Light', last='Window'):
    return f"qlineargradient(x1:0,y1:0,x2:0.65,y2:1,stop:0 {p[first]},stop:1 {p[last]})"


def rgba(color, alpha):
    return 'rgba('+','.join(str(int(color[i:i+2],16)) for i in (1,3,5))+f',{alpha})'


def qt_style(p):
    from designs import qt_style as base_style
    base = base_style(p).replace('"Noto Sans"', '"Inter"')
    glass = gradient(p)
    button = gradient(p, 'AlternateBase', 'Button')
    selection = gradient(p, 'Highlight', 'Highlight')
    return base + f'''
    /* Tidal Glass: readable pearl interiors with polished aqua edges. */
    QWidget {{background:transparent;}}
    QMainWindow, QDialog, QMessageBox, QWidget#controlRoot {{background:{glass};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QWidget#controlRoot {{background:qlineargradient(x1:0,y1:0,x2:0.7,y2:1,stop:0 {rgba(p['Light'],245)},stop:0.35 {rgba(p['Window'],237)},stop:1 {rgba(p['Button'],235)});}}
    QLabel#brand, QLabel#title, QLabel#dialogTitle {{font-weight:600; letter-spacing:0.3px;}}
    QLabel#eyebrow {{color:{p['Link']}; letter-spacing:2px; font-size:10px;}}
    QLabel#section {{font-size:19px; font-weight:600;}}
    QPushButton, QToolButton {{background:{button}; color:{p['ButtonText']}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:13px; padding:8px 14px;}}
    QPushButton:hover, QToolButton:hover {{background:{gradient(p,'Light','Highlight')}; border:1px solid {p['Accent']};}}
    QPushButton:pressed, QToolButton:pressed {{background:{p['Mid']};}}
    QPushButton:focus, QToolButton:focus {{border:1px solid {p['Accent']};}}
    QPushButton:checked, QPushButton#primary, QPushButton#share, QPushButton#format:checked {{background:{selection}; color:{p['HighlightedText']}; border:1px solid {p['Accent']}; border-radius:13px; font-weight:600;}}
    QPushButton#primary:hover, QPushButton#share:hover {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QPushButton:disabled, QToolButton:disabled {{background:{p['AlternateBase']}; color:{p['Disabled']}; border-color:{p['Midlight']};}}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:13px; padding:9px 12px;}}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{border:1px solid {p['Accent']};}}
    QGroupBox {{background:{gradient(p,'Base','AlternateBase')}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:20px;}}
    QGroupBox::title {{color:{p['Link']}; font-weight:600;}}
    QTabBar::tab {{background:transparent; color:{p['PlaceholderText']}; border:1px solid transparent; border-radius:12px; padding:9px 14px;}}
    QTabBar::tab:selected {{background:{selection}; color:{p['HighlightedText']}; border:1px solid {p['Midlight']};}}
    QTabBar::tab:hover {{background:{p['AlternateBase']}; color:{p['Text']};}}
    QWidget#modernRail {{background:{gradient(p,'Button','AlternateBase')}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:20px;}}
    QToolButton#railButton, QPushButton#railButton, QPushButton#launcherNav {{background:transparent; color:{p['Text']}; border:1px solid transparent; border-radius:12px; text-align:left;}}
    QToolButton#railButton:checked, QPushButton#railButton:checked, QPushButton#launcherNav:checked {{background:{selection}; color:{p['HighlightedText']}; border:1px solid {p['Midlight']}; border-left:3px solid {p['Accent']};}}
    QToolButton#railButton:hover, QPushButton#railButton:hover, QPushButton#launcherNav:hover {{background:{p['Base']}; border-color:{p['Midlight']};}}
    QLineEdit#appSearch {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:20px; padding:11px 18px; font-size:14px;}}
    QFrame#modernCard, QFrame#audioColumn, QFrame#changes, QFrame#presetCard {{background:{glass}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:20px;}}
    QTreeView, QListView, QTableWidget {{background:{p['Base']}; alternate-background-color:{p['AlternateBase']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:14px; outline:none;}}
    QTreeView::item:selected, QListView::item:selected, QTableWidget::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QHeaderView::section {{background:{p['AlternateBase']}; color:{p['Link']}; border:none; padding:9px;}}
    QMenu {{background:{gradient(p,'Base','Window')}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:16px; padding:7px;}}
    QMenu::item {{border-radius:10px; padding:9px 30px;}}
    QMenu::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QToolTip {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Accent']}; border-radius:10px;}}
    QSlider::groove:horizontal {{height:6px; background:{p['Midlight']}; border-radius:3px;}}
    QSlider::sub-page:horizontal {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {p['Link']},stop:1 {p['Accent']}); border-radius:3px;}}
    QSlider::handle:horizontal {{background:{p['Base']}; border:2px solid {p['Accent']}; width:14px; margin:-6px 0; border-radius:9px;}}
    QSlider::handle:vertical {{background:{p['Base']}; border:2px solid {p['Accent']}; border-radius:8px;}}
    QProgressBar {{background:{p['AlternateBase']}; border:1px solid {p['Midlight']}; border-radius:8px;}}
    QProgressBar::chunk {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {p['Link']},stop:1 {p['Accent']}); border-radius:7px;}}
    QCheckBox::indicator, QRadioButton::indicator {{border:1px solid {p['Midlight']}; background:{p['Base']};}}
    QRadioButton::indicator {{width:16px; height:16px; border-radius:8px;}}
    QRadioButton::indicator:checked {{background:{p['Accent']}; border:4px solid {p['Highlight']};}}
    QPushButton#danger, QPushButton#logout {{background:{p['AlternateBase']}; color:{p['Text']}; border-color:{p['Midlight']};}}
    '''


def waybar_style(p):
    return f'''
    /* An edge-lit glass ribbon; preserve every existing taskbar module. */
    * {{font-family:"Inter", "FiraCode Nerd Font", sans-serif;}}
    window#waybar {{background:linear-gradient(150deg,alpha({p['Base']},0.94),alpha({p['Button']},0.86)); color:{p['Text']}; border:1px solid alpha({p['Light']},0.9); border-radius:16px; box-shadow:inset 0 -1px alpha({p['Accent']},0.35);}}
    .modules-left, .modules-center, .modules-right {{padding:3px 6px;}}
    #custom-launcher, #custom-keys, #clock, #audio, #new-workspace, #workspaces button, #xetal-pins .pin {{background:transparent; color:{p['Text']}; border:1px solid transparent; border-radius:13px;}}
    #custom-launcher {{background:alpha({p['Base']},0.8); padding:0 14px; border-color:alpha({p['Light']},0.95);}}
    #workspaces button.active {{background:linear-gradient(140deg,{p['Base']},{p['Highlight']}); color:{p['HighlightedText']}; border-color:alpha({p['Accent']},0.55); box-shadow:0 0 7px alpha({p['Accent']},0.22);}}
    #workspaces button:hover, #custom-launcher:hover, #custom-keys:hover, #new-workspace:hover, #xetal-pins .pin:hover {{background:alpha({p['Light']},0.65); border-color:alpha({p['Accent']},0.55); color:{p['Text']};}}
    #workspaces .taskbar-window.active {{background:alpha({p['Accent']},0.13); border-radius:9px;}}
    #cpu, #memory, #custom-temperature, #disk, #clock, #mpris {{color:{p['PlaceholderText']};}}
    #bluetooth, #custom-lan, #custom-wifi, #custom-internet, #custom-vpn, #pulseaudio, #custom-notifications, #custom-power, #idle_inhibitor {{color:{p['Text']};}}
    #pulseaudio-slider trough {{background:{p['Midlight']}; border-radius:4px;}}
    #pulseaudio-slider highlight {{background:{p['Accent']}; border-radius:4px;}}
    #pulseaudio-slider slider {{background:{p['Base']}; border:1px solid {p['Accent']}; box-shadow:0 0 4px alpha({p['Accent']},0.35);}}
    tooltip, menu {{background:alpha({p['Base']},0.97); color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:15px;}}
    tooltip label, menuitem {{color:{p['Text']};}}
    menuitem {{border-radius:10px;}}
    menuitem:hover {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    '''


def notification_style(p):
    return f'''
    * {{font-family:"Inter",sans-serif;}}
    .control-center, .notification {{background:linear-gradient(140deg,alpha({p['Base']},0.97),alpha({p['Window']},0.94)); color:{p['Text']}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:20px; box-shadow:0 2px 12px alpha({p['Accent']},0.13);}}
    .control-center {{padding:12px;}}
    .notification {{margin:8px;}}
    .notification-content {{padding:14px;}}
    .notification-default-action {{border-radius:20px;}}
    .notification-action, .close-button {{background:{p['Button']}; color:{p['Text']}; border-radius:12px; margin:4px;}}
    .notification-action:hover, .notification-default-action:hover, .close-button:hover {{background:{p['Highlight']};}}
    .summary {{color:{p['Text']}; font-weight:600;}}
    .body, .time {{color:{p['PlaceholderText']};}}
    .widget-title, .widget-dnd {{background:{p['AlternateBase']}; color:{p['Text']}; border-radius:16px; margin:8px; padding:12px;}}
    .widget-title > button {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Midlight']}; border-radius:12px;}}
    '''


def compositor(p):
    return f'''
# Tidal Glass: refracted edges and soft ocean light. User effects still override.
general:col.active_border = rgb({p['Accent'][1:]}) rgb({p['Light'][1:]}) rgb({p['Link'][1:]}) 45deg
general:col.inactive_border = rgba({p['Midlight'][1:]}aa)
general:border_size = 2
general:gaps_in = 7
general:gaps_out = 10
decoration:rounding = 20
decoration:shadow:enabled = true
decoration:shadow:range = 28
decoration:shadow:render_power = 3
decoration:shadow:color = rgba(146c8b38)
decoration:blur:enabled = true
decoration:blur:size = 6
decoration:blur:passes = 3
decoration:blur:vibrancy = 0.12
animations {{
    bezier = tidalEase, 0.16, 0.9, 0.24, 1
    animation = windows, 1, 2.6, tidalEase
    animation = windowsIn, 1, 2.6, tidalEase, popin 94%
    animation = windowsOut, 1, 2, tidalEase, popin 96%
    animation = border, 1, 3, tidalEase
    animation = fade, 1, 2.6, tidalEase
    animation = layers, 1, 2.6, tidalEase
    animation = layersIn, 1, 2.6, tidalEase, fade
    animation = layersOut, 1, 2, tidalEase, fade
    animation = workspaces, 1, 3, tidalEase, slidefade 10%
}}
windowrule = match:class ^(xetal-launcher|xetal-switcher|xetal-share-picker|xetal-media|xetal-logout|xetal-image-viewer|xetal-auth|hypr-control|hypr-theme)$, rounding 20
layerrule = match:namespace ^(waybar|swaync-control-center|swaync-notification-window)$, blur on
'''


def paint_surface(painter, box, colors, radius=20, opacity=94, focused=False):
    """Frosted, slightly translucent glass, with a top glint and an aqua rim."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QLinearGradient, QPainterPath, QPen
    painter.save()
    path=QPainterPath();path.addRoundedRect(box,radius,radius)
    gradient=QLinearGradient(box.topLeft(),box.bottomRight())
    for position,key in ((0,'Light'),(.24,'Window'),(1,'Button')):
        color=QColor(colors[key]);color.setAlphaF(opacity/100);gradient.setColorAt(position,color)
    painter.setBrush(gradient)
    rim=QColor(colors['Accent'] if focused else colors['Midlight']);rim.setAlpha(210 if focused else 180)
    painter.setPen(QPen(rim,1.2));painter.drawPath(path)
    painter.setClipPath(path,Qt.ClipOperation.IntersectClip)
    glint=QLinearGradient(box.topLeft(),box.bottomLeft())
    light=QColor(colors['Light']);light.setAlpha(210);clear=QColor(light);clear.setAlpha(0)
    glint.setColorAt(0,light);glint.setColorAt(.38,clear);glint.setColorAt(1,clear)
    painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(glint,2))
    painter.drawRoundedRect(box.adjusted(1,1,-1,-1),max(0,radius-1),max(0,radius-1))
    painter.restore()

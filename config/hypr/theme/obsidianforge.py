"""Obsidian Forge: machined basalt plates, copper seams and furnace light."""


def basalt(p, upper='Button', lower='Window'):
    return f"qlineargradient(x1:0,y1:0,x2:0.2,y2:1,stop:0 {p[upper]},stop:0.45 {p[lower]},stop:1 {p['Base']})"


def qt_style(p):
    from designs import qt_style as base_style
    return base_style(p).replace('"Noto Sans"', '"Inter"') + f'''
    /* Cold basalt plates. A warm machined edge carries focus. */
    QWidget {{background:transparent;}}
    QMainWindow, QDialog, QMessageBox, QWidget#controlRoot {{background:{basalt(p)};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand, QLabel#title, QLabel#dialogTitle {{font-weight:600; letter-spacing:1px;}}
    QLabel#section {{font-size:19px; font-weight:600; letter-spacing:0.5px;}}
    QLabel#eyebrow {{color:{p['Accent']}; font-size:10px; letter-spacing:3px;}}
    QLabel#status {{background:{p['Base']}; color:{p['Link']}; border:1px solid {p['Midlight']}; border-bottom:2px solid {p['Accent']}; border-radius:3px;}}
    QPushButton, QToolButton {{background:{basalt(p)}; color:{p['ButtonText']}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:3px; padding:8px 13px;}}
    QPushButton:hover, QToolButton:hover {{background:{basalt(p,'Mid','Button')}; border-color:{p['Accent']}; color:{p['Text']};}}
    QPushButton:pressed, QToolButton:pressed {{background:{p['Base']}; border-top-color:{p['Shadow']};}}
    QPushButton:focus, QToolButton:focus {{border:1px solid {p['Accent']};}}
    QPushButton:checked, QToolButton:checked {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']};}}
    QPushButton#primary, QPushButton#share, QPushButton#format:checked {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']}; border-bottom:2px solid {p['Accent']}; border-radius:3px; font-weight:600;}}
    QPushButton#primary:hover, QPushButton#share:hover {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QPushButton:disabled, QToolButton:disabled, QPushButton#share:disabled {{background:{p['AlternateBase']}; color:{p['Disabled']}; border-color:{p['Midlight']};}}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-top-color:{p['Shadow']}; border-radius:3px; padding:8px 11px;}}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{border:1px solid {p['Accent']};}}
    QGroupBox {{background:{basalt(p,'AlternateBase','Window')}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:3px;}}
    QGroupBox::title {{color:{p['PlaceholderText']}; font-weight:600;}}
    QTabBar::tab {{background:{p['Base']}; color:{p['PlaceholderText']}; border:1px solid {p['Midlight']}; border-bottom:2px solid {p['Midlight']}; border-radius:2px; padding:9px 14px; margin:2px 4px 8px 0;}}
    QTabBar::tab:selected {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Midlight']}; border-bottom:2px solid {p['Accent']};}}
    QTabBar::tab:hover {{background:{p['Button']}; color:{p['Text']}; border-top-color:{p['Accent']};}}
    QWidget#modernRail {{background:{basalt(p,'AlternateBase','Base')}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:3px;}}
    QToolButton#railButton, QPushButton#railButton, QPushButton#launcherNav {{background:transparent; color:{p['Text']}; border:1px solid transparent; border-radius:2px; text-align:left;}}
    QToolButton#railButton:checked, QPushButton#railButton:checked, QPushButton#launcherNav:checked {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']};}}
    QToolButton#railButton:hover, QPushButton#railButton:hover, QPushButton#launcherNav:hover {{background:{p['Button']}; border-color:{p['Midlight']};}}
    QLineEdit#appSearch {{background:{p['Base']}; border:1px solid {p['Accent']}; border-radius:3px; padding:10px 14px; font-size:14px;}}
    QFrame#modernCard, QFrame#audioColumn, QFrame#changes, QFrame#presetCard {{background:{basalt(p,'AlternateBase','Window')}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:3px;}}
    QTreeView, QListView, QTableWidget {{background:{p['Base']}; alternate-background-color:{p['AlternateBase']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:2px; outline:none;}}
    QTreeView::item:selected, QListView::item:selected, QTableWidget::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QHeaderView::section, QTableCornerButton::section {{background:{basalt(p)}; color:{p['PlaceholderText']}; border:0px; border-bottom:1px solid {p['Midlight']}; padding:9px;}}
    QMenu {{background:{basalt(p,'AlternateBase','Base')}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-top-color:{p['Accent']}; border-radius:3px; padding:5px;}}
    QMenu::item {{border:1px solid transparent; border-radius:2px; padding:8px 28px;}}
    QMenu::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']}; border-color:{p['Accent']};}}
    QToolTip {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-top-color:{p['Accent']}; border-radius:3px;}}
    QSlider::groove:horizontal {{height:4px; background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:1px;}}
    QSlider::sub-page:horizontal {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {p['Highlight']},stop:1 {p['Accent']}); border-radius:1px;}}
    QSlider::handle:horizontal {{background:{p['Text']}; border:2px solid {p['Accent']}; width:9px; margin:-5px 0; border-radius:2px;}}
    QSlider::groove:vertical, QSlider::sub-page:vertical {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:1px;}}
    QSlider::add-page:vertical {{background:{p['Accent']}; border-radius:1px;}}
    QSlider::handle:vertical {{background:{p['Text']}; border:2px solid {p['Accent']}; border-radius:2px;}}
    QProgressBar {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:2px;}}
    QProgressBar::chunk {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {p['Highlight']},stop:1 {p['Accent']}); border-radius:1px;}}
    QCheckBox::indicator, QAbstractItemView::indicator {{border:1px solid {p['Midlight']}; background:{p['Base']}; border-radius:2px;}}
    QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {{border-radius:2px;}}
    QRadioButton::indicator {{width:16px; height:16px; border:1px solid {p['Midlight']}; border-radius:8px; background:{p['Base']};}}
    QRadioButton::indicator:checked {{background:{p['Accent']}; border:4px solid {p['Base']};}}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{background:{p['Midlight']}; border-radius:1px;}}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{background:{p['Accent']};}}
    '''


def waybar_style(p):
    return f'''
    * {{font-family:"Inter", "FiraCode Nerd Font", sans-serif;}}
    window#waybar {{background:linear-gradient(180deg,{p['Button']},{p['Base']}); color:{p['Text']}; border:0; border-bottom:1px solid {p['Midlight']}; border-radius:0; box-shadow:inset 0 -1px alpha({p['Accent']},0.22);}}
    .modules-left, .modules-center, .modules-right {{padding:2px 5px;}}
    #custom-launcher, #custom-keys, #clock, #audio, #new-workspace, #workspaces button, #xetal-pins .pin {{background:transparent; color:{p['Text']}; border:1px solid transparent; border-radius:2px; box-shadow:none;}}
    #custom-launcher {{background:linear-gradient(180deg,{p['Button']},{p['Base']}); color:{p['Accent']}; border:1px solid {p['Midlight']}; border-bottom-color:{p['Accent']}; padding:0 14px;}}
    #custom-updates {{background:{p['Base']}; color:{p['Link']}; border:1px solid {p['Midlight']}; border-radius:2px;}}
    #workspaces button.active {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']}; box-shadow:inset 0 -2px alpha({p['Accent']},0.3);}}
    #workspaces button:hover, #custom-launcher:hover, #custom-keys:hover, #new-workspace:hover, #xetal-pins .pin:hover {{background:{p['Button']}; color:{p['Text']}; border-color:{p['Accent']};}}
    #workspaces .taskbar-window.active {{background:alpha({p['Accent']},0.14); border-radius:1px;}}
    #cpu, #memory, #custom-temperature, #disk, #mpris {{color:{p['PlaceholderText']};}}
    #bluetooth, #custom-lan, #custom-wifi, #custom-internet, #custom-vpn, #pulseaudio, #custom-notifications, #custom-power, #idle_inhibitor {{color:{p['Text']};}}
    #pulseaudio-slider trough {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:1px;}}
    #pulseaudio-slider highlight {{background:linear-gradient(90deg,{p['Highlight']},{p['Accent']}); border-radius:1px;}}
    #pulseaudio-slider slider {{background:{p['Text']}; border:1px solid {p['Accent']}; border-radius:2px; box-shadow:none;}}
    tooltip, menu {{background:{p['Window']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-top-color:{p['Accent']}; border-radius:3px;}}
    tooltip label, menuitem {{color:{p['Text']};}}
    menuitem {{border-radius:2px;}}
    menuitem:hover {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    '''


def notification_style(p):
    return f'''
    * {{font-family:"Inter",sans-serif;}}
    .control-center, .notification {{background:linear-gradient(155deg,{p['Button']},{p['Base']}); color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:3px; box-shadow:0 4px 20px alpha({p['Shadow']},0.6);}}
    .control-center {{padding:12px; border-top-color:{p['Accent']};}}
    .notification {{margin:8px; border-bottom:2px solid {p['Accent']};}}
    .notification-content {{padding:14px;}}
    .notification-default-action {{border-radius:2px;}}
    .notification-action, .close-button {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:2px; margin:4px;}}
    .notification-action:hover, .notification-default-action:hover, .close-button:hover {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    .summary {{color:{p['Text']}; font-weight:600;}}
    .body, .time {{color:{p['PlaceholderText']};}}
    .widget-title, .widget-dnd {{background:{p['AlternateBase']}; color:{p['Text']}; border-radius:2px; margin:8px; padding:12px;}}
    .widget-title > button {{background:{p['Base']}; color:{p['Link']}; border:1px solid {p['Accent']}; border-radius:2px;}}
    '''


def compositor(p):
    return f'''
# Obsidian Forge: dark plates, copper edges, deliberate fast motion.
general:col.active_border = rgb({p['Accent'][1:]}) rgb({p['Midlight'][1:]}) rgb({p['Accent'][1:]}) 135deg
general:col.inactive_border = rgb({p['Midlight'][1:]})
general:border_size = 1
general:gaps_in = 6
general:gaps_out = 9
decoration:rounding = 3
decoration:shadow:enabled = true
decoration:shadow:range = 30
decoration:shadow:render_power = 3
decoration:shadow:color = rgba({p['Shadow'][1:]}b0)
decoration:blur:enabled = true
decoration:blur:size = 3
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.0
animations {{
    bezier = forgeEase, 0.18, 0.82, 0.22, 1
    animation = windows, 1, 2.8, forgeEase
    animation = windowsIn, 1, 2.8, forgeEase, popin 96%
    animation = windowsOut, 1, 2.2, forgeEase, popin 96%
    animation = border, 1, 3, forgeEase
    animation = fade, 1, 2.5, forgeEase
    animation = layers, 1, 2.8, forgeEase
    animation = layersIn, 1, 2.8, forgeEase, fade
    animation = layersOut, 1, 2.2, forgeEase, fade
    animation = workspaces, 1, 3, forgeEase, slidefade 12%
}}
windowrule = match:class ^(xetal-launcher|xetal-switcher|xetal-share-picker|xetal-media|xetal-logout|xetal-image-viewer|xetal-auth|hypr-control|hypr-theme)$, rounding 3
'''


def paint_surface(painter, box, colors, radius=3, opacity=100, focused=False):
    """Static faceted material: inexpensive, with no idle animation or timers."""
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QLinearGradient, QPainterPath, QPen
    painter.save()
    painter.setOpacity(painter.opacity()*max(0,min(1,opacity/100)))
    shape=QPainterPath();shape.addRoundedRect(box,radius,radius)
    painter.setClipPath(shape,Qt.ClipOperation.IntersectClip)
    fill=QLinearGradient(box.topLeft(),box.bottomRight())
    for position,key in ((0,'Button'),(.42,'Window'),(1,'Base')):fill.setColorAt(position,QColor(colors[key]))
    painter.fillPath(shape,fill)
    # Broad mineral facets stay below content; fine highlights form the bevel.
    facet=QPainterPath(box.topLeft()+QPointF(box.width()*.64,0))
    facet.lineTo(box.topRight());facet.lineTo(box.bottomRight())
    facet.lineTo(box.topLeft()+QPointF(box.width()*.9,box.height()*.38));facet.closeSubpath()
    shade=QColor(colors['Light']);shade.setAlpha(18);painter.fillPath(facet,shade)
    painter.setPen(QPen(QColor(colors['Light']),1))
    painter.drawLine(box.topLeft()+QPointF(radius+1,1),box.topRight()+QPointF(-radius-1,1))
    painter.setPen(QPen(QColor(colors['Shadow']),1))
    painter.drawLine(box.bottomLeft()+QPointF(radius+1,-1),box.bottomRight()+QPointF(-radius-1,-1))
    seam=QLinearGradient(box.bottomLeft(),box.bottomRight())
    for stop,alpha in ((0,0),(.15,80),(.5,245 if focused else 120),(.85,80),(1,0)):
        color=QColor(colors['Accent']);color.setAlpha(alpha);seam.setColorAt(stop,color)
    painter.setPen(QPen(seam,2));painter.drawLine(box.bottomLeft()+QPointF(8,-2),box.bottomRight()+QPointF(-8,-2))
    painter.setPen(QPen(QColor(colors['Accent'] if focused else colors['Midlight']),1))
    painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawPath(shape)
    painter.restore()


def paint_tile(painter, box, colors, opacity=100, selected=False, hovered=False):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor, QPen
    paint_surface(painter,box,colors,3,opacity,selected or hovered)
    if selected or hovered:
        painter.save();painter.setPen(QPen(QColor(colors['Accent']),1.5))
        for corner,dx,dy in ((box.topLeft(),1,1),(box.bottomRight(),-1,-1)):
            corner+=QPointF(dx*4,dy*4)
            painter.drawLine(corner,corner+QPointF(dx*9,0));painter.drawLine(corner,corner+QPointF(0,dy*9))
        painter.restore()

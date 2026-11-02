"""Porcelain Ink: warm paper, charcoal rules and a vermilion seal."""


def paper(p):
    return f"qlineargradient(x1:0,y1:0,x2:0.3,y2:1,stop:0 {p['Light']},stop:1 {p['Window']})"


def qt_style(p):
    from designs import qt_style as base_style
    return base_style(p).replace('"Noto Sans"', '"Inter"') + f'''
    /* Thin ink rules and matte porcelain, with color reserved for focus. */
    QWidget {{background:transparent;}}
    QMainWindow, QDialog, QMessageBox, QWidget#controlRoot {{background:{paper(p)};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand, QLabel#title, QLabel#dialogTitle {{font-family:"Noto Serif"; font-weight:500; letter-spacing:0px;}}
    QLabel#section {{font-family:"Noto Serif"; font-size:19px; font-weight:500;}}
    QLabel#eyebrow {{color:{p['Link']}; font-size:10px; letter-spacing:2px;}}
    QLabel#status {{background:{p['AlternateBase']}; color:{p['Text']}; border-left:2px solid {p['Accent']}; border-radius:0px;}}
    QPushButton, QToolButton {{background:{p['Base']}; color:{p['ButtonText']}; border:1px solid {p['Midlight']}; border-radius:2px; padding:8px 13px;}}
    QPushButton:hover, QToolButton:hover {{background:{p['AlternateBase']}; color:{p['Text']}; border-color:{p['Accent']};}}
    QPushButton:pressed, QToolButton:pressed {{background:{p['Mid']};}}
    QPushButton:focus, QToolButton:focus {{border:1px solid {p['Accent']};}}
    QPushButton:checked, QToolButton:checked {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']};}}
    QPushButton#primary, QPushButton#share, QPushButton#format:checked {{background:{p['Base']}; color:{p['Link']}; border:1px solid {p['Accent']}; border-radius:2px; font-weight:600;}}
    QPushButton#primary:hover, QPushButton#share:hover {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QPushButton:disabled, QToolButton:disabled, QPushButton#share:disabled {{background:{p['AlternateBase']}; color:{p['Disabled']}; border-color:{p['Midlight']};}}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:2px; padding:8px 11px;}}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{border-color:{p['Accent']};}}
    QGroupBox {{background:{p['Window']}; border:1px solid {p['Midlight']}; border-radius:2px;}}
    QGroupBox::title {{color:{p['PlaceholderText']}; font-weight:500;}}
    QTabBar::tab {{background:transparent; color:{p['PlaceholderText']}; border:0px; border-bottom:2px solid transparent; border-radius:0px; padding:9px 14px;}}
    QTabBar::tab:selected {{background:{p['AlternateBase']}; color:{p['Text']}; border:0px; border-bottom:2px solid {p['Accent']};}}
    QTabBar::tab:hover {{background:{p['AlternateBase']}; color:{p['Text']};}}
    QTabWidget#themeCollections > QTabBar::tab {{font-size:14px; padding:10px 22px; margin:0 8px 10px 0;}}
    QWidget#modernRail {{background:{p['AlternateBase']}; border:0px; border-right:1px solid {p['Midlight']}; border-radius:0px;}}
    QToolButton#railButton, QPushButton#railButton, QPushButton#launcherNav {{background:transparent; color:{p['Text']}; border:0px; border-left:2px solid transparent; border-radius:0px; text-align:left;}}
    QToolButton#railButton:checked, QPushButton#railButton:checked, QPushButton#launcherNav:checked {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:0px; border-left:2px solid {p['Accent']};}}
    QToolButton#railButton:hover, QPushButton#railButton:hover, QPushButton#launcherNav:hover {{background:{p['Mid']};}}
    QLineEdit#appSearch {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:2px; padding:10px 14px; font-size:14px;}}
    QFrame#modernCard, QFrame#audioColumn, QFrame#changes, QFrame#presetCard {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:2px;}}
    QTreeView, QListView, QTableWidget {{background:{p['Base']}; alternate-background-color:{p['AlternateBase']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:0px; outline:none;}}
    QTreeView::item:selected, QListView::item:selected, QTableWidget::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QHeaderView::section, QTableCornerButton::section {{background:{p['AlternateBase']}; color:{p['PlaceholderText']}; border:0px; border-bottom:1px solid {p['Midlight']}; padding:9px;}}
    QMenu {{background:{p['Window']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:2px; padding:5px;}}
    QMenu::item {{border-radius:0px; border-left:2px solid transparent; padding:8px 28px;}}
    QMenu::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']}; border-left-color:{p['Accent']};}}
    QToolTip {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:2px;}}
    QSlider::groove:horizontal {{height:4px; background:{p['Midlight']}; border-radius:2px;}}
    QSlider::sub-page:horizontal {{background:{p['Accent']}; border-radius:2px;}}
    QSlider::handle:horizontal {{background:{p['Base']}; border:1px solid {p['Text']}; width:12px; margin:-5px 0; border-radius:7px;}}
    QSlider::groove:vertical, QSlider::sub-page:vertical {{background:{p['Midlight']}; border-radius:2px;}}
    QSlider::add-page:vertical {{background:{p['Accent']}; border-radius:2px;}}
    QSlider::handle:vertical {{background:{p['Base']}; border:1px solid {p['Text']}; border-radius:6px;}}
    QProgressBar {{background:{p['AlternateBase']}; border:1px solid {p['Midlight']}; border-radius:1px;}}
    QProgressBar::chunk {{background:{p['Accent']}; border-radius:0px;}}
    QCheckBox::indicator, QAbstractItemView::indicator {{border:1px solid {p['Midlight']}; background:{p['Base']}; border-radius:2px;}}
    QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {{border-radius:2px;}}
    QRadioButton::indicator {{width:16px; height:16px; border:1px solid {p['Midlight']}; border-radius:8px; background:{p['Base']};}}
    QRadioButton::indicator:checked {{background:{p['Accent']}; border:4px solid {p['Base']};}}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{background:{p['Midlight']}; border-radius:1px;}}
    QPushButton#danger, QPushButton#logout {{background:{p['Base']}; color:{p['Link']}; border-color:{p['Accent']};}}
    '''


def waybar_style(p):
    return f'''
    * {{font-family:"Inter", "FiraCode Nerd Font", sans-serif;}}
    window#waybar {{background:linear-gradient(180deg,{p['Light']},{p['Window']}); color:{p['Text']}; border:0; border-bottom:1px solid {p['Midlight']}; border-radius:0; box-shadow:none;}}
    .modules-left, .modules-center, .modules-right {{padding:2px 6px;}}
    #custom-launcher, #custom-keys, #clock, #audio, #new-workspace, #workspaces button, #xetal-pins .pin {{background:transparent; color:{p['Text']}; border:1px solid transparent; border-radius:1px; box-shadow:none;}}
    #custom-launcher {{padding:0 14px; border-right-color:{p['Midlight']};}}
    #custom-updates {{border-radius:2px;}}
    #workspaces button.active {{background:{p['Highlight']}; color:{p['HighlightedText']}; border-bottom:2px solid {p['Accent']};}}
    #workspaces button:hover, #custom-launcher:hover, #custom-keys:hover, #new-workspace:hover, #xetal-pins .pin:hover {{background:{p['AlternateBase']}; color:{p['Text']}; border-bottom-color:{p['Accent']};}}
    #workspaces .taskbar-window.active {{background:alpha({p['Accent']},0.12); border-radius:1px;}}
    #cpu, #memory, #custom-temperature, #disk, #mpris {{color:{p['PlaceholderText']};}}
    #bluetooth, #custom-lan, #custom-wifi, #custom-internet, #custom-vpn, #pulseaudio, #custom-notifications, #custom-power, #idle_inhibitor {{color:{p['Text']};}}
    #pulseaudio-slider trough {{background:{p['Midlight']}; border-radius:2px;}}
    #pulseaudio-slider highlight {{background:{p['Accent']}; border-radius:2px;}}
    #pulseaudio-slider slider {{background:{p['Base']}; border:1px solid {p['Text']}; box-shadow:none;}}
    tooltip, menu {{background:{p['Window']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:2px;}}
    tooltip label, menuitem {{color:{p['Text']};}}
    menuitem {{border-radius:0;}}
    menuitem:hover {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    '''


def notification_style(p):
    return f'''
    * {{font-family:"Inter",sans-serif;}}
    .control-center, .notification {{background:{p['Window']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:2px; box-shadow:0 3px 12px alpha({p['Shadow']},0.22);}}
    .control-center {{padding:12px;}}
    .notification {{margin:8px; border-left:2px solid {p['Accent']};}}
    .notification-content {{padding:14px;}}
    .notification-default-action {{border-radius:1px;}}
    .notification-action, .close-button {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:2px; margin:4px;}}
    .notification-action:hover, .notification-default-action:hover, .close-button:hover {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    .summary {{color:{p['Text']}; font-weight:600;}}
    .body, .time {{color:{p['PlaceholderText']};}}
    .widget-title, .widget-dnd {{background:{p['AlternateBase']}; color:{p['Text']}; border-radius:1px; margin:8px; padding:12px;}}
    .widget-title > button {{background:{p['Base']}; color:{p['Link']}; border:1px solid {p['Accent']}; border-radius:2px;}}
    '''


def compositor(p):
    return f'''
# Porcelain Ink: fine rules, soft paper shadows and restrained motion.
general:col.active_border = rgb({p['Accent'][1:]})
general:col.inactive_border = rgb({p['Midlight'][1:]})
general:border_size = 1
general:gaps_in = 6
general:gaps_out = 9
decoration:rounding = 2
decoration:shadow:enabled = true
decoration:shadow:range = 22
decoration:shadow:render_power = 3
decoration:shadow:color = rgba({p['Shadow'][1:]}38)
decoration:blur:enabled = true
decoration:blur:size = 3
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.0
animations {{
    bezier = porcelainEase, 0.2, 0.8, 0.25, 1
    animation = windows, 1, 2.3, porcelainEase
    animation = windowsIn, 1, 2.3, porcelainEase, popin 98%
    animation = windowsOut, 1, 1.8, porcelainEase, popin 98%
    animation = border, 1, 2, porcelainEase
    animation = fade, 1, 2.3, porcelainEase
    animation = layers, 1, 2.3, porcelainEase
    animation = layersIn, 1, 2.3, porcelainEase, fade
    animation = layersOut, 1, 1.8, porcelainEase, fade
    animation = workspaces, 1, 2.6, porcelainEase, slidefade 8%
}}
windowrule = match:class ^(xetal-launcher|xetal-switcher|xetal-share-picker|xetal-media|xetal-logout|xetal-image-viewer|xetal-auth|hypr-control|hypr-theme)$, rounding 2
'''


def paint_surface(painter, box, colors, radius=2, opacity=100, focused=False):
    """A matte sheet with a fine ink edge; no translucent glass highlights."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QLinearGradient, QPen
    painter.save()
    fill=QLinearGradient(box.topLeft(),box.bottomLeft())
    for position,key in ((0,'Light'),(1,'Window')):
        color=QColor(colors[key]);color.setAlphaF(max(0,min(1,opacity/100)));fill.setColorAt(position,color)
    painter.setBrush(fill)
    painter.setPen(QPen(QColor(colors['Accent'] if focused else colors['Midlight']),1))
    painter.drawRoundedRect(box,radius,radius)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.restore()


def paint_tile(painter, box, colors, opacity=100, selected=False, hovered=False, focused=False):
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QPen
    painter.save()
    color=QColor(colors['Highlight'] if selected else colors['AlternateBase'] if hovered else colors['Base'])
    color.setAlphaF(max(0,min(1,opacity/100)))
    painter.setBrush(color)
    painter.setPen(QPen(QColor(colors['Accent'] if selected or focused else colors['Midlight']),1) if selected or hovered or focused else Qt.PenStyle.NoPen)
    painter.drawRoundedRect(box,2,2)
    if selected:
        painter.setPen(QPen(QColor(colors['Accent']),2))
        painter.drawLine(QPointF(box.left()+1,box.top()+6),QPointF(box.left()+1,box.bottom()-6))
    painter.restore()

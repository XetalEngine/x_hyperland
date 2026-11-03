"""Candy Cloud: pearlescent pillows, sherbet light and floating cloud gardens."""


def satin(p, first='Button', last='Window'):
    return f"qlineargradient(x1:0,y1:0,x2:0.8,y2:1,stop:0 {p[first]},stop:0.42 {p[last]},stop:1 {p['AlternateBase']})"


def qt_style(p):
    from designs import qt_style as base_style
    return base_style(p).replace('"Noto Sans"', '"Inter"') + f'''
    /* Rounded, sculpted surfaces; the gleam stays behind the content. */
    QWidget {{background:transparent;}}
    QMainWindow, QDialog, QMessageBox, QWidget#controlRoot {{background:{satin(p)};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand, QLabel#title, QLabel#dialogTitle {{font-weight:600; letter-spacing:0.2px;}}
    QLabel#section {{font-size:19px; font-weight:600;}}
    QLabel#eyebrow {{color:{p['Link']}; font-size:10px; letter-spacing:2px;}}
    QLabel#status {{background:{p['Base']}; color:{p['Link']}; border:1px solid {p['Midlight']}; border-radius:16px;}}
    QPushButton, QToolButton {{background:{satin(p,'Light','Button')}; color:{p['ButtonText']}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-bottom:2px solid {p['Dark']}; border-radius:16px; padding:8px 14px;}}
    QPushButton:hover, QToolButton:hover {{background:{satin(p,'Light','AlternateBase')}; color:{p['Text']}; border-color:{p['Accent']};}}
    QPushButton:pressed, QToolButton:pressed {{background:{p['AlternateBase']}; border-bottom:1px solid {p['Midlight']}; border-top:2px solid {p['Dark']};}}
    QPushButton:focus, QToolButton:focus {{border-color:{p['Accent']};}}
    QPushButton:checked, QToolButton:checked, QPushButton#primary, QPushButton#share, QPushButton#format:checked {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']}; border-bottom:2px solid {p['Dark']}; border-radius:16px; font-weight:600;}}
    QPushButton#primary:hover, QPushButton#share:hover {{background:{p['Highlight']}; color:{p['HighlightedText']}; border-color:{p['Link']};}}
    QPushButton:disabled, QToolButton:disabled, QPushButton#share:disabled {{background:{p['AlternateBase']}; color:{p['Disabled']}; border-color:{p['Midlight']};}}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-top-color:{p['Dark']}; border-radius:15px; padding:9px 12px;}}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{border:1px solid {p['Accent']};}}
    QGroupBox {{background:{satin(p,'Button','Window')}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:24px;}}
    QGroupBox::title {{color:{p['Link']}; font-weight:600;}}
    QTabBar::tab {{background:transparent; color:{p['PlaceholderText']}; border:1px solid transparent; border-radius:15px; padding:9px 14px; margin:2px 3px 6px 0;}}
    QTabBar::tab:selected {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Midlight']}; border-top-color:{p['Accent']};}}
    QTabBar::tab:hover {{background:{p['Button']}; color:{p['Text']};}}
    QTabWidget#themeCollections > QTabBar::tab {{font-size:14px; padding:10px 22px; margin:0 8px 12px 0;}}
    QWidget#modernRail {{background:{satin(p,'Button','AlternateBase')}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:26px;}}
    QToolButton#railButton, QPushButton#railButton, QPushButton#launcherNav {{background:transparent; color:{p['Text']}; border:1px solid transparent; border-radius:15px; text-align:left;}}
    QToolButton#railButton:checked, QPushButton#railButton:checked, QPushButton#launcherNav:checked {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Midlight']}; border-top-color:{p['Accent']};}}
    QToolButton#railButton:hover, QPushButton#railButton:hover, QPushButton#launcherNav:hover {{background:{p['Button']}; border-color:{p['Midlight']};}}
    QLineEdit#appSearch {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:20px; padding:11px 18px; font-size:14px;}}
    QFrame#modernCard, QFrame#audioColumn, QFrame#changes, QFrame#presetCard {{background:{satin(p)}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:24px;}}
    QTreeView, QListView, QTableWidget {{background:{p['Base']}; alternate-background-color:{p['AlternateBase']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:16px; outline:none;}}
    QTreeView::item:selected, QListView::item:selected, QTableWidget::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QHeaderView::section, QTableCornerButton::section {{background:{p['Button']}; color:{p['Text']}; border:0; padding:9px;}}
    QMenu {{background:{satin(p,'Button','Base')}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:20px; padding:8px;}}
    QMenu::item {{border-radius:12px; padding:9px 28px;}}
    QMenu::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QToolTip {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:12px;}}
    QSlider::groove:horizontal {{height:8px; background:{p['Midlight']}; border-radius:4px;}}
    QSlider::sub-page:horizontal {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {p['Link']},stop:1 {p['Accent']}); border-radius:4px;}}
    QSlider::handle:horizontal {{background:{satin(p,'Text','Base')}; border:2px solid {p['Accent']}; width:16px; margin:-6px 0; border-radius:10px;}}
    QSlider::groove:vertical {{background:{p['Midlight']}; border-radius:4px;}}
    QSlider::add-page:vertical {{background:{p['Accent']}; border-radius:4px;}}
    QSlider::handle:vertical {{background:{p['Base']}; border:2px solid {p['Accent']}; border-radius:10px;}}
    QProgressBar {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:9px;}}
    QProgressBar::chunk {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {p['Link']},stop:1 {p['Accent']}); border-radius:8px;}}
    QCheckBox::indicator, QAbstractItemView::indicator {{border:1px solid {p['Midlight']}; background:{p['Base']}; border-radius:6px;}}
    QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {{border-radius:6px;}}
    QRadioButton::indicator {{width:16px; height:16px; border:1px solid {p['Midlight']}; border-radius:8px; background:{p['Base']};}}
    QRadioButton::indicator:checked {{background:{p['Accent']}; border:4px solid {p['Base']};}}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{background:{p['Midlight']}; border-radius:4px;}}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{background:{p['Accent']};}}
    '''


def waybar_style(p):
    return f'''
    * {{font-family:"Inter", "FiraCode Nerd Font", sans-serif;}}
    window#waybar {{background:linear-gradient(135deg,alpha({p['Button']},0.97),alpha({p['Window']},0.95)); color:{p['Text']}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:20px; box-shadow:inset 0 -2px alpha({p['Accent']},0.14);}}
    .modules-left, .modules-center, .modules-right {{padding:3px 6px;}}
    #custom-launcher, #custom-keys, #clock, #audio, #new-workspace, #workspaces button, #xetal-pins .pin {{background:transparent; color:{p['Text']}; border:1px solid transparent; border-radius:14px; box-shadow:none;}}
    #custom-launcher {{background:linear-gradient(135deg,{p['Button']},{p['AlternateBase']}); border-color:{p['Light']}; padding:0 14px;}}
    #custom-updates {{background:{p['AlternateBase']}; color:{p['Link']}; border:1px solid {p['Midlight']}; border-radius:13px;}}
    #workspaces button.active {{background:{p['Highlight']}; color:{p['HighlightedText']}; border-color:{p['Accent']}; box-shadow:inset 0 1px alpha({p['Light']},0.55);}}
    #workspaces button:hover, #custom-launcher:hover, #custom-keys:hover, #new-workspace:hover, #xetal-pins .pin:hover {{background:{p['Button']}; color:{p['Text']}; border-color:{p['Accent']};}}
    #workspaces .taskbar-window.active {{background:alpha({p['Accent']},0.2); border-radius:10px;}}
    #cpu, #memory, #custom-temperature, #disk, #mpris {{color:{p['PlaceholderText']};}}
    #bluetooth, #custom-lan, #custom-wifi, #custom-internet, #custom-vpn, #pulseaudio, #custom-notifications, #custom-power, #idle_inhibitor {{color:{p['Text']};}}
    #pulseaudio-slider trough {{background:{p['Midlight']}; border-radius:5px;}}
    #pulseaudio-slider highlight {{background:linear-gradient(90deg,{p['Link']},{p['Accent']}); border-radius:5px;}}
    #pulseaudio-slider slider {{background:{p['Base']}; border:2px solid {p['Accent']}; border-radius:9px; box-shadow:0 1px 3px alpha({p['Shadow']},0.25);}}
    tooltip, menu {{background:{p['Window']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:16px;}}
    tooltip label, menuitem {{color:{p['Text']};}}
    menuitem {{border-radius:12px;}}
    menuitem:hover {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    '''


def notification_style(p):
    return f'''
    * {{font-family:"Inter",sans-serif;}}
    .control-center, .notification {{background:linear-gradient(135deg,{p['Button']},{p['Window']}); color:{p['Text']}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:24px; box-shadow:0 4px 18px alpha({p['Shadow']},0.4);}}
    .control-center {{padding:12px;}}
    .notification {{margin:8px;}}
    .notification-content {{padding:14px;}}
    .notification-default-action {{border-radius:22px;}}
    .notification-action, .close-button {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:14px; margin:4px;}}
    .notification-action:hover, .notification-default-action:hover, .close-button:hover {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    .summary {{color:{p['Text']}; font-weight:600;}}
    .body, .time {{color:{p['PlaceholderText']};}}
    .widget-title, .widget-dnd {{background:{p['AlternateBase']}; color:{p['Text']}; border-radius:18px; margin:8px; padding:12px;}}
    .widget-title > button {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Midlight']}; border-radius:14px;}}
    '''


def compositor(p):
    return f'''
# Candy Cloud: plush edges and a soft landing, timed by the compositor.
general:col.active_border = rgb({p['Accent'][1:]}) rgb({p['Link'][1:]}) rgb({p['Light'][1:]}) 45deg
general:col.inactive_border = rgba({p['Midlight'][1:]}cc)
general:border_size = 2
general:gaps_in = 7
general:gaps_out = 10
decoration:rounding = 26
decoration:shadow:enabled = true
decoration:shadow:range = 32
decoration:shadow:render_power = 3
decoration:shadow:color = rgba({p['Shadow'][1:]}70)
decoration:blur:enabled = true
decoration:blur:size = 5
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.12
animations {{
    bezier = cloudLanding, 0.18, 0.95, 0.26, 1
    animation = windows, 1, 3.2, cloudLanding
    animation = windowsIn, 1, 3.2, cloudLanding, popin 92%
    animation = windowsOut, 1, 2.5, cloudLanding, popin 96%
    animation = border, 1, 3, cloudLanding
    animation = fade, 1, 3, cloudLanding
    animation = layers, 1, 3, cloudLanding
    animation = layersIn, 1, 3, cloudLanding, fade
    animation = layersOut, 1, 2.5, cloudLanding, fade
    animation = workspaces, 1, 3.2, cloudLanding, slidefade 10%
}}
windowrule = match:class ^(xetal-launcher|xetal-switcher|xetal-share-picker|xetal-media|xetal-logout|xetal-image-viewer|xetal-auth|hypr-control|hypr-theme)$, rounding 26
layerrule = match:namespace ^(waybar|swaync-control-center|swaync-notification-window)$, blur on
'''


def faded_layer(painter, box, opacity, paint):
    """Composite the material once so 50% remains 50% beneath its highlights."""
    import math
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QImage, QPainter
    if opacity <= 0:return
    ratio=painter.device().devicePixelRatioF()
    image=QImage(math.ceil(box.width()*ratio),math.ceil(box.height()*ratio),QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(ratio);image.fill(0)
    brush=QPainter(image);brush.setRenderHints(painter.renderHints())
    paint(brush,QRectF(0,0,box.width(),box.height()));brush.end()
    painter.save();painter.setOpacity(painter.opacity()*opacity/100);painter.drawImage(box.topLeft(),image);painter.restore()


def paint_surface(painter, box, colors, radius=26, opacity=100, focused=False):
    """A satin pillow with two soft light pools. Entirely static while idle."""
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QLinearGradient, QPainterPath, QPen, QRadialGradient
    if opacity<100:
        faded_layer(painter,box,opacity,lambda p,b:paint_surface(p,b,colors,radius,100,focused))
        return
    painter.save();painter.setOpacity(painter.opacity()*max(0,min(1,opacity/100)))
    shape=QPainterPath();shape.addRoundedRect(box,radius,radius)
    painter.setClipPath(shape,Qt.ClipOperation.IntersectClip)
    fill=QLinearGradient(box.topLeft(),box.bottomRight())
    for position,key in ((0,'Button'),(.4,'Window'),(1,'AlternateBase')):fill.setColorAt(position,QColor(colors[key]))
    painter.fillPath(shape,fill)
    for center,key,size in ((box.topLeft()+QPointF(box.width()*.13,0),'Link',.7),(box.bottomRight(),'Accent',.6)):
        bloom=QRadialGradient(center,max(1,box.width()*size))
        color=QColor(colors[key]);color.setAlpha(24);bloom.setColorAt(0,color);color.setAlpha(0);bloom.setColorAt(1,color)
        painter.fillPath(shape,bloom)
    edge=QLinearGradient(box.topLeft(),box.bottomLeft())
    for stop,key in ((0,'Light'),(.28,'Midlight'),(1,'Dark')):edge.setColorAt(stop,QColor(colors[key]))
    painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(edge,1.4));painter.drawPath(shape)
    glint=QLinearGradient(box.topLeft(),box.bottomLeft())
    color=QColor(colors['Light']);color.setAlpha(210);glint.setColorAt(0,color);color.setAlpha(0);glint.setColorAt(.35,color);glint.setColorAt(1,color)
    painter.setPen(QPen(glint,2));painter.drawRoundedRect(box.adjusted(2,2,-2,-2),max(0,radius-2),max(0,radius-2))
    if focused:
        rim=QColor(colors['Accent']);rim.setAlpha(190);painter.setPen(QPen(rim,1.2));painter.drawPath(shape)
    painter.restore()


def paint_tile(painter, box, colors, opacity=100, selected=False, hovered=False):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QLinearGradient, QPainterPath, QPen
    if opacity<100:
        faded_layer(painter,box,opacity,lambda p,b:paint_tile(p,b,colors,100,selected,hovered))
        return
    painter.save()
    painter.setOpacity(painter.opacity()*max(0,min(1,opacity/100)))
    painter.setPen(Qt.PenStyle.NoPen);shadow=QColor(colors['Shadow']);shadow.setAlpha(100);painter.setBrush(shadow)
    painter.drawRoundedRect(box.adjusted(1,3,-1,0),24,24)
    face=box.adjusted(0,0,0,-3)
    paint_surface(painter,face,colors,24,100,selected or hovered)
    # A crescent of reflected light gives each icon its own soft pedestal.
    cap=QPainterPath();cap.addRoundedRect(face.adjusted(5,5,-5,-face.height()*.46),19,19)
    gleam=QLinearGradient(face.topLeft(),face.bottomLeft())
    color=QColor(colors['Light']);color.setAlpha(95 if hovered else 55);gleam.setColorAt(0,color);color.setAlpha(0);gleam.setColorAt(.6,color);gleam.setColorAt(1,color)
    painter.fillPath(cap,gleam)
    if selected:
        painter.setPen(QPen(QColor(colors['Accent']),2));painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(face.adjusted(3,3,-3,-3),21,21)
    painter.restore()

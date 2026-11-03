"""Shadow Edge: smoked glass, honed silver and a restrained crimson seam."""


def smoke(p, first='Button', last='Window'):
    return f"qlineargradient(x1:0,y1:0,x2:0.25,y2:1,stop:0 {p[first]},stop:0.16 {p[last]},stop:0.62 {p['Base']},stop:1 {p[last]})"


def qt_style(p):
    from designs import qt_style as base_style
    return base_style(p).replace('"Noto Sans"', '"Inter"') + f'''
    /* Quiet smoked faces, silver machining and a single crimson cutting edge. */
    QWidget {{background:transparent;}}
    QMainWindow, QDialog, QMessageBox, QWidget#controlRoot {{background:{smoke(p)};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand, QLabel#title, QLabel#dialogTitle {{font-weight:600; letter-spacing:1px;}}
    QLabel#section {{font-size:20px; font-weight:500; letter-spacing:0.5px;}}
    QLabel#eyebrow {{color:{p['Link']}; font-size:10px; letter-spacing:3px;}}
    QLabel#status {{background:{p['Base']}; color:{p['PlaceholderText']}; border:1px solid {p['Midlight']}; border-radius:2px;}}
    QPushButton, QToolButton {{background:{smoke(p)}; color:{p['ButtonText']}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:2px; padding:8px 14px;}}
    QPushButton:hover, QToolButton:hover {{background:{smoke(p,'Mid','Button')}; color:{p['Text']}; border-color:{p['Link']};}}
    QPushButton:pressed, QToolButton:pressed {{background:{p['Base']}; border-top-color:{p['Dark']};}}
    QPushButton:focus, QToolButton:focus {{border-color:{p['Accent']};}}
    QPushButton:checked, QToolButton:checked, QPushButton#primary, QPushButton#share, QPushButton#format:checked {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']}; border-top-color:{p['Link']}; border-radius:2px; font-weight:600;}}
    QPushButton#primary:hover, QPushButton#share:hover {{background:{p['Highlight']}; color:{p['HighlightedText']}; border-color:{p['Link']};}}
    QPushButton:disabled, QToolButton:disabled, QPushButton#share:disabled {{background:{p['AlternateBase']}; color:{p['Disabled']}; border-color:{p['Midlight']};}}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-top-color:{p['Dark']}; border-radius:2px; padding:9px 12px;}}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{border-color:{p['Accent']};}}
    QGroupBox {{background:{smoke(p,'AlternateBase','Window')}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:3px;}}
    QGroupBox::title {{color:{p['Link']}; font-weight:500;}}
    QTabBar::tab {{background:{p['Base']}; color:{p['PlaceholderText']}; border:1px solid {p['Midlight']}; border-radius:1px; padding:9px 14px; margin:0 3px 5px 0;}}
    QTabBar::tab:selected {{background:{p['Highlight']}; color:{p['HighlightedText']}; border-top-color:{p['Link']}; border-bottom:2px solid {p['Accent']};}}
    QTabBar::tab:hover {{background:{p['Button']}; color:{p['Text']};}}
    QWidget#modernRail {{background:{smoke(p)}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:2px;}}
    QToolButton#railButton, QPushButton#railButton, QPushButton#launcherNav {{background:transparent; color:{p['Text']}; border:1px solid transparent; border-radius:2px; text-align:left; padding:6px 4px;}}
    QToolButton#railButton:checked, QPushButton#railButton:checked, QPushButton#launcherNav:checked {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']}; border-top-color:{p['Link']};}}
    QToolButton#railButton:hover, QPushButton#railButton:hover, QPushButton#launcherNav:hover {{background:{p['Button']}; border-color:{p['Midlight']};}}
    QLineEdit#appSearch {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-bottom-color:{p['Link']}; border-radius:2px; padding:11px 18px; font-size:14px;}}
    QFrame#modernCard, QFrame#audioColumn, QFrame#changes, QFrame#presetCard {{background:{smoke(p)}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:3px;}}
    QTreeView, QListView, QTableWidget {{background:{p['Base']}; alternate-background-color:{p['AlternateBase']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:2px; outline:none;}}
    QTreeView::item:selected, QListView::item:selected, QTableWidget::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QHeaderView::section, QTableCornerButton::section {{background:{smoke(p)}; color:{p['Link']}; border:0; border-bottom:1px solid {p['Midlight']}; padding:9px;}}
    QMenu {{background:{smoke(p)}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:2px; padding:7px;}}
    QMenu::item {{border-radius:1px; padding:9px 28px;}}
    QMenu::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QToolTip {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Light']}; border-radius:2px;}}
    QSlider::groove:horizontal {{height:5px; background:{p['Midlight']}; border-radius:1px;}}
    QSlider::sub-page:horizontal {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {p['Highlight']},stop:1 {p['Accent']}); border-radius:1px;}}
    QSlider::handle:horizontal {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {p['Text']},stop:0.48 {p['Link']},stop:0.5 {p['Midlight']},stop:1 {p['Light']}); border:1px solid {p['Link']}; width:13px; margin:-5px 0; border-radius:7px;}}
    QSlider::groove:vertical {{background:{p['Midlight']}; border-radius:1px;}}
    QSlider::add-page:vertical {{background:{p['Accent']}; border-radius:1px;}}
    QSlider::handle:vertical {{background:{p['Link']}; border:1px solid {p['Light']}; border-radius:7px;}}
    QProgressBar {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:1px;}}
    QProgressBar::chunk {{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['Link']},stop:0.2 {p['Accent']},stop:1 {p['Highlight']}); border-radius:1px;}}
    QCheckBox::indicator, QAbstractItemView::indicator {{border:1px solid {p['Midlight']}; background:{p['Base']}; border-radius:2px;}}
    QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {{border-radius:2px;}}
    QRadioButton::indicator {{width:16px; height:16px; border:1px solid {p['Midlight']}; border-radius:8px; background:{p['Base']};}}
    QRadioButton::indicator:checked {{background:{p['Accent']}; border:4px solid {p['Base']};}}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{background:{p['Midlight']}; border-radius:1px;}}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{background:{p['Link']};}}
    '''


def waybar_style(p):
    return f'''
    * {{font-family:"Inter", "FiraCode Nerd Font", sans-serif;}}
    window#waybar {{background:linear-gradient(180deg,alpha({p['Button']},0.97),alpha({p['Base']},0.94)); color:{p['Text']}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-bottom-color:{p['Link']}; border-radius:1px;}}
    .modules-left, .modules-center, .modules-right {{padding:1px 4px;}}
    #custom-launcher, #custom-keys, #clock, #audio, #new-workspace, #workspaces button, #xetal-pins .pin {{background:transparent; color:{p['Text']}; border:1px solid transparent; border-radius:1px; box-shadow:none;}}
    #custom-launcher {{background:linear-gradient(135deg,{p['Button']},{p['Base']}); border-color:{p['Midlight']}; border-top-color:{p['Link']}; border-bottom-color:{p['Accent']}; padding:0 14px;}}
    #custom-updates {{background:{p['AlternateBase']}; color:{p['Link']}; border:1px solid {p['Midlight']}; border-radius:1px;}}
    #workspaces button.active {{background:{p['Highlight']}; color:{p['HighlightedText']}; border-top-color:{p['Link']}; border-bottom:2px solid {p['Accent']};}}
    #workspaces button:hover, #custom-launcher:hover, #custom-keys:hover, #new-workspace:hover, #xetal-pins .pin:hover {{background:{p['Button']}; color:{p['Text']}; border-color:{p['Light']};}}
    #workspaces .taskbar-window.active {{background:alpha({p['Accent']},0.18); border-radius:1px;}}
    #cpu, #memory, #custom-temperature, #disk, #mpris {{color:{p['PlaceholderText']};}}
    #bluetooth, #custom-lan, #custom-wifi, #custom-internet, #custom-vpn, #pulseaudio, #custom-notifications, #custom-power, #idle_inhibitor {{color:{p['Link']};}}
    #pulseaudio-slider trough {{background:{p['Midlight']}; border-radius:1px;}}
    #pulseaudio-slider highlight {{background:linear-gradient(90deg,{p['Highlight']},{p['Accent']}); border-radius:1px;}}
    #pulseaudio-slider slider {{background:linear-gradient(135deg,{p['Text']},{p['Light']}); border:1px solid {p['Link']}; border-radius:8px;}}
    tooltip, menu {{background:{p['Window']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-top-color:{p['Light']}; border-radius:2px;}}
    tooltip label, menuitem {{color:{p['Text']};}}
    menuitem {{border-radius:1px;}}
    menuitem:hover {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    '''


def notification_style(p):
    return f'''
    * {{font-family:"Inter",sans-serif;}}
    .control-center, .notification {{background:linear-gradient(155deg,{p['Button']},{p['Base']}); color:{p['Text']}; border:1px solid {p['Midlight']}; border-top-color:{p['Link']}; border-bottom:2px solid {p['Accent']}; border-radius:3px; box-shadow:0 4px 18px alpha({p['Shadow']},0.55);}}
    .control-center {{padding:12px;}}
    .notification {{margin:8px;}}
    .notification-content {{padding:14px;}}
    .notification-default-action {{border-radius:2px;}}
    .notification-action, .close-button {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:2px; margin:4px;}}
    .notification-action:hover, .notification-default-action:hover, .close-button:hover {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    .summary {{color:{p['Text']}; font-weight:600;}}
    .body, .time {{color:{p['PlaceholderText']};}}
    .widget-title, .widget-dnd {{background:{p['AlternateBase']}; color:{p['Text']}; border-radius:2px; margin:8px; padding:12px;}}
    .widget-title > button {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Midlight']}; border-radius:2px;}}
    '''


def compositor(p):
    return f'''
# Shadow Edge: smoked glass and quick, controlled movement.
general:col.active_border = rgb({p['Link'][1:]}) rgb({p['Accent'][1:]}) rgb({p['Midlight'][1:]}) 135deg
general:col.inactive_border = rgba({p['Midlight'][1:]}cc)
general:border_size = 1
general:gaps_in = 6
general:gaps_out = 9
decoration:rounding = 3
decoration:shadow:enabled = true
decoration:shadow:range = 24
decoration:shadow:render_power = 3
decoration:shadow:color = rgba({p['Shadow'][1:]}88)
decoration:blur:enabled = true
decoration:blur:size = 4
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.05
animations {{
    bezier = shadowCut, 0.16, 0.9, 0.25, 1
    animation = windows, 1, 2.7, shadowCut
    animation = windowsIn, 1, 2.7, shadowCut, popin 97%
    animation = windowsOut, 1, 2, shadowCut, popin 99%
    animation = border, 1, 2, shadowCut
    animation = fade, 1, 2.5, shadowCut
    animation = layers, 1, 2.5, shadowCut
    animation = layersIn, 1, 2.5, shadowCut, fade
    animation = layersOut, 1, 2, shadowCut, fade
    animation = workspaces, 1, 3, shadowCut, slidefade 7%
}}
windowrule = match:class ^(xetal-launcher|xetal-switcher|xetal-share-picker|xetal-media|xetal-logout|xetal-image-viewer|xetal-auth|hypr-control|hypr-theme)$, rounding 3
layerrule = match:namespace ^(waybar|swaync-control-center|swaync-notification-window)$, blur on
'''


def cut_path(box, cut=14):
    from PyQt6.QtGui import QPainterPath
    cut = max(0, min(cut, box.width()/4, box.height()/3))
    x,y,r,b=box.left(),box.top(),box.right(),box.bottom()
    path=QPainterPath();path.moveTo(x+cut,y);path.lineTo(r,y);path.lineTo(r,b-cut)
    path.lineTo(r-cut,b);path.lineTo(x,b);path.lineTo(x,y+cut);path.closeSubpath()
    return path


def paint_wallpaper(painter, picture, box):
    """Keep the shinobi's face and moon visible in the wide collection banners."""
    from PyQt6.QtCore import QRectF, Qt
    if picture.isNull():return
    painter.save();painter.setClipRect(box,Qt.ClipOperation.IntersectClip)
    scale=max(box.width()/picture.width(),box.height()/picture.height())
    width,height=picture.width()*scale,picture.height()*scale
    target=QRectF(box.center().x()-width/2,box.top()-(height-box.height())*.08,width,height)
    painter.drawPixmap(target,picture,QRectF(picture.rect()));painter.restore()


def paint_surface(painter, box, colors, radius=14, opacity=100, focused=False):
    """Honed opposing corners; paint once, then composite the whole material."""
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QLinearGradient, QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_surface(p,b,colors,radius,100,focused))
        return
    painter.save()
    cut=max(3,min(16,box.height()*.16));shape=cut_path(box,cut)
    painter.setClipPath(shape,Qt.ClipOperation.IntersectClip)
    fill=QLinearGradient(box.topLeft(),box.bottomLeft())
    for stop,key in ((0,'Button'),(.18,'Window'),(.65,'Base'),(1,'Window')):fill.setColorAt(stop,QColor(colors[key]))
    painter.fillPath(shape,fill)
    edge=QLinearGradient(box.topLeft(),box.bottomRight())
    for stop,key in ((0,'Link'),(.24,'Midlight'),(.7,'Dark'),(1,'Link')):edge.setColorAt(stop,QColor(colors[key]))
    painter.setPen(QPen(edge,1.5));painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawPath(shape)
    painter.setPen(QPen(QColor(colors['Accent']),2 if focused else 1.2))
    painter.drawLine(QPointF(box.right()-cut-7,box.bottom()-2),QPointF(box.right()-2,box.bottom()-cut-7))
    painter.setPen(QPen(QColor(colors['Link']),1))
    painter.drawLine(QPointF(box.left()+2,box.top()+cut+2),QPointF(box.left()+cut+2,box.top()+2))
    painter.restore()


def paint_tile(painter, box, colors, opacity=100, selected=False, hovered=False):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_tile(p,b,colors,100,selected,hovered))
        return
    paint_surface(painter,box,colors,8,100,selected or hovered)
    if selected or hovered:
        painter.save();shape=cut_path(box, min(16,box.height()*.16))
        wash=QColor(colors['Highlight']);wash.setAlpha(100 if selected else 55)
        painter.fillPath(shape,wash);painter.setPen(QPen(QColor(colors['Accent'] if selected else colors['Link']),1))
        painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawPath(shape);painter.restore()

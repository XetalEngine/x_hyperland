"""The Gilded Hollow: moss-dark stone, engraved brass and lantern light."""


def stone(p, first='Button', last='Window'):
    return f"qlineargradient(x1:0,y1:0,x2:0.72,y2:1,stop:0 {p[first]},stop:0.13 {p[last]},stop:0.52 {p['Base']},stop:0.8 {p[last]},stop:1 {p['AlternateBase']})"


def brass(p):
    return f"qlineargradient(x1:0,y1:0,x2:0.3,y2:1,stop:0 {p['Link']},stop:0.28 {p['Accent']},stop:0.53 {p['Midlight']},stop:0.8 {p['Accent']},stop:1 {p['Light']})"


def qt_style(p):
    from designs import qt_style as base
    return base(p)+f'''
    QWidget {{font-family:"Inter";}}
    QMainWindow,QDialog,QMessageBox,QWidget#controlRoot {{background:{stone(p)};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand,QLabel#title,QLabel#dialogTitle {{font-family:"Noto Serif";font-weight:500;letter-spacing:1px;color:{p['Link']};}}
    QLabel#eyebrow {{color:{p['Accent']};letter-spacing:3px;}}
    QLabel#section {{font-family:"Noto Serif";font-size:20px;font-weight:500;color:{p['Link']};}}
    QPushButton,QToolButton {{background:{stone(p)};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-bottom-color:{p['Mid']};border-radius:10px;padding:8px 13px;}}
    QPushButton:hover,QToolButton:hover {{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['Mid']},stop:0.45 {p['Button']},stop:1 {p['Window']});border-color:{p['Accent']};border-top-color:{p['Link']};}}
    QPushButton:checked,QPushButton#primary,QToolButton:checked {{background:qlineargradient(x1:0,y1:0,x2:0.3,y2:1,stop:0 {p['Mid']},stop:0.18 {p['Highlight']},stop:0.78 {p['Button']},stop:1 {p['Highlight']});color:{p['HighlightedText']};border:1px solid {p['Accent']};border-top-color:{p['Link']};}}
    QPushButton:pressed,QToolButton:pressed {{background:{p['Highlight']};border-color:{p['Link']};}}
    QPushButton:disabled,QToolButton:disabled {{background:{p['Window']};color:{p['Disabled']};border-color:{p['Mid']};}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {{background:{p['Base']};border:1px solid {p['Midlight']};border-top-color:{p['Mid']};border-radius:10px;}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QTextEdit:focus,QPlainTextEdit:focus {{border-color:{p['Accent']};}}
    QGroupBox,QFrame#modernCard,QFrame#audioColumn,QFrame#presetCard {{background:{stone(p,'AlternateBase','Window')};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:16px;}}
    QGroupBox::title {{color:{p['Link']};font-weight:500;}}
    QWidget#modernRail {{background:{stone(p)};border:1px solid {p['Midlight']};border-top-color:{p['Accent']};border-radius:16px;}}
    QToolButton#railButton,QPushButton#launcherNav {{background:transparent;border:1px solid transparent;border-radius:10px;}}
    QToolButton#railButton:checked,QPushButton#launcherNav:checked {{background:{p['Highlight']};border-color:{p['Accent']};}}
    QTabBar::tab {{background:{stone(p)};border:1px solid {p['Midlight']};border-radius:9px;padding:9px 15px;}}
    QTabBar::tab:selected {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};border-top-color:{p['Link']};}}
    QTabBar::tab:hover {{border-color:{p['Accent']};}}
    QMenu,QToolTip {{background:{stone(p)};border:1px solid {p['Accent']};border-radius:12px;}}
    QMenu::item {{padding:9px 26px;border-radius:8px;}}
    QMenu::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QMenu::separator {{height:1px;background:{p['Midlight']};margin:6px 12px;}}
    QSlider::groove:horizontal {{height:5px;background:{p['Base']};border:1px solid {p['Midlight']};border-radius:3px;}}
    QSlider::sub-page:horizontal {{background:{brass(p)};border-radius:3px;}}
    QSlider::handle:horizontal {{background:{brass(p)};border:1px solid {p['Link']};width:13px;margin:-5px 0;border-radius:7px;}}
    QProgressBar {{border:1px solid {p['Midlight']};border-radius:6px;background:{p['Base']};}}
    QProgressBar::chunk {{background:{brass(p)};border-radius:5px;}}
    QHeaderView::section {{background:{stone(p)};border-bottom:1px solid {p['Midlight']};color:{p['Link']};}}
    QScrollBar::handle:vertical,QScrollBar::handle:horizontal {{background:{p['Light']};border:1px solid {p['Midlight']};border-radius:3px;}}
    '''


def waybar_style(p):
    return f'''* {{font-family:"Inter","FiraCode Nerd Font",sans-serif;}}
    tooltip,menu {{background:linear-gradient(145deg,{p['Button']},{p['Base']});color:{p['Text']};border:1px solid {p['Accent']};border-radius:12px;}}
    menuitem:hover {{background:{p['Highlight']};}}'''


def notification_style(p):
    return f'''
    .control-center,.notification {{background:linear-gradient(145deg,{p['Button']},{p['Window']} 20%,{p['Base']});color:{p['Text']};border:1px solid {p['Accent']};border-radius:16px;box-shadow:inset 0 1px alpha({p['Link']},0.2);}}
    .notification-content {{padding:14px;}}
    .summary {{font-family:serif;color:{p['Link']};}}
    .body,.time {{color:{p['PlaceholderText']};}}
    .notification-action,.close-button,.widget-title > button {{background:{p['Highlight']};color:{p['HighlightedText']};border:1px solid {p['Midlight']};border-radius:9px;}}
    .notification-action:hover,.close-button:hover {{border-color:{p['Accent']};}}
    '''


def compositor(p):
    return f'''
# Gilded Hollow: a fine brass rim around the cavern glass.
general:col.active_border = rgb({p['Link'][1:]}) rgb({p['Accent'][1:]}) rgb({p['Midlight'][1:]}) 125deg
general:col.inactive_border = rgba({p['Midlight'][1:]}bb)
general:border_size = 1
general:gaps_in = 6
general:gaps_out = 10
decoration:rounding = 16
decoration:shadow:enabled = true
decoration:shadow:range = 28
decoration:shadow:render_power = 3
decoration:shadow:color = rgba({p['Shadow'][1:]}aa)
decoration:blur:enabled = true
decoration:blur:size = 4
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.04
'''


def alpha(value, opacity):
    from PyQt6.QtGui import QColor
    c=QColor(value);c.setAlphaF(max(0,min(1,opacity)));return c


def diamond(p, center, colors, size=5, glow=False):
    from PyQt6.QtCore import QPointF,Qt
    from PyQt6.QtGui import QColor,QPainterPath,QPen,QRadialGradient
    p.save();p.setPen(Qt.PenStyle.NoPen)
    if glow:
        halo=QRadialGradient(center,size*3.5);halo.setColorAt(0,alpha(colors['Accent'],.65));halo.setColorAt(1,alpha(colors['Accent'],0))
        p.setBrush(halo);p.drawEllipse(center,size*3.5,size*3.5)
    gem=QPainterPath(center+QPointF(0,-size))
    for x,y in ((size,0),(0,size),(-size,0)):gem.lineTo(center+QPointF(x,y))
    gem.closeSubpath();p.setBrush(QColor(colors['Accent']));p.setPen(QPen(QColor(colors['Link']),.8));p.drawPath(gem)
    p.setBrush(QColor(colors['Link']));p.drawEllipse(center,size*.22,size*.22);p.restore()


def scrollwork(p, x, y, colors, mirror=False, scale=1):
    """An engraved brass curl, with an inset rivet and a small leaf cut."""
    from PyQt6.QtCore import QPointF,Qt,QRectF
    from PyQt6.QtGui import QColor,QPainterPath,QPen
    p.save();p.translate(x,y);p.scale(-scale if mirror else scale,scale)
    curl=QPainterPath(QPointF(2,29));curl.cubicTo(8,26,19,20,22,9);curl.cubicTo(26,-4,11,-6,10,6);curl.cubicTo(10,14,21,14,19,6)
    p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(alpha(colors['Shadow'],.8),3));p.drawPath(curl)
    p.setPen(QPen(alpha(colors['Accent'],.85),1.1));p.drawPath(curl)
    leaf=QPainterPath(QPointF(8,22));leaf.cubicTo(0,15,2,9,5,7);leaf.cubicTo(13,11,13,18,8,22)
    p.setBrush(alpha(colors['Accent'],.2));p.setPen(QPen(alpha(colors['Link'],.7),.6));p.drawPath(leaf)
    p.setBrush(QColor(colors['Light']));p.setPen(QPen(alpha(colors['Link'],.7),.7));p.drawEllipse(QRectF(3,32,4,4));p.restore()


def paint_surface(painter, box, colors, radius=17, opacity=100, focused=False):
    from PyQt6.QtCore import QPointF,Qt
    from PyQt6.QtGui import QColor,QLinearGradient,QPainterPath,QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_surface(p,b,colors,radius,100,focused));return
    p=painter;p.save();shape=QPainterPath();shape.addRoundedRect(box,radius,radius)
    p.setClipPath(shape,Qt.ClipOperation.IntersectClip)
    fill=QLinearGradient(box.topLeft(),box.bottomRight())
    for stop,key in ((0,'Button'),(.16,'Window'),(.53,'Base'),(.83,'Window'),(1,'AlternateBase')):fill.setColorAt(stop,QColor(colors[key]))
    p.fillPath(shape,fill)
    # Quiet stone veins; deterministic so stationary surfaces never shimmer.
    p.setPen(QPen(alpha(colors['Light'],.055),.7));p.setBrush(Qt.BrushStyle.NoBrush)
    for index in range(9):
        vein=QPainterPath(QPointF(box.left()+index*box.width()/8-40,box.top()))
        vein.cubicTo(box.left()+index*box.width()/8+32,box.top()+box.height()*.32,
                     box.left()+index*box.width()/8-45,box.top()+box.height()*.7,
                     box.left()+index*box.width()/8+70,box.bottom());p.drawPath(vein)
    rim=QLinearGradient(box.topLeft(),box.bottomRight())
    for stop,key in ((0,'Link'),(.22,'Midlight'),(.5,'Accent'),(.78,'Midlight'),(1,'Light')):rim.setColorAt(stop,QColor(colors[key]))
    p.setPen(QPen(rim,1.6 if focused else 1.1));p.drawPath(shape)
    p.setPen(QPen(alpha(colors['Accent'],.25),.7));p.drawRoundedRect(box.adjusted(3,3,-3,-3),max(0,radius-3),max(0,radius-3))
    if box.width()>180 and box.height()>100:
        scrollwork(p,box.left()+7,box.bottom()-31,colors,scale=.65)
        scrollwork(p,box.right()-7,box.bottom()-31,colors,True,.65)
        center=QPointF(box.center().x(),box.bottom()-5)
        p.setPen(QPen(alpha(colors['Accent'],.4),.7));p.drawLine(center-QPointF(45,0),center+QPointF(45,0))
        diamond(p,center,colors,2.5,focused)
    p.restore()


def paint_tile(p,box,colors,opacity=100,selected=False,hovered=False):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QLinearGradient,QPen
    paint_surface(p,box,colors,10,opacity,selected or hovered)
    if selected or hovered:
        p.save();wash=QLinearGradient(box.topLeft(),box.bottomRight())
        wash.setColorAt(0,alpha(colors['Accent'],.18 if selected else .1));wash.setColorAt(1,alpha(colors['Accent'],.025))
        p.setBrush(wash);p.setPen(QPen(alpha(colors['Link'],.9 if selected else .6),1));p.drawRoundedRect(box,10,10);p.restore()

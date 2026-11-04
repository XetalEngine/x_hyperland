"""Hollow Grove: botanical glass, moonlit sage and fine silver branches."""


def glass(p,first='Button',last='Window'):
    return f"qlineargradient(x1:0,y1:0,x2:0.3,y2:1,stop:0 {p[first]},stop:0.15 {p[last]},stop:0.72 {p['Base']},stop:1 {p[last]})"


def qt_style(p):
    from designs import qt_style as base
    return base(p)+f'''
    QWidget {{font-family:"Inter";}}
    QMainWindow, QDialog, QMessageBox, QWidget#controlRoot {{background:{glass(p)};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand, QLabel#title, QLabel#dialogTitle {{font-family:"Noto Serif";font-weight:500;letter-spacing:1px;}}
    QLabel#eyebrow {{color:{p['Link']};letter-spacing:3px;}}
    QLabel#section {{font-family:"Noto Serif";font-size:20px;font-weight:500;}}
    QPushButton,QToolButton {{background:{glass(p)};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:12px;padding:8px 13px;}}
    QPushButton:hover,QToolButton:hover {{background:{p['Button']};border-color:{p['Link']};}}
    QPushButton:checked,QPushButton#primary,QToolButton:checked {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {p['Highlight']},stop:1 {p['Button']});color:{p['Text']};border-color:{p['Accent']};}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {{background:{p['Base']};border:1px solid {p['Midlight']};border-radius:14px;}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus {{border-color:{p['Accent']};}}
    QGroupBox,QFrame#modernCard,QFrame#audioColumn,QFrame#presetCard {{background:{glass(p,'AlternateBase','Window')};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:18px;}}
    QGroupBox::title {{color:{p['Link']};font-weight:500;}}
    QWidget#modernRail {{background:{glass(p)};border:1px solid {p['Midlight']};border-radius:20px;}}
    QToolButton#railButton,QPushButton#launcherNav {{background:transparent;border-color:transparent;border-radius:14px;}}
    QToolButton#railButton:checked,QPushButton#launcherNav:checked {{background:{p['Highlight']};border-color:{p['Accent']};}}
    QTabBar::tab {{background:{p['Window']};border:1px solid {p['Midlight']};border-radius:12px;padding:9px 16px;}}
    QTabBar::tab:selected {{background:{p['Highlight']};color:{p['Text']};border-color:{p['Accent']};}}
    QMenu,QToolTip {{background:{glass(p)};border:1px solid {p['Link']};border-radius:14px;}}
    QMenu::item {{padding:9px 26px;border-radius:10px;}}
    QMenu::item:selected {{background:{p['Highlight']};}}
    QSlider::groove:horizontal {{height:5px;background:{p['Midlight']};border-radius:3px;}}
    QSlider::sub-page:horizontal {{background:{p['Accent']};border-radius:3px;}}
    QSlider::handle:horizontal {{background:{p['Link']};border:1px solid {p['Light']};width:13px;margin:-5px 0;border-radius:7px;}}
    QProgressBar {{border:1px solid {p['Midlight']};border-radius:7px;background:{p['Base']};}}
    QProgressBar::chunk {{background:{p['Accent']};border-radius:6px;}}
    QHeaderView::section {{background:{p['Window']};border-bottom:1px solid {p['Midlight']};color:{p['Link']};}}
    '''


def waybar_style(p):
    return f'* {{font-family:"Inter", "FiraCode Nerd Font",sans-serif;}} tooltip,menu {{background:{p["Window"]};color:{p["Text"]};border:1px solid {p["Link"]};border-radius:14px;}}'


def notification_style(p):
    return f'''
    .control-center,.notification {{background:linear-gradient(155deg,{p['Button']},{p['Base']});color:{p['Text']};border:1px solid {p['Link']};border-radius:19px;}}
    .notification-content {{padding:14px;}}
    .summary {{font-family:serif;color:{p['Text']};}}
    .body,.time {{color:{p['PlaceholderText']};}}
    .notification-action,.close-button,.widget-title > button {{background:{p['Highlight']};color:{p['Text']};border-radius:12px;}}
    '''


def compositor(p):
    return f'''
# Hollow Grove: soft moonlit borders and quiet glass.
general:col.active_border = rgb({p['Link'][1:]}) rgb({p['Accent'][1:]}) 120deg
general:col.inactive_border = rgba({p['Midlight'][1:]}bb)
general:border_size = 1
general:gaps_in = 6
general:gaps_out = 10
decoration:rounding = 18
decoration:shadow:enabled = true
decoration:shadow:range = 24
decoration:shadow:render_power = 3
decoration:shadow:color = rgba({p['Shadow'][1:]}99)
decoration:blur:enabled = true
decoration:blur:size = 4
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.05
'''


def branch(painter,x,y,colors,mirror=False,scale=1):
    from PyQt6.QtCore import QPointF,Qt
    from PyQt6.QtGui import QColor,QPainterPath,QPen
    painter.save();painter.translate(x,y);painter.scale(-scale if mirror else scale,scale)
    stem=QPainterPath(QPointF(0,0));stem.cubicTo(20,-2,34,-12,48,-27)
    painter.setPen(QPen(QColor(colors['Link']),.8));painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawPath(stem)
    for x,y,angle in ((9,-3,-35),(19,-8,30),(29,-14,-35),(40,-22,25)):
        painter.save();painter.translate(x,y);painter.rotate(angle)
        leaf=QPainterPath(QPointF(0,0));leaf.cubicTo(2,-9,11,-8,13,-10);leaf.cubicTo(12,-1,6,2,0,0)
        color=QColor(colors['Accent']);color.setAlpha(135);painter.setBrush(color);painter.drawPath(leaf);painter.restore()
    painter.restore()


def paint_surface(painter,box,colors,radius=19,opacity=100,focused=False):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor,QLinearGradient,QPainterPath,QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_surface(p,b,colors,radius,100,focused));return
    painter.save();path=QPainterPath();path.addRoundedRect(box,radius,radius);painter.setClipPath(path,Qt.ClipOperation.IntersectClip)
    fill=QLinearGradient(box.topLeft(),box.bottomRight())
    for stop,key in ((0,'Button'),(.18,'Window'),(.75,'Base'),(1,'Window')):fill.setColorAt(stop,QColor(colors[key]))
    painter.fillPath(path,fill);painter.setPen(QPen(QColor(colors['Link'] if focused else colors['Midlight']),1));painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawPath(path)
    inner=box.adjusted(2,2,-2,-2);painter.setPen(QPen(QColor(colors['Light']),.5));painter.drawRoundedRect(inner,max(0,radius-2),max(0,radius-2))
    if box.width()>180 and box.height()>100:
        branch(painter,box.left()+7,box.bottom()-3,colors,scale=.4)
        branch(painter,box.right()-7,box.bottom()-3,colors,True,scale=.4)
    painter.restore()


def paint_tile(painter,box,colors,opacity=100,selected=False,hovered=False):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor,QPen
    paint_surface(painter,box,colors,13,opacity,selected or hovered)
    if selected or hovered:
        painter.save();wash=QColor(colors['Highlight']);wash.setAlpha(100 if selected else 45)
        painter.setBrush(wash);painter.setPen(QPen(QColor(colors['Accent']),1));painter.drawRoundedRect(box,13,13);painter.restore()

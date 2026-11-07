"""HyperFusion Blue: polished graphite, silver bevels and sapphire glass."""


def steel(p, first='Button', last='Window'):
    return (f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p[first]},"
            f"stop:0.08 {p['Midlight']},stop:0.12 {p[first]},stop:0.5 {p[last]},"
            f"stop:0.52 {p['Base']},stop:1 {p[last]})")


def blue(p):
    return (f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['Accent']},"
            f"stop:0.48 {p['Highlight']},stop:0.52 {p['Highlight']},stop:1 {p['Highlight']})")


def qt_style(p):
    from designs import qt_style as base
    return base(p)+f'''
    QWidget {{font-family:"Inter";}}
    QMainWindow,QDialog,QMessageBox,QWidget#controlRoot {{background:{steel(p)};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand,QLabel#title,QLabel#dialogTitle {{font-weight:700;letter-spacing:0px;}}
    QLabel#eyebrow {{color:{p['Link']};letter-spacing:2px;}}
    QLabel#section {{font-size:20px;font-weight:600;}}
    QPushButton,QToolButton {{background:{steel(p)};color:{p['ButtonText']};border:1px solid {p['Midlight']};
        border-top-color:{p['Light']};border-bottom-color:{p['Dark']};border-radius:6px;padding:7px 12px;}}
    QPushButton:hover,QToolButton:hover {{border-color:{p['Accent']};background:{steel(p,'Mid','Button')};}}
    QPushButton:pressed,QToolButton:pressed {{background:{p['Highlight']};border-color:{p['Link']};}}
    QPushButton:checked,QPushButton#primary,QToolButton:checked {{background:{blue(p)};color:{p['HighlightedText']};border-color:{p['Link']};}}
    QPushButton:disabled,QToolButton:disabled {{color:{p['Disabled']};background:{p['Window']};border-color:{p['Midlight']};}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {{background:{p['Base']};
        color:{p['Text']};border:1px solid {p['Midlight']};border-bottom-color:{p['Light']};border-radius:5px;padding:6px;}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QTextEdit:focus,QPlainTextEdit:focus {{border-color:{p['Accent']};}}
    QGroupBox,QFrame#modernCard,QFrame#audioColumn,QFrame#presetCard {{background:{steel(p,'AlternateBase','Window')};
        border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:9px;}}
    QGroupBox::title {{color:{p['Text']};font-weight:600;}}
    QWidget#modernRail {{background:{steel(p)};border:1px solid {p['Midlight']};border-radius:8px;}}
    QToolButton#railButton,QPushButton#launcherNav {{background:transparent;border-color:transparent;border-radius:5px;}}
    QToolButton#railButton:checked,QPushButton#launcherNav:checked {{background:{blue(p)};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QTabBar::tab {{background:{steel(p)};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:5px;padding:8px 15px;}}
    QTabBar::tab:selected {{background:{blue(p)};color:{p['HighlightedText']};border-color:{p['Link']};}}
    QMenu,QToolTip {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Light']};border-radius:7px;}}
    QMenu::item {{padding:8px 26px;border-radius:4px;}}
    QMenu::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QSlider::groove:horizontal {{height:6px;background:{p['Base']};border:1px solid {p['Midlight']};border-radius:3px;}}
    QSlider::sub-page:horizontal {{background:{p['Accent']};border-radius:3px;}}
    QSlider::handle:horizontal {{background:{steel(p,'Light','Button')};border:1px solid {p['Light']};width:14px;margin:-5px 0;border-radius:8px;}}
    QProgressBar {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:5px;}}
    QProgressBar::chunk {{background:{blue(p)};border-radius:4px;}}
    QHeaderView::section {{background:{steel(p)};color:{p['Text']};border:0;border-bottom:1px solid {p['Midlight']};padding:6px;}}
    QAbstractItemView::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    '''


def waybar_style(p):
    return f'''* {{font-family:"Inter","FiraCode Nerd Font",sans-serif;}}
    tooltip,menu {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Light']};border-radius:7px;}}
    menuitem:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}'''


def notification_style(p):
    return f'''
    .control-center,.notification {{background:linear-gradient(180deg,{p['Button']},{p['Window']} 18%,{p['Base']});
        color:{p['Text']};border:1px solid {p['Light']};border-radius:10px;}}
    .notification-content {{background:transparent;padding:14px;color:{p['Text']};}}
    .summary,.widget-title {{color:{p['Text']};font-weight:600;}}
    .body,.time {{color:{p['PlaceholderText']};}}
    .notification-action,.close-button,.widget-title > button {{background:linear-gradient(180deg,{p['Button']},{p['Window']});
        color:{p['Text']};border:1px solid {p['Midlight']};border-radius:5px;}}
    .notification-action:hover,.close-button:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    '''


def compositor(p):
    return f'''
# HyperFusion Blue: a silver frame with a sapphire focus edge.
general:col.active_border = rgb({p['Light'][1:]}) rgb({p['Accent'][1:]}) 135deg
general:col.inactive_border = rgba({p['Midlight'][1:]}cc)
general:border_size = 2
general:gaps_in = 5
general:gaps_out = 8
decoration:rounding = 9
decoration:shadow:enabled = true
decoration:shadow:range = 22
decoration:shadow:render_power = 3
decoration:shadow:color = rgba({p['Shadow'][1:]}aa)
decoration:blur:enabled = true
decoration:blur:size = 4
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.04
'''


def paint_surface(painter,box,colors,radius=9,opacity=100,focused=False):
    from PyQt6.QtCore import Qt,QPointF
    from PyQt6.QtGui import QColor,QLinearGradient,QPainterPath,QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_surface(p,b,colors,radius,100,focused));return
    painter.save();path=QPainterPath();path.addRoundedRect(box,radius,radius)
    painter.setClipPath(path,Qt.ClipOperation.IntersectClip)
    fill=QLinearGradient(box.topLeft(),box.bottomLeft())
    for stop,key in ((0,'Button'),(.16,'Window'),(.52,'Base'),(1,'Window')):fill.setColorAt(stop,QColor(colors[key]))
    painter.fillPath(path,fill)
    # Hairline grain stays subtle; highlights outline the material, not the text.
    grain=QColor(colors['Light']);grain.setAlpha(8);painter.setPen(QPen(grain,.5))
    for y in range(int(box.top())+4,int(box.bottom()),4):
        painter.drawLine(QPointF(box.left()+2,y),QPointF(box.right()-2,y))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(colors['Accent'] if focused else colors['Midlight']),1));painter.drawPath(path)
    painter.setPen(QPen(QColor(colors['Light']),.7));painter.drawRoundedRect(box.adjusted(1.5,1.5,-1.5,-1.5),max(0,radius-1),max(0,radius-1))
    if focused:
        painter.setPen(QPen(QColor(colors['Accent']),2));painter.drawLine(QPointF(box.left()+radius,box.bottom()-2),QPointF(box.right()-radius,box.bottom()-2))
    painter.restore()


def paint_tile(painter,box,colors,opacity=100,selected=False,hovered=False):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor,QLinearGradient,QPen
    paint_surface(painter,box,colors,7,opacity,selected or hovered)
    if selected or hovered:
        painter.save();wash=QLinearGradient(box.topLeft(),box.bottomLeft())
        top=QColor(colors['Accent']);top.setAlpha(110 if selected else 38)
        bottom=QColor(colors['Highlight']);bottom.setAlpha(160 if selected else 55)
        wash.setColorAt(0,top);wash.setColorAt(1,bottom)
        painter.setBrush(wash);painter.setPen(QPen(QColor(colors['Accent']),1));painter.drawRoundedRect(box,7,7);painter.restore()

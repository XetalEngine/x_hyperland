"""Blackwood: walnut joinery, aged brass, sage enamel and quiet coastal light."""
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / 'assets'


def wood(p):
    return (f"qlineargradient(x1:0,y1:0,x2:.08,y2:1,stop:0 {p['Button']},"
            f"stop:.22 {p['Window']},stop:.8 {p['Base']},stop:1 {p['Window']})")


def sage(p):
    return (f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['Highlight']},"
            f"stop:1 {p['Highlight']})")


def qt_style(p):
    from designs import qt_style as base
    return base(p)+f'''
    QWidget {{font-family:"Noto Serif";}}
    QMainWindow,QDialog,QMessageBox,QWidget#controlRoot {{background:{wood(p)};color:{p['Text']};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand,QLabel#title,QLabel#dialogTitle {{font-family:"Noto Serif";font-weight:600;}}
    QLabel#section {{font-family:"Noto Serif";font-size:20px;font-weight:600;}}
    QLabel#eyebrow {{color:{p['Link']};letter-spacing:3px;}}
    QPushButton,QToolButton {{background:{wood(p)};color:{p['ButtonText']};border:1px solid {p['Midlight']};
        border-top-color:{p['Light']};border-bottom-color:{p['Dark']};border-radius:4px;padding:6px 12px;}}
    QPushButton:hover,QToolButton:hover {{border-color:{p['Light']};background:{p['Button']};}}
    QPushButton:focus,QToolButton:focus {{border:1px solid {p['Accent']};}}
    QPushButton:pressed,QToolButton:pressed {{background:{p['Base']};border-color:{p['Accent']};}}
    QPushButton:checked,QPushButton#primary,QToolButton:checked {{background:{sage(p)};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QPushButton#primary:hover {{background:{p['Highlight']};border-color:{p['Light']};}}
    QPushButton:disabled,QToolButton:disabled {{color:{p['Disabled']};background:{p['Window']};border-color:{p['Mid']};}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {{background:{p['Base']};color:{p['Text']};
        border:1px solid {p['Midlight']};border-bottom-color:{p['Light']};border-radius:3px;padding:6px;}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QTextEdit:focus,QPlainTextEdit:focus {{border-color:{p['Accent']};}}
    QGroupBox,QFrame#modernCard,QFrame#audioColumn,QFrame#presetCard {{background:{wood(p)};
        border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:5px;}}
    QGroupBox::title {{color:{p['Text']};font-weight:600;}}
    QWidget#modernRail {{background:{wood(p)};border:1px solid {p['Midlight']};border-radius:5px;}}
    QToolButton#railButton,QPushButton#launcherNav {{background:transparent;border-color:transparent;border-radius:3px;}}
    QToolButton#railButton:checked,QPushButton#launcherNav:checked {{background:{sage(p)};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QTabBar::tab {{background:{wood(p)};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:3px;padding:7px 14px;}}
    QTabBar::tab:selected {{background:{sage(p)};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QMenu,QToolTip {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Light']};border-radius:4px;}}
    QMenu::item {{padding:7px 26px;border-radius:3px;}}
    QMenu::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QMenu::separator {{background:{p['Midlight']};height:1px;margin:5px 10px;}}
    QSlider::groove:horizontal {{height:4px;background:{p['Base']};border:1px solid {p['Midlight']};border-radius:3px;}}
    QSlider::sub-page:horizontal {{background:{p['Accent']};border-radius:3px;}}
    QSlider::handle:horizontal {{background:{p['Highlight']};border:1px solid {p['Light']};width:15px;margin:-6px 0;border-radius:8px;}}
    QProgressBar {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:3px;}}
    QProgressBar::chunk {{background:{p['Accent']};border-radius:2px;}}
    QHeaderView::section {{background:{wood(p)};color:{p['Text']};border:0;border-right:1px solid {p['Mid']};border-bottom:1px solid {p['Light']};padding:6px;}}
    QAbstractItemView {{selection-background-color:{p['Highlight']};selection-color:{p['HighlightedText']};}}
    QAbstractItemView::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    '''


def files_style(p):
    return f'''QMainWindow,QWidget#filesBody,QWidget#hyperControlPanel,QToolBar,QFrame#addressRow {{background:{wood(p)};}}
    QToolBar {{background-image:url("{ASSETS/'blackwood-grain.svg'}");border-bottom:1px solid {p['Light']};}}
    QGroupBox#drivePartitionCard,QFrame#defaultsHero,QFrame#ramMetric,QFrame#ramMode,QFrame#filterGroupBox {{background:{wood(p)};
        border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:5px;}}
    QTreeWidget#places {{background:{p['Window']};border-right:1px solid {p['Midlight']};}}
    QTreeWidget#places::item:selected,QTabBar::tab:selected {{background:{sage(p)};color:{p['HighlightedText']};border:1px solid {p['Accent']};border-radius:3px;}}
    QFrame#pickerActions,QStatusBar {{background:{p['Window']};border-top:1px solid {p['Light']};}}
    QToolButton#windowClose {{background:{wood(p)};color:{p['Text']};border:1px solid {p['Midlight']};}}
    QToolButton#windowClose:hover {{background:#743e2c;color:#fff4db;border-color:#d3b27e;}}'''


def waybar_style(p):
    return f'''* {{font-family:"Noto Serif","FiraCode Nerd Font",serif;}}
    tooltip,menu {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Light']};border-radius:4px;}}
    menuitem:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}'''


def bar_controls(p,root):
    return f'''window#waybar {{border-color:{p['Light']};}}
    #custom-launcher {{background-image:url("{root/'assets/blackwood-mark.svg'}"),linear-gradient(180deg,{p['Button']},{p['Base']});
        background-repeat:no-repeat;background-position:8px center;border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:4px;
        padding:0 13px 0 39px;color:{p['Text']};font-weight:600;}}
    #workspaces button {{background:linear-gradient(180deg,{p['Button']},{p['Base']});color:{p['Text']};
        border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:4px;padding:0 7px;margin:3px 3px;}}
    #workspaces button.active {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};
        box-shadow:inset 0 1px alpha({p['Light']},0.5);}}
    #custom-keys,#new-workspace,#xetal-pins .pin {{border:1px solid {p['Midlight']};border-radius:3px;background:{p['Window']};}}
    #clock {{background:transparent;border-left:1px solid {p['Midlight']};border-radius:0;padding:0 12px;}}
    #audio {{border-right:1px solid {p['Midlight']};border-radius:0;}}
    #custom-updates {{color:{p['Accent']};}}
    '''


def notification_style(p):
    return f'''
    .control-center,.notification {{background:linear-gradient(175deg,{p['Button']},{p['Window']} 18%,{p['Base']});
        color:{p['Text']};border:1px solid {p['Light']};border-radius:6px;}}
    .notification-content {{background:transparent;padding:14px;color:{p['Text']};}}
    .summary,.widget-title {{color:{p['Text']};font-family:"Noto Serif",serif;font-weight:600;}}
    .body,.time,.widget-label {{color:{p['PlaceholderText']};}}
    .notification-action,.close-button,.widget-title > button,.widget-buttons-grid > flowbox > flowboxchild > button {{background:{p['Button']};color:{p['Text']};
        border:1px solid {p['Midlight']};border-radius:3px;}}
    .notification-action:hover,.close-button:hover,.widget-title > button:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    .widget-mpris {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:5px;}}
    .widget-dnd > switch:checked {{background:{p['Highlight']};border:1px solid {p['Accent']};}}
    scale trough {{background:{p['Base']};border:1px solid {p['Midlight']};}}
    scale highlight {{background:{p['Accent']};}}
    '''


def compositor(p):
    return f'''
# Blackwood: aged brass framing, calm sage focus, compact walnut joinery.
general:col.active_border = rgb({p['Light'][1:]}) rgb({p['Accent'][1:]}) 120deg
general:col.inactive_border = rgba({p['Midlight'][1:]}bb)
general:border_size = 2
general:gaps_in = 5
general:gaps_out = 8
decoration:rounding = 5
decoration:shadow:enabled = true
decoration:shadow:range = 22
decoration:shadow:render_power = 3
decoration:shadow:color = rgba({p['Shadow'][1:]}bb)
decoration:blur:enabled = true
decoration:blur:size = 3
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.01
'''


def paint_surface(painter,box,colors,radius=5,opacity=100,focused=False):
    from math import sin
    from PyQt6.QtCore import Qt,QPointF,QRectF
    from PyQt6.QtGui import QColor,QLinearGradient,QPainterPath,QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_surface(p,b,colors,radius,100,focused));return
    painter.save();path=QPainterPath();path.addRoundedRect(box,radius,radius)
    painter.setClipPath(path,Qt.ClipOperation.IntersectClip)
    fill=QLinearGradient(box.topLeft(),box.bottomRight())
    for stop,key in ((0,'Button'),(.18,'Window'),(.85,'Base'),(1,'Window')):fill.setColorAt(stop,QColor(colors[key]))
    painter.fillPath(path,fill)
    # Walnut grain belongs to the narrow header, leaving text/content calm.
    header=QRectF(box.left(),box.top(),box.width(),min(30,box.height()*.28))
    grain=QColor(colors['Light']);grain.setAlpha(22)
    painter.setPen(QPen(grain,.65))
    for row in range(2,int(header.height()),3):
        curve=QPainterPath();curve.moveTo(box.left(),box.top()+row)
        for col in range(0,int(box.width())+14,14):
            curve.lineTo(box.left()+col,box.top()+row+sin(col*.036+row)*1.1+sin(col*.009)*.8)
        painter.drawPath(curve)
    painter.setPen(QPen(QColor(colors['Midlight']),.75))
    painter.drawLine(header.bottomLeft(),header.bottomRight())
    painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(QColor(colors['Light']),1))
    painter.drawPath(path)
    painter.setPen(QPen(QColor(colors['Midlight']),.6));painter.drawRoundedRect(box.adjusted(2,2,-2,-2),max(0,radius-1),max(0,radius-1))
    # Tiny brass pins at the corners, like a cabinet escutcheon.
    if box.width()>80 and box.height()>55:
        for x in (box.left()+7,box.right()-7):
            for y in (box.top()+7,box.bottom()-7):
                painter.setBrush(QColor(colors['Light']));painter.setPen(Qt.PenStyle.NoPen);painter.drawEllipse(QPointF(x,y),1.2,1.2)
    if focused:
        painter.setPen(QPen(QColor(colors['Accent']),1.5));painter.drawLine(QPointF(box.left()+14,box.bottom()-4),QPointF(box.right()-14,box.bottom()-4))
    painter.restore()


def paint_tile(painter,box,colors,opacity=100,selected=False,hovered=False):
    from PyQt6.QtGui import QColor,QPen
    paint_surface(painter,box,colors,4,opacity,selected or hovered)
    if selected or hovered:
        painter.save();wash=QColor(colors['Accent']);wash.setAlpha(55 if selected else 20)
        painter.setBrush(wash);painter.setPen(QPen(QColor(colors['Accent']),1))
        painter.drawRoundedRect(box.adjusted(2,2,-2,-2),3,3);painter.restore()

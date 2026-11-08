"""Mycelium: plum velvet, ivory root veins and softly lit lilac caps."""
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / 'assets'


def velvet(p):
    return (f"qlineargradient(x1:0,y1:0,x2:.18,y2:1,stop:0 {p['Button']},"
            f"stop:.25 {p['Window']},stop:1 {p['Base']})")


def lilac(p):
    return f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['Accent']},stop:1 {p['Highlight']})"


def qt_style(p):
    from designs import qt_style as base
    return base(p)+f'''
    QWidget {{font-family:"Noto Serif";}}
    QMainWindow,QDialog,QMessageBox,QWidget#controlRoot {{background:{velvet(p)};color:{p['Text']};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand,QLabel#title,QLabel#dialogTitle {{font-weight:600;}}
    QLabel#section {{font-size:20px;font-weight:600;}}
    QLabel#eyebrow {{color:{p['Link']};letter-spacing:2px;}}
    QPushButton,QToolButton {{background:{velvet(p)};color:{p['ButtonText']};border:1px solid {p['Midlight']};
        border-top-color:{p['Light']};border-radius:8px;padding:6px 12px;}}
    QPushButton:hover,QToolButton:hover {{background:{p['Button']};border-color:{p['Accent']};}}
    QPushButton:focus,QToolButton:focus {{border:1px solid {p['Accent']};}}
    QPushButton:pressed,QToolButton:pressed {{background:{p['Base']};border-color:{p['Accent']};}}
    QPushButton:checked,QPushButton#primary,QToolButton:checked {{background:{lilac(p)};
        color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QPushButton#primary:hover {{background:{p['Accent']};color:{p['HighlightedText']};border-color:{p['Light']};}}
    QPushButton:disabled,QToolButton:disabled {{color:{p['Disabled']};background:{p['Window']};border-color:{p['Mid']};}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {{background:{p['Base']};color:{p['Text']};
        border:1px solid {p['Midlight']};border-radius:7px;padding:6px;}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QTextEdit:focus,QPlainTextEdit:focus {{border-color:{p['Accent']};}}
    QComboBox QAbstractItemView {{background:{p['Window']};color:{p['Text']};selection-background-color:{p['Highlight']};selection-color:{p['HighlightedText']};}}
    QGroupBox,QFrame#modernCard,QFrame#audioColumn,QFrame#presetCard {{background:{velvet(p)};
        border:1px solid {p['Midlight']};border-radius:12px;}}
    QGroupBox::title {{color:{p['Text']};font-weight:600;}}
    QWidget#modernRail {{background:{velvet(p)};border:1px solid {p['Midlight']};border-radius:12px;}}
    QToolButton#railButton,QPushButton#launcherNav {{background:transparent;border-color:transparent;border-radius:7px;}}
    QToolButton#railButton:checked,QPushButton#launcherNav:checked {{background:{lilac(p)};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QTabBar::tab {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:7px;padding:7px 14px;}}
    QTabBar::tab:selected {{background:{lilac(p)};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QMenu,QToolTip {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Light']};border-radius:9px;}}
    QMenu::item {{padding:7px 26px;border-radius:6px;}}
    QMenu::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QMenu::item:disabled {{color:{p['Disabled']};}}
    QMenu::separator {{background:{p['Midlight']};height:1px;margin:5px 10px;}}
    QSlider::groove:horizontal {{height:4px;background:{p['Base']};border:1px solid {p['Midlight']};border-radius:3px;}}
    QSlider::sub-page:horizontal {{background:{p['Accent']};border-radius:3px;}}
    QSlider::handle:horizontal {{background:{p['Accent']};border:1px solid {p['Light']};width:15px;margin:-6px 0;border-radius:8px;}}
    QProgressBar {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:5px;}}
    QProgressBar::chunk {{background:{lilac(p)};border-radius:4px;}}
    QHeaderView::section {{background:{velvet(p)};color:{p['Text']};border:0;border-right:1px solid {p['Mid']};border-bottom:1px solid {p['Midlight']};padding:6px;}}
    QAbstractItemView {{selection-background-color:{p['Highlight']};selection-color:{p['HighlightedText']};}}
    QAbstractItemView::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QCheckBox::indicator:checked,QRadioButton::indicator:checked {{background:{p['Highlight']};border-color:{p['Accent']};}}
    '''


def files_style(p):
    return f'''QMainWindow,QWidget#filesBody,QWidget#hyperControlPanel,QToolBar,QFrame#addressRow {{background:{velvet(p)};}}
    QToolBar {{background-image:url("{ASSETS/'mycelium-roots.svg'}");background-repeat:no-repeat;background-position:top right;border-bottom:1px solid {p['Midlight']};}}
    QGroupBox#drivePartitionCard,QFrame#defaultsHero,QFrame#ramMetric,QFrame#ramMode,QFrame#filterGroupBox {{background:{velvet(p)};
        border:1px solid {p['Midlight']};border-radius:12px;}}
    QTreeWidget#places {{background:{p['Window']};border-right:1px solid {p['Midlight']};}}
    QTreeWidget#places::item:selected,QTabBar::tab:selected {{background:{lilac(p)};color:{p['HighlightedText']};border:1px solid {p['Accent']};border-radius:6px;}}
    QFrame#pickerActions,QStatusBar {{background:{p['Window']};border-top:1px solid {p['Midlight']};}}
    QToolButton#windowClose {{color:{p['Text']};}}
    QToolButton#windowClose:hover {{color:{p['HighlightedText']};}}'''


def waybar_style(p):
    return f'''* {{font-family:"Noto Serif","FiraCode Nerd Font",serif;}}
    tooltip,menu {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Light']};border-radius:9px;}}
    menuitem:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}'''


def bar_controls(p,root):
    return f'''window#waybar {{border-color:{p['Midlight']};}}
    #custom-launcher {{background-image:url("{root/'assets/mycelium-mark.svg'}"),linear-gradient(180deg,{p['Button']},{p['Window']});
        background-repeat:no-repeat;background-position:8px center;border:1px solid {p['Midlight']};border-radius:14px;
        padding:0 14px 0 40px;color:{p['Text']};}}
    #custom-launcher:hover {{border-color:{p['Accent']};}}
    #workspaces button {{background:linear-gradient(180deg,{p['Button']},{p['Base']});color:{p['Text']};
        border:1px solid {p['Midlight']};border-radius:6px;padding:0 7px;margin:3px;}}
    #workspaces button.active {{background:linear-gradient(180deg,{p['Accent']},{p['Highlight']});color:{p['HighlightedText']};
        border-color:{p['Accent']};box-shadow:inset 0 1px alpha({p['Light']},0.5);}}
    #custom-keys,#new-workspace,#xetal-pins .pin {{border:1px solid {p['Midlight']};border-radius:8px;background:{p['Window']};}}
    #xetal-pins .pin.active {{border-color:{p['Accent']};background:{p['Button']};}}
    #clock {{background:transparent;border-left:1px solid {p['Midlight']};border-radius:0;padding:0 12px;}}
    #audio {{border-right:1px solid {p['Midlight']};border-radius:0;}}
    #custom-updates {{color:{p['Accent']};}}
    #xetal-bar-options-controller {{background-image:url("{root/'assets/mycelium-roots.svg'}");background-position:right center;}}
    '''


def notification_style(p):
    return f'''.control-center,.notification {{background:linear-gradient(165deg,{p['Button']},{p['Window']} 22%,{p['Base']});
        color:{p['Text']};border:1px solid {p['Midlight']};border-radius:14px;}}
    .notification-content {{background:transparent;padding:14px;color:{p['Text']};}}
    .summary,.widget-title {{color:{p['Text']};font-family:"Noto Serif",serif;font-weight:600;}}
    .body,.time,.widget-label {{color:{p['PlaceholderText']};}}
    .notification-action,.close-button,.widget-title > button,.widget-buttons-grid > flowbox > flowboxchild > button {{background:{p['Button']};
        color:{p['Text']};border:1px solid {p['Midlight']};border-radius:7px;}}
    .notification-action:hover,.close-button:hover,.widget-title > button:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    .widget-mpris {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:10px;}}
    .widget-dnd > switch:checked {{background:{p['Highlight']};border:1px solid {p['Accent']};}}
    scale trough {{background:{p['Base']};border:1px solid {p['Midlight']};}}
    scale highlight {{background:{p['Accent']};}}'''


def compositor(p):
    return f'''\n# Mycelium: soft plum silhouettes and lilac focus.
general:col.active_border = rgb({p['Accent'][1:]}) rgb({p['Midlight'][1:]}) 135deg
general:col.inactive_border = rgba({p['Midlight'][1:]}aa)
general:border_size = 2
decoration:rounding = 14
'''


def roots(painter,box,color,opacity=.5):
    """Fine branching veins occupy only the corners, leaving content clear."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor,QPainterPath,QPen
    painter.save();ink=QColor(color);ink.setAlphaF(opacity)
    painter.setPen(QPen(ink,.8));painter.setBrush(Qt.BrushStyle.NoBrush)
    reach=min(112.,box.width()*.28);height=min(11.,box.height()*.12)
    for x,y,sx,sy in ((box.right()-7,box.top()+3,-1,1),(box.left()+7,box.bottom()-3,1,-1)):
        painter.save();painter.translate(x,y);painter.scale(sx,sy)
        for branch in (0,1):
            line=QPainterPath();line.moveTo(0,0)
            line.cubicTo(reach*.22,height*.9,reach*.28,-height*.2,reach*.52,height*.45)
            line.cubicTo(reach*.72,height*(.8-branch*.4),reach*.78,-height*.1,reach,height*(.2+branch*.4))
            painter.drawPath(line)
            for fraction in (.28,.63):
                root=QPainterPath();root.moveTo(reach*fraction,height*.35)
                root.cubicTo(reach*(fraction+.04),height*.25,reach*(fraction+.07),height*(.9-branch*.4),reach*(fraction+.17),height*(.9-branch*.6))
                painter.drawPath(root)
        painter.restore()
    painter.restore()


def mushroom(painter,x,y,scale,cap,ivory):
    """A compact sculpted cap, luminous gills and a curved ivory stem."""
    from PyQt6.QtCore import QPointF,QRectF,Qt
    from PyQt6.QtGui import QColor,QLinearGradient,QPainterPath,QPen
    painter.save();painter.translate(x,y);painter.scale(scale,scale)
    stem=QPainterPath();stem.moveTo(-2,0);stem.cubicTo(-1,7,-3,13,-5,17);stem.quadTo(2,20,5,17);stem.cubicTo(2,10,3,4,3,0)
    painter.setBrush(QColor(ivory));painter.setPen(QPen(QColor(cap).darker(150),.7));painter.drawPath(stem)
    shape=QPainterPath();shape.moveTo(-17,1);shape.cubicTo(-13,-8,-8,-11,0,-11);shape.cubicTo(9,-11,13,-7,17,1);shape.quadTo(0,7,-17,1)
    fill=QLinearGradient(0,-11,0,5);fill.setColorAt(0,QColor(cap).lighter(130));fill.setColorAt(.65,QColor(cap));fill.setColorAt(1,QColor(cap).darker(155))
    painter.setBrush(fill);painter.setPen(QPen(QColor(ivory),.8));painter.drawPath(shape)
    painter.setBrush(QColor(ivory));painter.setPen(Qt.PenStyle.NoPen);painter.drawEllipse(QRectF(-14,0,28,4))
    painter.setPen(QPen(QColor(cap).darker(125),.55))
    for i in range(-12,13,4):painter.drawLine(QPointF(i,1),QPointF(i*.35,4))
    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(ivory))
    for px,py,r in ((-5,-6,1.2),(4,-7,1.5),(10,-2,.8),(-10,-2,.8)):painter.drawEllipse(QPointF(px,py),r,r*.6)
    painter.restore()


def paint_surface(painter,box,colors,radius=14,opacity=100,focused=False):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor,QLinearGradient,QPainterPath,QPen
    painter.save();painter.setOpacity(painter.opacity()*opacity/100)
    path=QPainterPath();path.addRoundedRect(box,radius,radius)
    fill=QLinearGradient(box.topLeft(),box.bottomRight())
    for stop,key in ((0,'Button'),(.18,'Window'),(.75,'Base'),(1,'Window')):fill.setColorAt(stop,QColor(colors[key]))
    painter.fillPath(path,fill);painter.setClipPath(path)
    if box.width()>150 and box.height()>55:
        roots(painter,box,colors['Light'],.32)
    painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(QColor(colors['Accent'] if focused else colors['Midlight']),1.2))
    painter.drawPath(path)
    if box.height()>70:
        inner=QColor(colors['Light']);inner.setAlpha(48);painter.setPen(QPen(inner,.6))
        painter.drawRoundedRect(box.adjusted(3,3,-3,-3),max(2,radius-2),max(2,radius-2))
    painter.restore()


def paint_tile(painter,box,colors,opacity=100,selected=False,hovered=False):
    from PyQt6.QtGui import QColor,QPen
    paint_surface(painter,box,colors,11,opacity,selected or hovered)
    if selected or hovered:
        painter.save();wash=QColor(colors['Accent']);wash.setAlpha(45 if selected else 18)
        painter.setBrush(wash);painter.setPen(QPen(QColor(colors['Accent']),1))
        painter.drawRoundedRect(box.adjusted(2,2,-2,-2),9,9);painter.restore()

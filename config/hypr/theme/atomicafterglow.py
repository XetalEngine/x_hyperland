"""Atomic Afterglow: olive graphite, brass fasteners and phosphor instruments."""
from pathlib import Path

ASSETS=Path(__file__).resolve().parent/'assets'


def metal(p):
    return (f"qlineargradient(x1:0,y1:0,x2:.12,y2:1,stop:0 {p['Button']},"
            f"stop:.18 {p['Window']},stop:.82 {p['Base']},stop:1 {p['Window']})")


def phosphor(p):
    return f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['Accent']},stop:1 {p['Highlight']})"


def qt_style(p):
    from designs import qt_style as base
    return base(p)+f'''
    QWidget {{font-family:"Inter";}}
    QMainWindow,QDialog,QMessageBox,QWidget#controlRoot {{background:{metal(p)};color:{p['Text']};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand,QLabel#title,QLabel#dialogTitle {{font-weight:600;letter-spacing:.3px;}}
    QLabel#eyebrow {{color:{p['Accent']};letter-spacing:2px;}}
    QPushButton,QToolButton {{background:{metal(p)};color:{p['ButtonText']};border:1px solid {p['Midlight']};
        border-top-color:{p['Light']};border-radius:4px;padding:6px 12px;}}
    QPushButton:hover,QToolButton:hover {{background:{p['Button']};border-color:{p['Accent']};}}
    QPushButton:focus,QToolButton:focus {{border:1px solid {p['Accent']};}}
    QPushButton:pressed,QToolButton:pressed {{background:{p['Base']};border-color:{p['Accent']};}}
    QPushButton:checked,QPushButton#primary,QToolButton:checked {{background:{phosphor(p)};
        color:{p['HighlightedText']};border-color:{p['Accent']};font-weight:600;}}
    QPushButton#primary:hover {{background:{p['Accent']};color:{p['HighlightedText']};border-color:{p['Light']};}}
    QPushButton:disabled,QToolButton:disabled {{color:{p['Disabled']};background:{p['Window']};border-color:{p['Mid']};}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {{background:{p['Base']};color:{p['Text']};
        border:1px solid {p['Midlight']};border-bottom-color:{p['Light']};border-radius:3px;padding:6px;}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QTextEdit:focus,QPlainTextEdit:focus {{border-color:{p['Accent']};}}
    QGroupBox,QFrame#modernCard,QFrame#audioColumn,QFrame#presetCard {{background:{metal(p)};
        border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:5px;}}
    QGroupBox::title {{color:{p['Text']};font-weight:600;}}
    QWidget#modernRail {{background:{metal(p)};border:1px solid {p['Midlight']};border-radius:5px;}}
    QToolButton#railButton,QPushButton#launcherNav {{background:transparent;border-color:transparent;border-radius:3px;}}
    QToolButton#railButton:checked,QPushButton#launcherNav:checked {{background:{phosphor(p)};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QTabBar::tab {{background:{metal(p)};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:3px;padding:7px 14px;}}
    QTabBar::tab:selected {{background:{phosphor(p)};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QMenu,QToolTip {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Light']};border-radius:4px;}}
    QMenu::item {{padding:7px 26px;border-radius:3px;}}
    QMenu::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QMenu::separator {{background:{p['Midlight']};height:1px;margin:5px 10px;}}
    QSlider::groove:horizontal {{height:4px;background:{p['Base']};border:1px solid {p['Midlight']};border-radius:3px;}}
    QSlider::sub-page:horizontal {{background:{p['Accent']};border-radius:3px;}}
    QSlider::handle:horizontal {{background:{p['Accent']};border:1px solid {p['Light']};width:14px;margin:-6px 0;border-radius:7px;}}
    QProgressBar {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:3px;}}
    QProgressBar::chunk {{background:{phosphor(p)};border-radius:2px;}}
    QHeaderView::section {{background:{metal(p)};color:{p['Text']};border:0;border-right:1px solid {p['Mid']};border-bottom:1px solid {p['Light']};padding:6px;}}
    QAbstractItemView {{selection-background-color:{p['Highlight']};selection-color:{p['HighlightedText']};}}
    QAbstractItemView::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    '''


def files_style(p):
    return f'''QMainWindow,QWidget#filesBody,QWidget#hyperControlPanel,QToolBar,QFrame#addressRow {{background:{metal(p)};}}
    QToolBar {{border-bottom:1px solid {p['Light']};}}
    QGroupBox#drivePartitionCard,QFrame#defaultsHero,QFrame#ramMetric,QFrame#ramMode,QFrame#filterGroupBox {{background:{metal(p)};
        border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:5px;}}
    QTreeWidget#places {{background:{p['Window']};border-right:1px solid {p['Midlight']};}}
    QTreeWidget#places::item:selected,QTabBar::tab:selected {{background:{phosphor(p)};color:{p['HighlightedText']};border:1px solid {p['Accent']};border-radius:3px;}}
    QFrame#pickerActions,QStatusBar {{background:{p['Window']};border-top:1px solid {p['Light']};}}
    /* Native header controls keep their own transparent background. Match
       that surface; their local stylesheet owns the highlight on hover. */
    QToolButton#windowClose {{color:{p['Text']};}}
    QToolButton#windowClose:hover {{color:{p['HighlightedText']};}}'''


def waybar_style(p):
    return f'''* {{font-family:"Inter","FiraCode Nerd Font",sans-serif;}}
    tooltip,menu {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Light']};border-radius:4px;}}
    menuitem:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}'''


def bar_controls(p,root):
    return f'''window#waybar {{border-color:{p['Light']};}}
    #custom-launcher {{background-image:url("{root/'assets/atomicafterglow-mark.svg'}"),linear-gradient(180deg,{p['Button']},{p['Base']});
        background-repeat:no-repeat;background-position:8px center;border:1px solid {p['Midlight']};border-top-color:{p['Light']};
        border-radius:4px;padding:0 13px 0 39px;color:{p['Text']};font-weight:600;}}
    #workspaces button {{background:linear-gradient(180deg,{p['Button']},{p['Base']});color:{p['Text']};
        border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:3px;padding:0 7px;margin:3px;}}
    #workspaces button.active {{background:linear-gradient(180deg,{p['Accent']},{p['Highlight']});color:{p['HighlightedText']};
        border-color:{p['Accent']};box-shadow:inset 0 1px alpha({p['Light']},0.5);}}
    #custom-keys,#new-workspace,#xetal-pins .pin {{border:1px solid {p['Midlight']};border-radius:3px;background:{p['Window']};}}
    #xetal-pins .pin.active {{border-bottom:2px solid {p['Accent']};}}
    #clock {{background:transparent;border-left:1px solid {p['Midlight']};border-radius:0;padding:0 12px;}}
    #audio {{border-right:1px solid {p['Midlight']};border-radius:0;}}
    #custom-updates {{color:{p['Accent']};}}
    #xetal-bar-options-controller {{background-image:url("{root/'assets/atomicafterglow-hazard.svg'}");
        background-repeat:no-repeat;background-position:center;min-width:9px;}}
    '''


def notification_style(p):
    return f'''.control-center,.notification {{background:linear-gradient(175deg,{p['Button']},{p['Window']} 18%,{p['Base']});
        color:{p['Text']};border:1px solid {p['Light']};border-radius:5px;}}
    .notification-content {{background:transparent;padding:14px;color:{p['Text']};}}
    .summary,.widget-title {{color:{p['Text']};font-family:"Inter",sans-serif;font-weight:600;}}
    .body,.time,.widget-label {{color:{p['PlaceholderText']};}}
    .notification-action,.close-button,.widget-title > button,.widget-buttons-grid > flowbox > flowboxchild > button {{background:{p['Button']};
        color:{p['Text']};border:1px solid {p['Midlight']};border-radius:3px;}}
    .notification-action:hover,.close-button:hover,.widget-title > button:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    .widget-mpris {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:4px;}}
    .widget-dnd > switch:checked {{background:{p['Highlight']};border:1px solid {p['Accent']};}}
    scale trough {{background:{p['Base']};border:1px solid {p['Midlight']};}}
    scale highlight {{background:{p['Accent']};}}'''


def compositor(p):
    return f'''\n# Atomic Afterglow: graphite casing and phosphor focus.
general:col.active_border = rgb({p['Accent'][1:]}) rgb({p['Light'][1:]}) 135deg
general:col.inactive_border = rgba({p['Midlight'][1:]}bb)
general:border_size = 2
decoration:rounding = 5
'''


def paint_surface(painter,box,colors,radius=5,opacity=100,focused=False):
    from PyQt6.QtCore import QPointF,Qt
    from PyQt6.QtGui import QColor,QLinearGradient,QPainterPath,QPen
    painter.save();painter.setOpacity(painter.opacity()*opacity/100)
    x,y,r,b=box.left(),box.top(),box.right(),box.bottom();cut=min(7,box.height()/5)
    path=QPainterPath();path.moveTo(x+cut,y);path.lineTo(r-cut,y);path.lineTo(r,y+cut)
    path.lineTo(r,b-cut);path.lineTo(r-cut,b);path.lineTo(x+cut,b);path.lineTo(x,b-cut);path.lineTo(x,y+cut);path.closeSubpath()
    fill=QLinearGradient(box.topLeft(),box.bottomLeft())
    for stop,key in ((0,'Button'),(.14,'Window'),(.8,'Base'),(1,'Window')):fill.setColorAt(stop,QColor(colors[key]))
    painter.fillPath(path,fill);painter.setClipPath(path)
    # Fine brushed-metal lines stay on the border, outside the content area.
    grain=QColor(colors['Light']);grain.setAlpha(17);painter.setPen(QPen(grain,.6))
    for row in range(3,17,3):painter.drawLine(QPointF(x+8,y+row),QPointF(r-8,y+row))
    painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(QColor(colors['Light']),1));painter.drawPath(path)
    painter.setPen(QPen(QColor(colors['Midlight']),.6));painter.drawRoundedRect(box.adjusted(3,3,-3,-3),3,3)
    if box.width()>80 and box.height()>55:
        for sx in (x+7,r-7):
            for sy in (y+7,b-7):
                painter.setPen(QPen(QColor(colors['Light']),.8));painter.setBrush(QColor(colors['Base']));painter.drawEllipse(QPointF(sx,sy),1.8,1.8)
                painter.drawLine(QPointF(sx-1,sy+1),QPointF(sx+1,sy-1))
    painter.setPen(QPen(QColor(colors['Accent']),1.7 if focused else .7))
    painter.drawLine(QPointF(x+15,b-4),QPointF(r-15,b-4))
    painter.restore()


def paint_tile(painter,box,colors,opacity=100,selected=False,hovered=False):
    from PyQt6.QtGui import QColor,QPen
    paint_surface(painter,box,colors,5,opacity,selected or hovered)
    if selected or hovered:
        painter.save();wash=QColor(colors['Accent']);wash.setAlpha(55 if selected else 20)
        painter.setBrush(wash);painter.setPen(QPen(QColor(colors['Accent']),1))
        painter.drawRoundedRect(box.adjusted(3,3,-3,-3),3,3);painter.restore()

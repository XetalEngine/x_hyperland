"""Midnight Transit: deep teal enamel, ivory pinstripes and amber signals."""


def enamel(p, first='Button', last='Window'):
    return (f"qlineargradient(x1:0,y1:0,x2:0.25,y2:1,stop:0 {p[first]},"
            f"stop:0.16 {p[last]},stop:0.74 {p['Base']},stop:1 {p[last]})")


def amber(p):
    return (f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['Accent']},"
            f"stop:0.25 {p['Highlight']},stop:1 {p['Highlight']})")


def qt_style(p):
    from designs import qt_style as base
    return base(p)+f'''
    QWidget {{font-family:"Inter";}}
    QMainWindow,QDialog,QMessageBox,QWidget#controlRoot {{background:{enamel(p)};color:{p['Text']};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand,QLabel#title,QLabel#dialogTitle {{font-weight:600;letter-spacing:1px;}}
    QLabel#eyebrow {{color:{p['Link']};letter-spacing:3px;}}
    QLabel#section {{font-size:20px;font-weight:600;}}
    QPushButton,QToolButton {{background:{enamel(p)};color:{p['ButtonText']};border:1px solid {p['Midlight']};
        border-top-color:{p['Light']};border-radius:5px;padding:7px 12px;}}
    QPushButton:hover,QToolButton:hover {{border-color:{p['Accent']};background:{enamel(p,'Mid','Button')};}}
    QPushButton:pressed,QToolButton:pressed {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QPushButton:checked,QPushButton#primary,QToolButton:checked {{background:{amber(p)};color:{p['HighlightedText']};border-color:{p['Light']};}}
    QPushButton:disabled,QToolButton:disabled {{color:{p['Disabled']};background:{p['Window']};border-color:{p['Midlight']};}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {{background:{p['Base']};color:{p['Text']};
        border:1px solid {p['Midlight']};border-bottom-color:{p['Light']};border-radius:4px;padding:6px;}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QTextEdit:focus,QPlainTextEdit:focus {{border-color:{p['Accent']};}}
    QGroupBox,QFrame#modernCard,QFrame#audioColumn,QFrame#presetCard {{background:{enamel(p,'AlternateBase')};
        border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:7px;}}
    QGroupBox::title {{color:{p['Text']};font-weight:600;}}
    QWidget#modernRail {{background:{enamel(p)};border:1px solid {p['Light']};border-radius:7px;}}
    QToolButton#railButton,QPushButton#launcherNav {{background:transparent;border-color:transparent;border-radius:4px;}}
    QToolButton#railButton:checked,QPushButton#launcherNav:checked {{background:{amber(p)};color:{p['HighlightedText']};border-color:{p['Light']};}}
    QTabBar::tab {{background:{enamel(p)};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:4px;padding:8px 15px;}}
    QTabBar::tab:selected {{background:{amber(p)};color:{p['HighlightedText']};border-color:{p['Light']};}}
    QMenu,QToolTip {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Light']};border-radius:5px;}}
    QMenu::item {{padding:8px 26px;border-radius:3px;}}
    QMenu::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QSlider::groove:horizontal {{height:5px;background:{p['Base']};border:1px solid {p['Midlight']};border-radius:3px;}}
    QSlider::sub-page:horizontal {{background:{p['Accent']};border-radius:3px;}}
    QSlider::handle:horizontal {{background:{p['Light']};border:2px solid {p['Accent']};width:12px;margin:-5px 0;border-radius:8px;}}
    QProgressBar {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:4px;}}
    QProgressBar::chunk {{background:{amber(p)};border-radius:3px;}}
    QHeaderView::section {{background:{enamel(p)};color:{p['Text']};border:0;border-bottom:1px solid {p['Light']};padding:6px;}}
    QAbstractItemView {{selection-background-color:{p['Highlight']};selection-color:{p['HighlightedText']};}}
    QAbstractItemView::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    '''


def files_style(p):
    return f'''QMainWindow,QWidget#filesBody,QWidget#hyperControlPanel,QToolBar,QFrame#addressRow {{background:{enamel(p)};}}
    QGroupBox#drivePartitionCard,QFrame#defaultsHero,QFrame#ramMetric,QFrame#ramMode,QFrame#filterGroupBox {{background:{enamel(p)};
        border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:7px;}}
    QTreeWidget#places {{background:{p['Window']};border-right:1px solid {p['Light']};}}
    QTreeWidget#places::item:selected,QTabBar::tab:selected {{background:{amber(p)};color:{p['HighlightedText']};border:1px solid {p['Light']};border-radius:4px;}}
    QFrame#pickerActions,QStatusBar {{background:{p['Window']};border-top:1px solid {p['Light']};}}
    QToolButton#windowClose {{background:{amber(p)};color:{p['HighlightedText']};border:1px solid {p['Light']};}}
    QToolButton#windowClose:hover {{background:#a54922;color:#fff6e7;}}'''


def waybar_style(p):
    return f'''* {{font-family:"Inter","FiraCode Nerd Font",sans-serif;}}
    tooltip,menu {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Light']};border-radius:5px;}}
    menuitem:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}'''


def bar_controls(p,root):
    return f'''window#waybar {{border-color:{p['Light']};}}
    #custom-launcher {{background-image:url("{root/'assets/midnight-transit-mark.svg'}"),linear-gradient(160deg,{p['Button']},{p['Base']});
        background-repeat:no-repeat;background-position:7px center;border:1px solid {p['Light']};border-radius:15px;
        padding:0 13px 0 38px;color:{p['Text']};font-weight:600;}}
    #workspaces button {{background:linear-gradient(160deg,{p['Button']},{p['Base']});color:{p['Text']};
        border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:4px;padding:0 7px;margin:3px 2px;}}
    #workspaces button.active {{background:linear-gradient(180deg,{p['Accent']},{p['Highlight']});color:{p['HighlightedText']};
        border-color:{p['Light']};box-shadow:inset 0 1px alpha({p['Light']},0.65),0 0 4px alpha({p['Accent']},0.25);}}
    #custom-keys,#new-workspace,#xetal-pins .pin {{border:1px solid {p['Midlight']};border-radius:4px;background:{p['Window']};}}
    #clock {{background:transparent;border-left:1px solid {p['Midlight']};border-radius:0;padding:0 12px;}}
    #audio {{border-right:1px solid {p['Midlight']};border-radius:0;}}'''


def notification_style(p):
    return f'''
    .control-center,.notification {{background:linear-gradient(160deg,{p['Button']},{p['Window']} 22%,{p['Base']});
        color:{p['Text']};border:1px solid {p['Light']};border-radius:8px;}}
    .notification-content {{background:transparent;padding:14px;color:{p['Text']};}}
    .summary,.widget-title {{color:{p['Text']};font-weight:600;}}
    .body,.time {{color:{p['PlaceholderText']};}}
    .notification-action,.close-button,.widget-title > button {{background:{p['Button']};color:{p['Text']};
        border:1px solid {p['Midlight']};border-radius:4px;}}
    .notification-action:hover,.close-button:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    '''


def compositor(p):
    return f'''
# Midnight Transit: cream pinstripes around teal enamel.
general:col.active_border = rgb({p['Light'][1:]}) rgb({p['Accent'][1:]}) 135deg
general:col.inactive_border = rgba({p['Midlight'][1:]}cc)
general:border_size = 2
general:gaps_in = 5
general:gaps_out = 8
decoration:rounding = 7
decoration:shadow:enabled = true
decoration:shadow:range = 22
decoration:shadow:render_power = 3
decoration:shadow:color = rgba({p['Shadow'][1:]}bb)
decoration:blur:enabled = true
decoration:blur:size = 4
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.03
'''


def paint_surface(painter, box, colors, radius=7, opacity=100, focused=False):
    from PyQt6.QtCore import Qt,QPointF
    from PyQt6.QtGui import QColor,QLinearGradient,QPainterPath,QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_surface(p,b,colors,radius,100,focused));return
    painter.save();path=QPainterPath();path.addRoundedRect(box,radius,radius)
    painter.setClipPath(path,Qt.ClipOperation.IntersectClip)
    fill=QLinearGradient(box.topLeft(),box.bottomRight())
    for stop,key in ((0,'Button'),(.2,'Window'),(.75,'Base'),(1,'Window')):fill.setColorAt(stop,QColor(colors[key]))
    painter.fillPath(path,fill);painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(colors['Light']),1.2));painter.drawPath(path)
    painter.setPen(QPen(QColor(colors['Midlight']),.6))
    painter.drawRoundedRect(box.adjusted(3,3,-3,-3),max(0,radius-2),max(0,radius-2))
    if focused:
        painter.setPen(QPen(QColor(colors['Accent']),2))
        painter.drawLine(QPointF(box.left()+radius+5,box.bottom()-4),QPointF(box.right()-radius-5,box.bottom()-4))
    painter.restore()


def paint_tile(painter,box,colors,opacity=100,selected=False,hovered=False):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor,QPen
    paint_surface(painter,box,colors,6,opacity,selected or hovered)
    if selected or hovered:
        painter.save();wash=QColor(colors['Accent']);wash.setAlpha(55 if selected else 22)
        painter.setBrush(wash);painter.setPen(QPen(QColor(colors['Accent']),1))
        painter.drawRoundedRect(box.adjusted(2,2,-2,-2),4,4);painter.restore()

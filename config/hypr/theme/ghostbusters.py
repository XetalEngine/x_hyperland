"""Ghostbusters: luminous ectoplasm, ink-black enamel and playful slime edges."""


def enamel(p):
    return f"qlineargradient(x1:0,y1:0,x2:.25,y2:1,stop:0 {p['Button']},stop:.30 {p['Window']},stop:.90 {p['Base']},stop:1 {p['Window']})"


def chrome_style(p):
    return f'''QToolButton {{background:transparent;color:{p['Text']};border:1px solid transparent;border-radius:10px;padding:0;}}
    QToolButton:hover {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QToolButton:pressed {{background:{p['Mid']};}}
    QToolButton:focus {{border-color:{p['Accent']};}}
    QToolButton:disabled {{color:{p['Disabled']};}}
    QToolButton#windowClose {{color:{p['Accent']};}}
    QToolButton#windowClose:hover {{color:{p['HighlightedText']};}}'''


def qt_style(p):
    from pathlib import Path
    from PyQt6.QtGui import QColor
    from designs import qt_style as base
    arrow=Path(__file__).resolve().parent/'assets'/('ghostbusters-down-light.svg' if QColor(p['Text']).lightnessF()>.5 else 'ghostbusters-down-dark.svg')
    return base(p)+f'''
    QWidget {{font-family:"Inter";}}
    QMainWindow,QDialog,QMessageBox,QWidget#controlRoot {{background:{enamel(p)};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand,QLabel#title,QLabel#dialogTitle {{color:{p['Text']};font-family:"Inter";font-weight:600;}}
    QLabel#eyebrow {{color:{p['Accent']};letter-spacing:1px;}}
    QPushButton,QToolButton {{background:{enamel(p)};color:{p['ButtonText']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-bottom-color:{p['Midlight']};border-radius:10px;padding:7px 12px;}}
    QPushButton:hover,QToolButton:hover {{background:{p['Mid']};border-color:{p['Accent']};}}
    QPushButton:pressed,QToolButton:pressed {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QPushButton:checked,QToolButton:checked,QPushButton#primary {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QToolButton:checked {{background:{p['Button']};color:{p['ButtonText']};border-color:{p['Accent']};border-bottom:2px solid {p['Accent']};}}
    QPushButton#primary:hover {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QPushButton:focus,QToolButton:focus {{border-color:{p['Accent']};}}
    QPushButton:disabled,QToolButton:disabled {{background:{p['Window']};color:{p['Disabled']};border-color:{p['Midlight']};}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:10px;padding:6px 8px;}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QTextEdit:focus,QPlainTextEdit:focus {{border-color:{p['Accent']};}}
    QLineEdit:disabled,QComboBox:disabled,QSpinBox:disabled {{background:{p['Window']};color:{p['Disabled']};}}
    QComboBox QAbstractItemView {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};}}
    QComboBox::down-arrow {{image:url("{arrow}");width:12px;height:8px;}}
    QGroupBox,QFrame#modernCard,QFrame#audioColumn,QFrame#presetCard,QFrame#changes {{background:{p['AlternateBase']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:10px;}}
    QGroupBox::title {{color:{p['Text']};font-weight:600;}}
    QWidget#modernRail {{background:{p['Base']};border:1px solid {p['Midlight']};border-radius:10px;}}
    QToolButton#railButton,QPushButton#railButton,QPushButton#launcherNav {{background:transparent;border-color:transparent;border-radius:10px;}}
    QToolButton#railButton:checked,QPushButton#railButton:checked,QPushButton#launcherNav:checked {{background:{p['Highlight']};color:{p['HighlightedText']};border-left:2px solid {p['Light']};}}
    QTabWidget::pane {{border:0;background:transparent;}}
    QTabBar::tab {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:10px;padding:8px 14px;margin:2px 2px 4px 0;}}
    QTabBar::tab:selected {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QTabBar::tab:hover {{border-color:{p['Accent']};}}
    QTreeView,QListView,QTableView {{background:{p['Base']};alternate-background-color:{p['AlternateBase']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:10px;}}
    QAbstractItemView::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QHeaderView::section,QTableCornerButton::section {{background:{p['Button']};color:{p['Text']};border:0;border-top:1px solid {p['Light']};border-bottom:1px solid {p['Midlight']};padding:7px;}}
    QMenuBar {{background:{p['Window']};color:{p['Text']};}}
    QMenu,QToolTip {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};border-radius:10px;padding:5px;}}
    QMenu::item {{padding:7px 28px;border-radius:10px;}}
    QMenu::item:selected,QMenuBar::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QMenu::item:disabled {{color:{p['Disabled']};}}
    QCheckBox::indicator,QRadioButton::indicator {{background:{p['Base']};border:1px solid {p['Midlight']};}}
    QCheckBox::indicator:checked,QRadioButton::indicator:checked {{background:{p['Highlight']};border-color:{p['Accent']};}}
    QRadioButton::indicator {{width:12px;height:12px;border:2px solid {p['Midlight']};border-radius:8px;}}
    QRadioButton::indicator:checked {{border-color:{p['Accent']};}}
    QSlider::groove:horizontal {{background:{p['Base']};height:5px;border:1px solid {p['Midlight']};border-radius:3px;}}
    QSlider::sub-page:horizontal {{background:{p['Accent']};}}
    QSlider::handle:horizontal {{background:{p['Highlight']};border:1px solid {p['LinkVisited']};width:14px;margin:-5px 0;border-radius:10px;}}
    QProgressBar {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:10px;}}
    QProgressBar::chunk {{background:{p['Highlight']};border-radius:10px;}}
    QScrollBar::handle:vertical,QScrollBar::handle:horizontal {{background:{p['Midlight']};border-radius:3px;}}
    '''


def files_style(p):
    return f'''QMainWindow,QWidget#filesBody,QWidget#hyperControlPanel,QToolBar,QFrame#addressRow {{background:{p['Window']};}}
    QToolBar QToolButton:checked {{background:{p['Button']};color:{p['ButtonText']};border-color:{p['Accent']};border-bottom:2px solid {p['Accent']};}}
    QPushButton#pickerAccept:hover {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Light']};}}
    QTreeWidget#places {{background:{p['Base']};border:1px solid {p['Midlight']};border-radius:10px;}}
    QTreeWidget#places::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QFrame#panelHeader {{background:{enamel(p)};border:0;border-bottom:1px solid {p['Accent']};}}
    QFrame#panelHeader QLabel {{color:{p['Text']};}}
    QFrame#pickerActions,QStatusBar {{background:{p['Window']};border-top:1px solid {p['Midlight']};}}
    QGroupBox#drivePartitionCard,QFrame#defaultsHero,QFrame#ramMetric {{background:{p['AlternateBase']};border:1px solid {p['Accent']};border-radius:10px;}}
    QToolButton#windowMinimize,QToolButton#windowMaximize {{color:{p['Text']};}}
    QToolButton#windowClose {{color:{p['Accent']};}}
    QToolButton#windowClose:hover,QToolButton#windowMinimize:hover,QToolButton#windowMaximize:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QToolButton#windowClose:disabled,QToolButton#windowMinimize:disabled,QToolButton#windowMaximize:disabled {{color:{p['Disabled']};}}'''


def waybar_style(p):
    return f'''* {{font-family:"Inter","FiraCode Nerd Font",sans-serif;}}
    tooltip,menu {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};border-radius:10px;}}
    menuitem:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}'''


def bar_controls(p,root):
    return f'''#custom-launcher {{background-image:url("{root/'assets/ghostbusters-mark.svg'}");background-repeat:no-repeat;background-position:8px center;padding:0 12px 0 38px;color:{p['Text']};border:0;border-radius:10px;}}
    #workspaces button,#custom-keys,#new-workspace,#xetal-pins .pin {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:10px;}}
    #workspaces button.active,#xetal-pins .pin.active {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};box-shadow:inset 0 1px {p['Light']};}}
    #workspaces button.urgent {{background:#8e0912;color:#ffffff;}}
    #clock {{background:transparent;color:{p['Text']};border-left:1px solid {p['Light']};border-radius:0;padding:0 12px;}}
    #audio {{border-right:1px solid {p['Midlight']};border-radius:0;}}
    #custom-updates {{color:{p['Accent']};}}
    #custom-launcher:hover,#custom-keys:hover,#xetal-pins .pin:hover {{border-color:{p['Accent']};background-color:{p['Mid']};}}'''


def notification_style(p):
    return f'''.control-center,.notification {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};border-radius:10px;}}
    .notification-content {{background:transparent;padding:13px;color:{p['Text']};}}
    .summary,.widget-title {{color:{p['Text']};font-family:"Inter",sans-serif;font-weight:600;}}
    .body,.time,.widget-label {{color:{p['PlaceholderText']};}}
    .notification-action,.close-button,.widget-title > button,.widget-buttons-grid > flowbox > flowboxchild > button {{background:{p['Button']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:10px;}}
    .notification-action:hover,.close-button:hover,.widget-title > button:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    .widget-dnd,.widget-mpris {{background:{p['AlternateBase']};color:{p['Text']};border-radius:10px;padding:8px;}}
    .widget-dnd > switch:checked {{background:{p['Highlight']};}}
    .widget-mpris button {{color:{p['Text']};}}'''


def compositor(p):
    return f'''# Ghostbusters: ectoplasm focus, rounded green rims and deep enamel.
general:col.active_border = rgb({p['Accent'][1:]}) rgb({p['Light'][1:]}) 135deg
general:col.inactive_border = rgba({p['Midlight'][1:]}cc)
general:border_size = 2
general:gaps_in = 5
general:gaps_out = 8
decoration:rounding = 10
decoration:shadow:enabled = true
decoration:shadow:range = 20
decoration:shadow:render_power = 3
decoration:shadow:color = rgba({p['Shadow'][1:]}bb)
decoration:blur:enabled = true
decoration:blur:size = 3
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.03
'''


def paint_surface(painter, box, colors, radius=10, opacity=100, focused=False):
    """Enamel with an ectoplasm rim. Slime stays inside the content-free edge."""
    from PyQt6.QtCore import Qt, QPointF
    from PyQt6.QtGui import QColor, QLinearGradient, QPainterPath, QPen
    if opacity < 100:
        from candycloud import faded_layer
        faded_layer(painter, box, opacity, lambda p,b: paint_surface(p,b,colors,radius,100,focused))
        return
    painter.save()
    path=QPainterPath();path.addRoundedRect(box,radius,radius)
    fill=QLinearGradient(box.topLeft(),box.bottomLeft())
    for stop,key in ((0,'Button'),(.22,'Window'),(1,'Base')):
        fill.setColorAt(stop,QColor(colors[key]))
    painter.fillPath(path,fill);painter.setClipPath(path,Qt.ClipOperation.IntersectClip)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(colors['Accent']),1.8 if focused else 1.2));painter.drawPath(path)
    shine=QColor(colors['Light']);shine.setAlpha(75)
    painter.setPen(QPen(shine,.8));painter.drawRoundedRect(box.adjusted(3,3,-3,-3),max(2,radius-2),max(2,radius-2))
    # Small, asymmetric drips only occupy the outer eight pixels. No overlay
    # widgets, input regions or text hit targets are introduced by decoration.
    for x,sx in ((box.left(),1),(box.right(),-1)):
        painter.save();painter.translate(x,box.top());painter.scale(sx,1)
        slime=QPainterPath(QPointF(2,17));slime.cubicTo(1,5,5,1,18,1)
        slime.lineTo(35,1);slime.cubicTo(37,1,36,5,32,5)
        slime.cubicTo(27,5,27,2,22,3);slime.cubicTo(16,3,18,8,14,8)
        slime.cubicTo(10,8,13,3,8,6);slime.cubicTo(4,9,8,17,5,20)
        slime.cubicTo(3,21,2,20,2,17)
        painter.fillPath(slime,QColor(colors['Accent']))
        painter.setPen(QPen(QColor(colors['Light']),.7));painter.drawLine(QPointF(9,3),QPointF(16,2))
        painter.restore()
    painter.restore()


def paint_tile(painter, box, colors, opacity=100, selected=False, hovered=False):
    from PyQt6.QtGui import QColor,QPen
    if opacity < 100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_tile(p,b,colors,100,selected,hovered));return
    paint_surface(painter,box,colors,10,100,selected or hovered)
    if selected or hovered:
        painter.save();wash=QColor(colors['Highlight']);wash.setAlpha(200 if selected else 45)
        painter.setBrush(wash);painter.setPen(QPen(QColor(colors['Accent']),1.2))
        painter.drawRoundedRect(box.adjusted(3,3,-3,-3),7,7);painter.restore()


def little_ghost(painter, center, size, accent, surface):
    """Original friendly slime courier, shared by the transfer scene."""
    from PyQt6.QtCore import Qt,QPointF
    from PyQt6.QtGui import QColor,QPainterPath,QPen
    painter.save();painter.translate(center);painter.scale(size/24,size/24)
    body=QPainterPath(QPointF(-11,8));body.cubicTo(-7,2,-12,-12,0,-13)
    body.cubicTo(12,-12,8,1,13,7);body.cubicTo(9,13,7,5,4,10)
    body.cubicTo(0,15,-1,6,-5,10);body.cubicTo(-8,12,-12,12,-11,8)
    painter.setPen(QPen(QColor(surface),1.2));painter.setBrush(QColor(accent));painter.drawPath(body)
    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(surface))
    for x in (-4,4):painter.drawEllipse(QPointF(x,-4),1.7,2.4)
    grin=QPainterPath(QPointF(-5,1));grin.quadTo(0,3,6,0);grin.quadTo(1,9,-5,1)
    painter.drawPath(grin);painter.restore()



"""Leviathan: obsidian reliquaries, geometric brass inlay and amethyst light."""


def obsidian(p):
    return f"qlineargradient(x1:0,y1:0,x2:.25,y2:1,stop:0 {p['Button']},stop:.22 {p['Window']},stop:.70 {p['Base']},stop:1 {p['Window']})"


def chrome_style(p):
    return f'''QToolButton {{background:transparent;color:{p['Text']};border:1px solid transparent;border-radius:6px;padding:0;}}
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
    arrow=Path(__file__).resolve().parent/'assets'/('leviathan-down-light.svg' if QColor(p['Text']).lightnessF()>.5 else 'leviathan-down-dark.svg')
    return base(p)+f'''
    QWidget {{font-family:"Inter";}}
    QMainWindow,QDialog,QMessageBox,QWidget#controlRoot {{background:{obsidian(p)};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand,QLabel#title,QLabel#dialogTitle {{color:{p['Text']};font-family:"Noto Serif";font-weight:600;}}
    QLabel#eyebrow {{color:{p['Accent']};letter-spacing:1px;}}
    QPushButton,QToolButton {{background:{obsidian(p)};color:{p['ButtonText']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-bottom-color:{p['Dark']};border-radius:6px;padding:7px 12px;}}
    QPushButton:hover,QToolButton:hover {{background:{p['Mid']};border-color:{p['Accent']};}}
    QPushButton:pressed,QToolButton:pressed {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QPushButton:checked,QToolButton:checked,QPushButton#primary {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QToolButton:checked {{background:{p['Button']};color:{p['ButtonText']};border-color:{p['Accent']};border-bottom:2px solid {p['Accent']};}}
    QPushButton#primary:hover {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QPushButton:focus,QToolButton:focus {{border-color:{p['Accent']};}}
    QPushButton:disabled,QToolButton:disabled {{background:{p['Window']};color:{p['Disabled']};border-color:{p['Midlight']};}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:6px;padding:6px 8px;}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QTextEdit:focus,QPlainTextEdit:focus {{border-color:{p['Accent']};}}
    QLineEdit:disabled,QComboBox:disabled,QSpinBox:disabled {{background:{p['Window']};color:{p['Disabled']};}}
    QComboBox QAbstractItemView {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};}}
    QComboBox::down-arrow {{image:url("{arrow}");width:12px;height:8px;}}
    QGroupBox,QFrame#modernCard,QFrame#audioColumn,QFrame#presetCard,QFrame#changes {{background:{p['AlternateBase']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:6px;}}
    QGroupBox::title {{color:{p['Text']};font-weight:600;}}
    QWidget#modernRail {{background:{p['Base']};border:1px solid {p['Midlight']};border-radius:6px;}}
    QToolButton#railButton,QPushButton#railButton,QPushButton#launcherNav {{background:transparent;border-color:transparent;border-radius:6px;}}
    QToolButton#railButton:checked,QPushButton#railButton:checked,QPushButton#launcherNav:checked {{background:{p['Highlight']};color:{p['HighlightedText']};border-left:2px solid {p['Light']};}}
    QTabWidget::pane {{border:0;background:transparent;}}
    QTabBar::tab {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:6px;padding:8px 14px;margin:2px 2px 4px 0;}}
    QTabBar::tab:selected {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QTabBar::tab:hover {{border-color:{p['Accent']};}}
    QTreeView,QListView,QTableView {{background:{p['Base']};alternate-background-color:{p['AlternateBase']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:6px;}}
    QAbstractItemView::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QHeaderView::section,QTableCornerButton::section {{background:{p['Button']};color:{p['Text']};border:0;border-top:1px solid {p['Light']};border-bottom:1px solid {p['Midlight']};padding:7px;}}
    QMenuBar {{background:{p['Window']};color:{p['Text']};}}
    QMenu,QToolTip {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Light']};border-radius:6px;padding:5px;}}
    QMenu::item {{padding:7px 28px;border-radius:6px;}}
    QMenu::item:selected,QMenuBar::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QMenu::item:disabled {{color:{p['Disabled']};}}
    QCheckBox::indicator,QRadioButton::indicator {{background:{p['Base']};border:1px solid {p['Midlight']};}}
    QCheckBox::indicator:checked,QRadioButton::indicator:checked {{background:{p['Highlight']};border-color:{p['Accent']};}}
    QRadioButton::indicator {{width:12px;height:12px;border:2px solid {p['Midlight']};border-radius:8px;}}
    QRadioButton::indicator:checked {{border-color:{p['Accent']};}}
    QSlider::groove:horizontal {{background:{p['Base']};height:5px;border:1px solid {p['Midlight']};border-radius:3px;}}
    QSlider::sub-page:horizontal {{background:{p['Accent']};}}
    QSlider::handle:horizontal {{background:{p['Highlight']};border:1px solid {p['LinkVisited']};width:14px;margin:-5px 0;border-radius:6px;}}
    QProgressBar {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:6px;}}
    QProgressBar::chunk {{background:{p['Highlight']};border-radius:6px;}}
    QScrollBar::handle:vertical,QScrollBar::handle:horizontal {{background:{p['Midlight']};border-radius:3px;}}
    '''


def files_style(p):
    return f'''QMainWindow,QWidget#filesBody,QWidget#hyperControlPanel,QToolBar,QFrame#addressRow {{background:{p['Window']};}}
    QToolBar QToolButton:checked {{background:{p['Button']};color:{p['ButtonText']};border-color:{p['Accent']};border-bottom:2px solid {p['Accent']};}}
    QPushButton#pickerAccept:hover {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Light']};}}
    QTreeWidget#places {{background:{p['Base']};border:1px solid {p['Midlight']};border-radius:6px;}}
    QTreeWidget#places::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QFrame#panelHeader {{background:{obsidian(p)};border:0;border-bottom:1px solid {p['Accent']};}}
    QFrame#panelHeader QLabel {{color:{p['Text']};}}
    QFrame#pickerActions,QStatusBar {{background:{p['Window']};border-top:1px solid {p['Midlight']};}}
    QGroupBox#drivePartitionCard,QFrame#defaultsHero,QFrame#ramMetric {{background:{p['AlternateBase']};border:1px solid {p['Accent']};border-radius:6px;}}
    QToolButton#windowMinimize,QToolButton#windowMaximize {{color:{p['Text']};}}
    QToolButton#windowClose {{color:{p['Accent']};}}
    QToolButton#windowClose:hover,QToolButton#windowMinimize:hover,QToolButton#windowMaximize:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QToolButton#windowClose:disabled,QToolButton#windowMinimize:disabled,QToolButton#windowMaximize:disabled {{color:{p['Disabled']};}}'''


def waybar_style(p):
    return f'''* {{font-family:"Inter","FiraCode Nerd Font",sans-serif;}}
    tooltip,menu {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};border-radius:6px;}}
    menuitem:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}'''


def bar_controls(p,root):
    return f'''#custom-launcher {{background-image:url("{root/'assets/leviathan-mark.svg'}");background-repeat:no-repeat;background-position:8px center;padding:0 12px 0 38px;color:{p['Text']};border:0;border-radius:6px;}}
    #workspaces button,#custom-keys,#new-workspace,#xetal-pins .pin {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:6px;}}
    #workspaces button.active,#xetal-pins .pin.active {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};box-shadow:inset 0 1px {p['Light']};}}
    #workspaces button.urgent {{background:#8e0912;color:#ffffff;}}
    #clock {{background:transparent;color:{p['Text']};border-left:1px solid {p['Light']};border-radius:0;padding:0 12px;}}
    #audio {{border-right:1px solid {p['Midlight']};border-radius:0;}}
    #custom-updates {{color:{p['Accent']};}}
    #custom-launcher:hover,#custom-keys:hover,#xetal-pins .pin:hover {{border-color:{p['Accent']};background-color:{p['Mid']};}}'''


def notification_style(p):
    return f'''.control-center,.notification {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-bottom-color:{p['Light']};border-radius:6px;}}
    .notification-content {{background:transparent;padding:13px;color:{p['Text']};}}
    .summary,.widget-title {{color:{p['Text']};font-family:"Inter",sans-serif;font-weight:600;}}
    .body,.time,.widget-label {{color:{p['PlaceholderText']};}}
    .notification-action,.close-button,.widget-title > button,.widget-buttons-grid > flowbox > flowboxchild > button {{background:{p['Button']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:6px;}}
    .notification-action:hover,.close-button:hover,.widget-title > button:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    .widget-dnd,.widget-mpris {{background:{p['AlternateBase']};color:{p['Text']};border-radius:6px;padding:8px;}}
    .widget-dnd > switch:checked {{background:{p['Highlight']};}}
    .widget-mpris button {{color:{p['Text']};}}'''


def compositor(p):
    return f'''# Leviathan: amethyst focus, engraved brass rims and obsidian depth.
general:col.active_border = rgb({p['Accent'][1:]}) rgb({p['Light'][1:]}) 135deg
general:col.inactive_border = rgba({p['Midlight'][1:]}cc)
general:border_size = 2
general:gaps_in = 5
general:gaps_out = 8
decoration:rounding = 6
decoration:shadow:enabled = true
decoration:shadow:range = 20
decoration:shadow:render_power = 3
decoration:shadow:color = rgba({p['Shadow'][1:]}bb)
decoration:blur:enabled = true
decoration:blur:size = 3
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.03
'''



def paint_surface(painter, box, colors, radius=6, opacity=100, focused=False):
    """Opaque obsidian with brass double rims and miniature corner engravings.

    All ornament stays within the outer six pixels so content remains clear.
    Opacity applies to the entire surface, including its engraved edges.
    """
    from PyQt6.QtCore import Qt, QPointF
    from PyQt6.QtGui import QColor, QLinearGradient, QPainterPath, QPen
    if opacity < 100:
        from candycloud import faded_layer
        faded_layer(painter, box, opacity, lambda p,b: paint_surface(p,b,colors,radius,100,focused)); return
    painter.save(); path=QPainterPath(); path.addRoundedRect(box,radius,radius)
    fill=QLinearGradient(box.topLeft(),box.bottomRight())
    for stop,key in ((0,'Button'),(.22,'Window'),(.70,'Base'),(1,'Window')):
        fill.setColorAt(stop,QColor(colors[key]))
    painter.fillPath(path,fill); painter.setClipPath(path,Qt.ClipOperation.IntersectClip)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(colors['Accent'] if focused else colors['Light']),1));painter.drawPath(path)
    inset=QColor(colors['Midlight']);inset.setAlpha(110)
    painter.setPen(QPen(inset,.7));painter.drawRoundedRect(box.adjusted(3,3,-3,-3),max(1,radius-2),max(1,radius-2))
    # Inset diamonds and paired geometric turns, mirrored at every corner.
    for x,sx in ((box.left(),1),(box.right(),-1)):
        for y,sy in ((box.top(),1),(box.bottom(),-1)):
            painter.save();painter.translate(x,y);painter.scale(sx,sy)
            knot=QPainterPath(QPointF(2,17));knot.lineTo(2,7);knot.lineTo(7,2);knot.lineTo(17,2)
            knot.moveTo(4,13);knot.lineTo(4,7);knot.lineTo(7,4);knot.lineTo(13,4)
            painter.setPen(QPen(QColor(colors['Light']),.8));painter.drawPath(knot)
            diamond=QPainterPath(QPointF(5,2));diamond.lineTo(8,5);diamond.lineTo(5,8);diamond.lineTo(2,5);diamond.closeSubpath()
            painter.setBrush(QColor(colors['Window']));painter.drawPath(diamond)
            painter.setPen(QPen(QColor(colors['Accent']),.8));painter.drawPoint(QPointF(5,5))
            painter.restore()
    painter.restore()


def paint_tile(painter, box, colors, opacity=100, selected=False, hovered=False):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor,QPen
    if opacity < 100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_tile(p,b,colors,100,selected,hovered));return
    paint_surface(painter,box,colors,6,100,selected or hovered)
    if selected or hovered:
        painter.save();wash=QColor(colors['Highlight']);wash.setAlpha(190 if selected else 55)
        painter.setBrush(wash);painter.setPen(QPen(QColor(colors['Accent']),1))
        painter.drawRoundedRect(box.adjusted(2,2,-2,-2),4,4);painter.restore()


def puzzle_cube(p, center, size, brass, violet, surface):
    """Small isometric brass puzzle box, scalable for transfers and previews."""
    from PyQt6.QtCore import QPointF,Qt
    from PyQt6.QtGui import QColor,QPainterPath,QPen
    p.save();p.translate(center);p.scale(size/24,size/24)
    p.setPen(QPen(QColor(brass),1));p.setBrush(QColor(surface))
    for points in (((0,-13),(12,-7),(0,-1),(-12,-7)),((-12,-7),(0,-1),(0,13),(-12,6)),((0,-1),(12,-7),(12,6),(0,13))):
        path=QPainterPath(QPointF(*points[0]))
        for point in points[1:]:path.lineTo(*point)
        path.closeSubpath();p.drawPath(path)
    p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor(brass),.65))
    engrave=QPainterPath(QPointF(-9,-3));engrave.lineTo(-3,0);engrave.lineTo(-3,8);engrave.lineTo(-8,5);engrave.lineTo(-8,1);engrave.lineTo(-6,2)
    engrave.moveTo(3,0);engrave.lineTo(9,-3);engrave.lineTo(9,4);engrave.lineTo(5,6);engrave.lineTo(5,2)
    engrave.moveTo(-7,-7);engrave.lineTo(0,-10);engrave.lineTo(7,-7);engrave.lineTo(0,-4);engrave.closeSubpath();p.drawPath(engrave)
    p.setBrush(QColor(violet));p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(0,-7),1.1,1.1)
    p.restore()

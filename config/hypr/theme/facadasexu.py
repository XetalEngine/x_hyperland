"""777 Facadas Exu: black lacquer, oxblood velvet, ivory and copper."""
from pathlib import Path


def lacquer(p):
    return f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['Button']},stop:.32 {p['Window']},stop:1 {p['Base']})"


def chrome_style(p):
    return f'''QToolButton {{background:transparent;color:{p['Text']};border:1px solid transparent;border-radius:6px;padding:0;}}
    QToolButton:hover,QToolButton:pressed {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QToolButton:focus {{border-color:{p['Accent']};}}
    QToolButton#windowClose {{color:{p['Text']};}}
    QToolButton:disabled {{color:{p['Disabled']};}}'''


def qt_style(p):
    from PyQt6.QtGui import QColor
    from designs import qt_style as base
    arrow=Path(__file__).resolve().parent/'assets'/('facadasexu-down-light.svg' if QColor(p['Text']).lightnessF()>.5 else 'facadasexu-down-dark.svg')
    return base(p)+f'''
    QWidget {{font-family:"Inter";}}
    QMainWindow,QDialog,QMessageBox,QWidget#controlRoot {{background:{p['Window']};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand,QLabel#title,QLabel#dialogTitle {{color:{p['Text']};font-weight:600;}}
    QLabel#eyebrow {{color:{p['Link']};letter-spacing:1px;}}
    QPushButton,QToolButton {{background:{lacquer(p)};color:{p['ButtonText']};border:1px solid {p['Midlight']};border-radius:7px;padding:7px 12px;}}
    QPushButton:hover,QToolButton:hover {{background:{p['Mid']};border-color:{p['Light']};}}
    QPushButton:pressed,QToolButton:pressed,QPushButton:checked,QToolButton:checked,QPushButton#primary {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QPushButton#primary:hover {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Light']};}}
    QPushButton:focus,QToolButton:focus {{border-color:{p['Accent']};}}
    QPushButton:disabled,QToolButton:disabled {{background:{p['Window']};color:{p['Disabled']};border-color:{p['Midlight']};}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:6px;padding:6px 8px;}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QTextEdit:focus,QPlainTextEdit:focus {{border-color:{p['Accent']};}}
    QLineEdit:disabled,QComboBox:disabled,QSpinBox:disabled {{color:{p['Disabled']};background:{p['Window']};}}
    QComboBox QAbstractItemView {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Midlight']};}}
    QComboBox::down-arrow {{image:url("{arrow}");width:12px;height:8px;}}
    QGroupBox,QFrame#modernCard,QFrame#audioColumn,QFrame#presetCard,QFrame#changes {{background:{p['AlternateBase']};border:1px solid {p['Midlight']};border-radius:8px;}}
    QGroupBox::title {{color:{p['Text']};font-weight:600;}}
    QWidget#modernRail {{background:{p['Base']};border:1px solid {p['Midlight']};border-radius:8px;}}
    QToolButton#railButton,QPushButton#railButton,QPushButton#launcherNav {{background:transparent;border-color:transparent;border-radius:7px;}}
    QToolButton#railButton:checked,QPushButton#railButton:checked,QPushButton#launcherNav:checked {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QTabWidget::pane {{border:0;background:transparent;}}
    QTabBar::tab {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:7px;padding:8px 14px;margin:2px 2px 4px 0;}}
    QTabBar::tab:selected {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QTabBar::tab:hover {{border-color:{p['Light']};}}
    QTreeView,QListView,QTableView {{background:{p['Base']};alternate-background-color:{p['AlternateBase']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:7px;}}
    QAbstractItemView::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QHeaderView::section,QTableCornerButton::section {{background:{p['Button']};color:{p['Text']};border:0;border-bottom:1px solid {p['Midlight']};padding:7px;}}
    QMenuBar {{background:{p['Window']};color:{p['Text']};}}
    QMenu,QToolTip {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:7px;padding:5px;}}
    QMenu::item {{padding:7px 28px;border-radius:6px;}}
    QMenu::item:selected,QMenuBar::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QMenu::item:disabled {{color:{p['Disabled']};}}
    QCheckBox::indicator,QRadioButton::indicator {{background:{p['Base']};border:1px solid {p['Midlight']};}}
    QCheckBox::indicator:checked,QRadioButton::indicator:checked {{background:{p['Highlight']};border-color:{p['Accent']};}}
    QRadioButton::indicator {{width:12px;height:12px;border:2px solid {p['Midlight']};border-radius:8px;}}
    QSlider::groove:horizontal {{background:{p['Base']};height:5px;border:1px solid {p['Midlight']};border-radius:3px;}}
    QSlider::sub-page:horizontal {{background:{p['Highlight']};}}
    QSlider::handle:horizontal {{background:{p['Text']};border:1px solid {p['Midlight']};width:14px;margin:-5px 0;border-radius:7px;}}
    QProgressBar {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:5px;}}
    QProgressBar::chunk {{background:{p['Highlight']};border-radius:4px;}}
    QScrollBar::handle:vertical,QScrollBar::handle:horizontal {{background:{p['Midlight']};border-radius:3px;}}
    '''


def files_style(p):
    return f'''QMainWindow,QWidget#filesBody,QWidget#hyperControlPanel,QToolBar,QFrame#addressRow {{background:{p['Window']};}}
    QTreeWidget#places {{background:{p['Base']};border:1px solid {p['Midlight']};border-radius:7px;}}
    QTreeWidget#places::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QFrame#panelHeader {{background:{lacquer(p)};border:0;border-bottom:1px solid {p['Midlight']};}}
    QFrame#panelHeader QLabel {{color:{p['Text']};}}
    QFrame#pickerActions,QStatusBar {{background:{p['Window']};border-top:1px solid {p['Midlight']};}}
    QFrame#defaultsHero,QFrame#ramMetric {{background:{p['AlternateBase']};border:1px solid {p['Midlight']};border-radius:8px;}}
    QToolButton#windowClose,QToolButton#windowMinimize,QToolButton#windowMaximize {{color:{p['Text']};}}
    QToolButton#windowClose:hover,QToolButton#windowMinimize:hover,QToolButton#windowMaximize:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QToolButton#windowClose:disabled,QToolButton#windowMinimize:disabled,QToolButton#windowMaximize:disabled {{color:{p['Disabled']};}}
    QPushButton#pickerAccept:hover {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Light']};}}'''


def waybar_style(p):
    return f'''* {{font-family:"Inter","FiraCode Nerd Font",sans-serif;}}
    tooltip,menu {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:7px;}}
    menuitem:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}'''


def bar_controls(p,root):
    return f'''#custom-launcher {{background-image:url("{root/'assets/facadasexu-mark.svg'}");background-repeat:no-repeat;background-position:8px center;padding:0 12px 0 38px;color:{p['Text']};border:0;border-radius:7px;}}
    #workspaces button,#custom-keys,#new-workspace,#xetal-pins .pin {{background:transparent;color:{p['Text']};border:1px solid transparent;border-radius:7px;}}
    #workspaces button.active,#xetal-pins .pin.active {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    #workspaces button.urgent {{background:{p['Accent']};color:{p['Base']};}}
    #clock {{background:transparent;color:{p['Text']};border-left:1px solid {p['Midlight']};border-radius:0;padding:0 12px;}}
    #audio {{border-right:1px solid {p['Midlight']};border-radius:0;}}
    #custom-updates {{color:{p['Link']};}}
    #custom-launcher:hover,#custom-keys:hover,#xetal-pins .pin:hover,#new-workspace:hover {{border-color:{p['Midlight']};background-color:{p['Mid']};}}'''


def notification_style(p):
    return f'''.control-center,.notification {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:8px;}}
    .notification-content {{background:transparent;padding:13px;color:{p['Text']};}}
    .summary,.widget-title {{color:{p['Text']};font-family:"Inter",sans-serif;font-weight:600;}}
    .body,.time,.widget-label {{color:{p['PlaceholderText']};}}
    .notification-action,.close-button,.widget-title > button,.widget-buttons-grid > flowbox > flowboxchild > button {{background:{p['Button']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:6px;}}
    .notification-action:hover,.close-button:hover,.widget-title > button:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    .widget-dnd,.widget-mpris {{background:{p['AlternateBase']};color:{p['Text']};border-radius:7px;padding:8px;}}
    .widget-dnd > switch:checked {{background:{p['Highlight']};}}
    .widget-mpris button {{color:{p['Text']};}}'''


def compositor(p):
    return f'''# 777 Facadas Exu: oxblood focus, copper edges and soft shadows.
general:col.active_border = rgb({p['Accent'][1:]}) rgb({p['Light'][1:]}) 135deg
general:col.inactive_border = rgba({p['Midlight'][1:]}bb)
general:border_size = 2
general:gaps_in = 5
general:gaps_out = 8
decoration:rounding = 8
decoration:shadow:enabled = true
decoration:shadow:range = 20
decoration:shadow:render_power = 3
decoration:shadow:color = rgba({p['Shadow'][1:]}bb)
decoration:blur:enabled = true
decoration:blur:size = 3
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.02
'''


def paint_surface(painter,box,colors,radius=8,opacity=100,focused=False):
    """Quiet lacquer, copper hairline and a short warm reflection at the rim."""
    from PyQt6.QtCore import Qt,QPointF
    from PyQt6.QtGui import QColor,QLinearGradient,QPainterPath,QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_surface(p,b,colors,radius,100,focused));return
    painter.save();path=QPainterPath();path.addRoundedRect(box,radius,radius)
    fill=QLinearGradient(box.topLeft(),box.bottomLeft())
    for stop,key in ((0,'Button'),(.32,'Window'),(1,'Base')):fill.setColorAt(stop,QColor(colors[key]))
    painter.fillPath(path,fill);painter.setClipPath(path,Qt.ClipOperation.IntersectClip)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(colors['Accent'] if focused else colors['Midlight']),1));painter.drawPath(path)
    gleam=QLinearGradient(box.topLeft(),box.topRight())
    copper=QColor(colors['Light']);clear=QColor(copper);clear.setAlpha(0)
    gleam.setColorAt(0,clear);gleam.setColorAt(.18,copper);gleam.setColorAt(.55,clear);gleam.setColorAt(1,clear)
    painter.setPen(QPen(gleam,1));painter.drawLine(QPointF(box.left()+radius,box.top()+1),QPointF(box.right()-radius,box.top()+1))
    painter.restore()


def paint_tile(painter,box,colors,opacity=100,selected=False,hovered=False):
    from PyQt6.QtGui import QColor,QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_tile(p,b,colors,100,selected,hovered));return
    paint_surface(painter,box,colors,7,100,selected or hovered)
    if selected or hovered:
        painter.save();wash=QColor(colors['Highlight']);wash.setAlpha(215 if selected else 45)
        painter.setBrush(wash);painter.setPen(QPen(QColor(colors['Accent']),1));painter.drawRoundedRect(box,7,7);painter.restore()

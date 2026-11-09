"""Midnight Run: graphite lacquer, cyan edges and magenta neon."""


def lacquer(p):
    return f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['Button']},stop:.22 {p['Window']},stop:1 {p['Base']})"


def chrome_style(p):
    return f'''QToolButton {{background:transparent;color:{p['Text']};border:1px solid transparent;border-radius:5px;padding:0;}}
    QToolButton:hover {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QToolButton:pressed {{background:{p['Mid']};}}
    QToolButton:focus {{border-color:{p['Accent']};}}
    QToolButton:disabled {{color:{p['Disabled']};}}
    QToolButton#windowClose {{color:{p['LinkVisited']};}}
    QToolButton#windowClose:hover {{color:{p['HighlightedText']};}}'''


def qt_style(p):
    from pathlib import Path
    from PyQt6.QtGui import QColor
    from designs import qt_style as base
    arrow=Path(__file__).resolve().parent/'assets'/('midnightrun-down-light.svg' if QColor(p['Text']).lightnessF()>.5 else 'midnightrun-down-dark.svg')
    return base(p)+f'''
    QWidget {{font-family:"Inter";}}
    QMainWindow,QDialog,QMessageBox,QWidget#controlRoot {{background:{lacquer(p)};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand,QLabel#title,QLabel#dialogTitle {{color:{p['Text']};font-weight:700;}}
    QLabel#eyebrow {{color:{p['Accent']};letter-spacing:1px;}}
    QPushButton,QToolButton {{background:{lacquer(p)};color:{p['ButtonText']};border:1px solid {p['Midlight']};border-radius:5px;padding:7px 12px;}}
    QPushButton:hover,QToolButton:hover {{background:{p['Mid']};border-color:{p['Accent']};}}
    QPushButton:pressed,QToolButton:pressed {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QPushButton:checked,QToolButton:checked,QPushButton#primary {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['LinkVisited']};}}
    QPushButton#primary:hover {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QPushButton:focus,QToolButton:focus {{border-color:{p['Accent']};}}
    QPushButton:disabled,QToolButton:disabled {{background:{p['Window']};color:{p['Disabled']};border-color:{p['Midlight']};}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:5px;padding:6px 8px;}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QTextEdit:focus,QPlainTextEdit:focus {{border-color:{p['Accent']};}}
    QLineEdit:disabled,QComboBox:disabled,QSpinBox:disabled {{background:{p['Window']};color:{p['Disabled']};}}
    QComboBox QAbstractItemView {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};}}
    QComboBox::down-arrow {{image:url("{arrow}");width:12px;height:8px;}}
    QGroupBox,QFrame#modernCard,QFrame#audioColumn,QFrame#presetCard,QFrame#changes {{background:{p['AlternateBase']};border:1px solid {p['Midlight']};border-top-color:{p['Accent']};border-radius:7px;}}
    QGroupBox::title {{color:{p['Text']};font-weight:600;}}
    QWidget#modernRail {{background:{p['Base']};border:1px solid {p['Midlight']};border-radius:7px;}}
    QToolButton#railButton,QPushButton#railButton,QPushButton#launcherNav {{background:transparent;border-color:transparent;border-radius:4px;}}
    QToolButton#railButton:checked,QPushButton#railButton:checked,QPushButton#launcherNav:checked {{background:{p['Highlight']};color:{p['HighlightedText']};border-left:2px solid {p['Accent']};}}
    QTabWidget::pane {{border:0;background:transparent;}}
    QTabBar::tab {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:5px;padding:8px 14px;margin:2px 2px 4px 0;}}
    QTabBar::tab:selected {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['LinkVisited']};}}
    QTabBar::tab:hover {{border-color:{p['Accent']};}}
    QTreeView,QListView,QTableView {{background:{p['Base']};alternate-background-color:{p['AlternateBase']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:6px;}}
    QAbstractItemView::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QHeaderView::section,QTableCornerButton::section {{background:{p['Button']};color:{p['Text']};border:0;border-bottom:1px solid {p['Accent']};padding:7px;}}
    QMenuBar {{background:{p['Window']};color:{p['Text']};}}
    QMenu,QToolTip {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};border-radius:6px;padding:5px;}}
    QMenu::item {{padding:7px 28px;border-radius:4px;}}
    QMenu::item:selected,QMenuBar::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QMenu::item:disabled {{color:{p['Disabled']};}}
    QCheckBox::indicator,QRadioButton::indicator {{background:{p['Base']};border:1px solid {p['Midlight']};}}
    QCheckBox::indicator:checked,QRadioButton::indicator:checked {{background:{p['Highlight']};border-color:{p['LinkVisited']};}}
    QRadioButton::indicator {{width:12px;height:12px;border:2px solid {p['Midlight']};border-radius:8px;}}
    QRadioButton::indicator:checked {{border-color:{p['Accent']};}}
    QSlider::groove:horizontal {{background:{p['Base']};height:5px;border:1px solid {p['Midlight']};border-radius:3px;}}
    QSlider::sub-page:horizontal {{background:{p['Accent']};}}
    QSlider::handle:horizontal {{background:{p['Highlight']};border:1px solid {p['LinkVisited']};width:14px;margin:-5px 0;border-radius:6px;}}
    QProgressBar {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:5px;}}
    QProgressBar::chunk {{background:{p['Highlight']};border-radius:4px;}}
    QScrollBar::handle:vertical,QScrollBar::handle:horizontal {{background:{p['Midlight']};border-radius:3px;}}
    '''


def files_style(p):
    return f'''QMainWindow,QWidget#filesBody,QWidget#hyperControlPanel,QToolBar,QFrame#addressRow {{background:{p['Window']};}}
    QTreeWidget#places {{background:{p['Base']};border:1px solid {p['Midlight']};border-radius:5px;}}
    QTreeWidget#places::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QFrame#panelHeader {{background:{lacquer(p)};border:0;border-bottom:1px solid {p['Accent']};}}
    QFrame#panelHeader QLabel {{color:{p['Text']};}}
    QFrame#pickerActions,QStatusBar {{background:{p['Window']};border-top:1px solid {p['Midlight']};}}
    QGroupBox#drivePartitionCard,QFrame#defaultsHero,QFrame#ramMetric {{background:{p['AlternateBase']};border:1px solid {p['Accent']};border-radius:6px;}}
    QToolButton#windowMinimize,QToolButton#windowMaximize {{color:{p['Text']};}}
    QToolButton#windowClose {{color:{p['LinkVisited']};}}
    QToolButton#windowClose:hover,QToolButton#windowMinimize:hover,QToolButton#windowMaximize:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QToolButton#windowClose:disabled,QToolButton#windowMinimize:disabled,QToolButton#windowMaximize:disabled {{color:{p['Disabled']};}}'''


def waybar_style(p):
    return f'''* {{font-family:"Inter","FiraCode Nerd Font",sans-serif;}}
    tooltip,menu {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};border-radius:6px;}}
    menuitem:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}'''


def bar_controls(p,root):
    return f'''#custom-launcher {{background-image:url("{root/'assets/midnightrun-mark.svg'}");background-repeat:no-repeat;background-position:8px center;padding:0 12px 0 38px;color:{p['Text']};border:0;border-radius:5px;}}
    #workspaces button,#custom-keys,#new-workspace,#xetal-pins .pin {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:5px;}}
    #workspaces button.active,#xetal-pins .pin.active {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};box-shadow:inset 0 -1px {p['LinkVisited']};}}
    #workspaces button.urgent {{background:#952d53;color:#ffffff;}}
    #clock {{background:transparent;color:{p['Text']};border-left:1px solid {p['Midlight']};border-radius:0;padding:0 12px;}}
    #audio {{border-right:1px solid {p['Midlight']};border-radius:0;}}
    #custom-updates {{color:{p['LinkVisited']};}}
    #custom-launcher:hover,#custom-keys:hover,#xetal-pins .pin:hover {{border-color:{p['Accent']};background-color:{p['Mid']};}}'''


def notification_style(p):
    return f'''.control-center,.notification {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};border-bottom-color:{p['LinkVisited']};border-radius:8px;}}
    .notification-content {{background:transparent;padding:13px;color:{p['Text']};}}
    .summary,.widget-title {{color:{p['Text']};font-family:"Inter",sans-serif;font-weight:600;}}
    .body,.time,.widget-label {{color:{p['PlaceholderText']};}}
    .notification-action,.close-button,.widget-title > button,.widget-buttons-grid > flowbox > flowboxchild > button {{background:{p['Button']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:5px;}}
    .notification-action:hover,.close-button:hover,.widget-title > button:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    .widget-dnd,.widget-mpris {{background:{p['AlternateBase']};color:{p['Text']};border-radius:6px;padding:8px;}}
    .widget-dnd > switch:checked {{background:{p['Highlight']};}}
    .widget-mpris button {{color:{p['Text']};}}'''


def compositor(p):
    return f'''# Midnight Run: cyan headlight and magenta tail-light edges.
general:col.active_border = rgb({p['Accent'][1:]}) rgb({p['LinkVisited'][1:]}) 135deg
general:col.inactive_border = rgba({p['Midlight'][1:]}cc)
general:border_size = 2
general:gaps_in = 5
general:gaps_out = 8
decoration:rounding = 7
decoration:shadow:enabled = true
decoration:shadow:range = 20
decoration:shadow:render_power = 3
decoration:shadow:color = rgba({p['Shadow'][1:]}bb)
decoration:blur:enabled = true
decoration:blur:size = 4
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.03
'''


def paint_surface(painter,box,colors,radius=7,opacity=100,focused=False):
    from PyQt6.QtCore import Qt,QPointF
    from PyQt6.QtGui import QColor,QLinearGradient,QPainterPath,QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_surface(p,b,colors,radius,100,focused));return
    painter.save();path=QPainterPath();path.addRoundedRect(box,radius,radius)
    fill=QLinearGradient(box.topLeft(),box.bottomLeft())
    for stop,key in ((0,'Button'),(.22,'Window'),(1,'Base')):fill.setColorAt(stop,QColor(colors[key]))
    painter.fillPath(path,fill);painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(colors['Accent'] if focused else colors['Midlight']),1));painter.drawPath(path)
    painter.setClipPath(path,Qt.ClipOperation.IntersectClip)
    painter.setPen(QPen(QColor(colors['Accent']),1))
    painter.drawLine(QPointF(box.left()+radius,box.top()+1),QPointF(box.right()-radius,box.top()+1))
    pink=QColor(colors['LinkVisited']);pink.setAlpha(225 if focused else 145);painter.setPen(QPen(pink,1))
    painter.drawLine(QPointF(box.left()+radius,box.bottom()-1),QPointF(box.right()-radius,box.bottom()-1))
    painter.restore()


def paint_tile(painter,box,colors,opacity=100,selected=False,hovered=False):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor,QPen
    paint_surface(painter,box,colors,6,opacity,selected or hovered)
    if selected or hovered:
        painter.save();wash=QColor(colors['Highlight']);wash.setAlpha(155 if selected else 40)
        painter.setBrush(wash);painter.setPen(QPen(QColor(colors['Accent']),1));painter.drawRoundedRect(box,6,6);painter.restore()

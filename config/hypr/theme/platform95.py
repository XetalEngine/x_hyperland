"""Platform 95: ivory casework, espresso headers and antique-gold bevels."""
from pathlib import Path

ASSETS = Path(__file__).resolve().parent/'assets'


def casework(p):
    return f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['Button']},stop:.14 {p['Window']},stop:1 {p['Window']})"


def gold(p):
    return f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['Highlight']},stop:1 {p['Highlight']})"


def bevel(p, inset=False):
    top, bottom = (p['Dark'], p['Light']) if inset else (p['Light'], p['Dark'])
    return f"border:2px solid {bottom};border-top-color:{top};border-left-color:{top};border-radius:1px;"


def chrome_style(p):
    return f'''QToolButton {{background:{casework(p)};color:{p['ButtonText']};{bevel(p)}padding:0;}}
    QToolButton:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QToolButton:pressed {{{bevel(p,True)}background:{p['Mid']};}}
    QToolButton:focus {{border-color:{p['Accent']};}}
    QToolButton:disabled {{background:{p['Window']};color:{p['Disabled']};}}
    QToolButton#windowClose:hover {{background:#903b2b;color:#fff8e9;}}'''


def qt_style(p):
    from designs import qt_style as base
    from PyQt6.QtGui import QColor
    arrow=ASSETS/('platform95-down-ivory.svg' if QColor(p['Text']).lightnessF()>.5 else 'platform95-down-espresso.svg')
    return base(p)+f'''
    QWidget {{font-family:"Noto Sans";}}
    QMainWindow,QDialog,QMessageBox,QWidget#controlRoot {{background:{casework(p)};color:{p['Text']};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QWidget#xetalDialogHeader {{background:{p['Dark']};border-radius:0;}}
    QWidget#xetalDialogHeader QLabel {{color:{p['BrightText']};}}
    QLabel#brand,QLabel#title,QLabel#dialogTitle {{font-weight:700;letter-spacing:0;}}
    QLabel#eyebrow {{color:{p['Link']};letter-spacing:1px;}}
    QLabel#section {{font-size:19px;font-weight:700;}}
    QPushButton,QToolButton {{background:{casework(p)};color:{p['ButtonText']};{bevel(p)}padding:6px 11px;}}
    QPushButton:hover,QToolButton:hover {{background:{p['Mid']};}}
    QPushButton:focus,QToolButton:focus {{border-color:{p['Accent']};padding:6px 11px;}}
    QPushButton:pressed,QToolButton:pressed {{background:{p['Mid']};{bevel(p,True)}}}
    QPushButton:checked,QPushButton#primary,QToolButton:checked {{background:{gold(p)};color:{p['HighlightedText']};{bevel(p)}font-weight:700;}}
    QPushButton#primary:hover {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QPushButton:disabled,QToolButton:disabled {{background:{p['Window']};color:{p['Disabled']};border-color:{p['Midlight']};}}
    QPushButton#danger,QPushButton#logout {{background:#903b2b;color:#fff8e9;border-color:#5a241b;border-top-color:#d19c85;}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {{background:{p['Base']};color:{p['Text']};
        {bevel(p,True)}padding:5px 7px;selection-background-color:{p['Highlight']};selection-color:{p['HighlightedText']};}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QTextEdit:focus,QPlainTextEdit:focus {{border-color:{p['Accent']};}}
    QLineEdit:disabled,QComboBox:disabled,QSpinBox:disabled,QDoubleSpinBox:disabled {{background:{p['Window']};color:{p['Disabled']};}}
    QLineEdit#appSearch {{border-radius:1px;padding:7px 9px;}}
    QComboBox::drop-down {{background:{casework(p)};border-left:1px solid {p['Midlight']};width:22px;}}
    QComboBox::down-arrow {{image:url("{arrow}");width:10px;height:6px;}}
    QComboBox QAbstractItemView {{background:{p['Base']};color:{p['Text']};border:2px solid {p['Dark']};padding:2px;}}
    QGroupBox,QFrame#modernCard,QFrame#audioColumn,QFrame#presetCard,QFrame#changes {{background:{p['Window']};
        border:1px solid {p['Midlight']};border-bottom-color:{p['Light']};border-right-color:{p['Light']};border-radius:1px;}}
    QGroupBox::title {{color:{p['Text']};font-weight:700;}}
    QWidget#modernRail {{background:{casework(p)};{bevel(p,True)}}}
    QToolButton#railButton,QPushButton#railButton,QPushButton#launcherNav {{background:transparent;border:2px solid transparent;border-radius:1px;}}
    QToolButton#railButton:checked,QPushButton#railButton:checked,QPushButton#launcherNav:checked {{background:{p['Highlight']};color:{p['HighlightedText']};{bevel(p,True)}}}
    QTabWidget::pane {{background:{p['Window']};border:1px solid {p['Midlight']};}}
    QTabBar::tab {{background:{p['Button']};color:{p['Text']};{bevel(p)}padding:6px 13px;margin:2px 1px 0 0;}}
    QTabBar::tab:selected {{background:{p['Window']};color:{p['Text']};border-bottom-color:{p['Window']};font-weight:700;}}
    QTabBar::tab:hover {{background:{p['Mid']};}}
    QTreeView,QListView,QTableView {{background:{p['Base']};alternate-background-color:{p['AlternateBase']};
        color:{p['Text']};{bevel(p,True)}selection-background-color:{p['Highlight']};selection-color:{p['HighlightedText']};}}
    QAbstractItemView::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QHeaderView::section,QTableCornerButton::section {{background:{casework(p)};color:{p['Text']};{bevel(p)}padding:5px 7px;}}
    QMenuBar {{background:{p['Window']};color:{p['Text']};border-bottom:1px solid {p['Midlight']};}}
    QMenuBar::item:selected,QMenu::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QMenu,QToolTip {{background:{p['Window']};color:{p['Text']};{bevel(p)}padding:3px;}}
    QMenu::item {{padding:6px 28px;border-radius:0;}}
    QMenu::item:disabled {{color:{p['Disabled']};}}
    QMenu::separator {{height:1px;background:{p['Midlight']};margin:3px 4px;}}
    QCheckBox::indicator {{background:{p['Base']};{bevel(p,True)}width:15px;height:15px;}}
    QCheckBox::indicator:checked {{background:{p['Highlight']};border-radius:1px;border-color:{p['Dark']};}}
    QRadioButton::indicator {{background:{p['Base']};border:2px solid {p['Midlight']};border-radius:8px;width:12px;height:12px;}}
    QRadioButton::indicator:checked {{background:{p['Highlight']};border:3px solid {p['Dark']};}}
    QCheckBox::indicator:disabled,QRadioButton::indicator:disabled {{background:{p['Window']};border-color:{p['Disabled']};}}
    QSlider::groove:horizontal {{height:3px;background:{p['Base']};border:1px solid {p['Midlight']};border-bottom-color:{p['Light']};border-radius:0;}}
    QSlider::sub-page:horizontal {{background:{p['Highlight']};border-radius:0;}}
    QSlider::handle:horizontal {{background:{gold(p)};{bevel(p)}width:12px;margin:-7px 0;}}
    QSlider::handle:vertical {{background:{gold(p)};{bevel(p)}height:12px;}}
    QProgressBar {{background:{p['Base']};color:{p['Text']};{bevel(p,True)}text-align:center;}}
    QProgressBar::chunk {{background:{p['Highlight']};border-radius:0;}}
    QScrollBar:vertical {{background:{p['Window']};width:13px;margin:1px;}}
    QScrollBar:horizontal {{background:{p['Window']};height:13px;margin:1px;}}
    QScrollBar::handle:vertical,QScrollBar::handle:horizontal {{background:{casework(p)};{bevel(p)}min-height:24px;min-width:24px;}}
    QSplitter::handle {{background:{p['Window']};}}
    QLabel#status {{background:{p['AlternateBase']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:1px;}}
    '''


def files_style(p):
    return f'''QMainWindow,QWidget#filesBody,QWidget#hyperControlPanel,QToolBar,QFrame#addressRow {{background:{casework(p)};}}
    QGroupBox#drivePartitionCard,QFrame#defaultsHero,QFrame#ramMetric,QFrame#ramMode,QFrame#filterGroupBox {{background:{p['Window']};{bevel(p)}}}
    QTreeWidget#places {{background:{p['Window']};{bevel(p,True)}}}
    QTreeWidget#places::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};border-radius:0;}}
    QFrame#pickerActions,QStatusBar {{background:{p['Window']};border-top:1px solid {p['Light']};}}
    QFrame#panelHeader {{background:{p['Dark']};border:1px solid {p['Light']};}}
    QFrame#panelHeader QLabel {{color:{p['BrightText']};}}
    QWidget#hyperControlPanel,QWidget#defaultAppsTab QToolButton,QListWidget#defaultsAppList,QListWidget#defaultsAppList::item,
    QLabel#diskDetails,QFrame#storageSummary,QFrame#volumeDetails,QLabel#volumeArtwork {{border-radius:1px;}}
    QHeaderView::section,QPushButton#pickerAccept {{background:{casework(p)};color:{p['Text']};{bevel(p)}}}
    QPushButton#pickerAccept:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QToolButton#windowClose,QToolButton#windowMinimize,QToolButton#windowMaximize {{color:{p['Text']};}}
    QFrame#panelHeader QToolButton#windowClose,QFrame#panelHeader QToolButton#windowMinimize,QFrame#panelHeader QToolButton#windowMaximize {{color:{p['BrightText']};}}
    QToolButton#windowClose:hover,QToolButton#windowMinimize:hover,QToolButton#windowMaximize:hover {{color:{p['HighlightedText']};}}
    QFrame#panelHeader QToolButton#windowClose:hover,QFrame#panelHeader QToolButton#windowMinimize:hover,QFrame#panelHeader QToolButton#windowMaximize:hover {{color:{p['HighlightedText']};}}
    QToolButton#windowClose:disabled,QToolButton#windowMinimize:disabled,QToolButton#windowMaximize:disabled,
    QFrame#panelHeader QToolButton#windowClose:disabled,QFrame#panelHeader QToolButton#windowMinimize:disabled,QFrame#panelHeader QToolButton#windowMaximize:disabled {{color:{p['Disabled']};}}
    '''


def waybar_style(p):
    return f'''* {{font-family:"Noto Sans","FiraCode Nerd Font",sans-serif;}}
    tooltip,menu {{background:{p['Window']};color:{p['Text']};border:2px solid {p['Dark']};
        border-top-color:{p['Light']};border-left-color:{p['Light']};border-radius:0;}}
    menuitem:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}'''


def bar_controls(p,root):
    return f'''#custom-launcher {{background-image:url("{root/'assets/platform95-mark.svg'}"),linear-gradient(180deg,{p['Button']},{p['Window']});
        background-repeat:no-repeat;background-position:7px center;border:2px solid {p['Dark']};
        border-top-color:{p['Light']};border-left-color:{p['Light']};border-radius:1px;
        padding:0 12px 0 38px;color:{p['Text']};font-weight:bold;}}
    #custom-launcher:hover {{background-color:{p['Mid']};}}
    #workspaces button,#custom-keys,#new-workspace,#xetal-pins .pin {{background:linear-gradient(180deg,{p['Button']},{p['Window']});
        color:{p['Text']};border:2px solid {p['Dark']};border-top-color:{p['Light']};border-left-color:{p['Light']};border-radius:1px;}}
    #workspaces button {{padding:0 6px;margin:2px 1px;}}
    #workspaces button.active,#xetal-pins .pin.active {{background:{p['Highlight']};color:{p['HighlightedText']};
        border-color:{p['Light']};border-top-color:{p['Dark']};border-left-color:{p['Dark']};box-shadow:none;}}
    #workspaces button.urgent {{background:#903b2b;color:#fff8e9;}}
    #clock {{background:transparent;color:{p['Text']};border-left:1px solid {p['Midlight']};border-radius:0;padding:0 12px;}}
    #audio {{border-right:1px solid {p['Midlight']};border-radius:0;}}
    #custom-updates {{color:{p['Link']};}}
    '''


def notification_style(p):
    return f'''.control-center,.notification {{background:{p['Window']};color:{p['Text']};
        border:2px solid {p['Dark']};border-top-color:{p['Light']};border-left-color:{p['Light']};border-radius:1px;}}
    .notification-content {{background:transparent;color:{p['Text']};padding:12px;}}
    .summary,.widget-title {{color:{p['Text']};font-family:"Noto Sans",sans-serif;font-weight:bold;}}
    .body,.time,.widget-label {{color:{p['PlaceholderText']};}}
    .notification-action,.close-button,.widget-title > button,.widget-buttons-grid > flowbox > flowboxchild > button {{
        background:{p['Button']};color:{p['Text']};border:2px solid {p['Dark']};border-top-color:{p['Light']};border-left-color:{p['Light']};border-radius:1px;}}
    .notification-action:hover,.close-button:hover,.widget-title > button:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    .widget-mpris {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:1px;}}
    .widget-dnd > switch {{background:{p['Base']};border:1px solid {p['Midlight']};border-radius:1px;}}
    .widget-dnd > switch:checked {{background:{p['Highlight']};}}
    scale trough {{background:{p['Base']};border:1px solid {p['Midlight']};border-radius:0;}}
    scale highlight {{background:{p['Highlight']};border-radius:0;}}
    scale slider {{background:{p['Button']};border:1px solid {p['Dark']};border-radius:1px;}}'''


def compositor(p):
    return f'''\n# Platform 95: crisp casework with an antique-gold focus edge.
general:col.active_border = rgb({p['Light'][1:]}) rgb({p['Accent'][1:]}) 135deg
general:col.inactive_border = rgb({p['Midlight'][1:]})
general:border_size = 2
decoration:rounding = 1
'''


def paint_surface(painter,box,colors,radius=1,opacity=100,focused=False):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor,QLinearGradient,QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_surface(p,b,colors,radius,100,focused));return
    painter.save();painter.setClipRect(box,Qt.ClipOperation.IntersectClip)
    fill=QLinearGradient(box.topLeft(),box.bottomLeft())
    fill.setColorAt(0,QColor(colors['Button']));fill.setColorAt(.16,QColor(colors['Window']));fill.setColorAt(1,QColor(colors['Window']))
    painter.fillRect(box,fill)
    # The two opposing edges form real raised casework, even on small tiles.
    for inset,top,bottom in ((.5,'Light','Dark'),(1.5,'Button','Midlight')):
        edge=box.adjusted(inset,inset,-inset,-inset)
        painter.setPen(QPen(QColor(colors[top]),1));painter.drawLine(edge.bottomLeft(),edge.topLeft());painter.drawLine(edge.topLeft(),edge.topRight())
        painter.setPen(QPen(QColor(colors[bottom]),1));painter.drawLine(edge.topRight(),edge.bottomRight());painter.drawLine(edge.bottomRight(),edge.bottomLeft())
    if focused:
        painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(QColor(colors['Accent']),1,Qt.PenStyle.DotLine))
        painter.drawRect(box.adjusted(4,4,-4,-4))
    painter.restore()


def paint_tile(painter,box,colors,opacity=100,selected=False,hovered=False):
    from PyQt6.QtGui import QColor
    paint_surface(painter,box,colors,1,opacity,selected or hovered)
    if selected or hovered:
        painter.save();painter.setOpacity(painter.opacity()*opacity/100)
        wash=QColor(colors['Highlight']);wash.setAlpha(95 if selected else 35)
        painter.fillRect(box.adjusted(3,3,-3,-3),wash);painter.restore()

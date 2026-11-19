"""StarCraft II — machined command panels, cobalt enamel and psionic light."""
from pathlib import Path


def armor(p):
    return f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['Button']},stop:.12 {p['Mid']},stop:.48 {p['Window']},stop:.52 {p['Base']},stop:1 {p['Window']})"


def enamel(p):
    from PyQt6.QtGui import QColor
    top=QColor(p['Highlight']).lighter(112).name()
    return f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {top},stop:.48 {p['Highlight']},stop:1 {p['Highlight']})"


def chrome_style(p):
    return f'''QToolButton {{background:{armor(p)};color:{p['Text']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-bottom-color:{p['Dark']};border-radius:3px;padding:0;}}
    QToolButton:hover,QToolButton:pressed {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QToolButton:focus {{border:2px solid {p['Accent']};}}
    QToolButton:disabled {{color:{p['Disabled']};border-color:{p['Midlight']};}}'''


def qt_style(p):
    from PyQt6.QtGui import QColor
    from designs import qt_style as base
    arrow = Path(__file__).resolve().parent/'assets'/('starcraft-down-light.svg' if QColor(p['Text']).lightnessF() > .5 else 'starcraft-down-dark.svg')
    return base(p)+f'''
    QWidget {{font-family:"Inter";}}
    QMainWindow,QDialog,QMessageBox,QWidget#controlRoot {{background:{p['Window']};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand,QLabel#title,QLabel#dialogTitle {{color:{p['Text']};font-weight:600;}}
    QLabel#eyebrow {{color:{p['Accent']};letter-spacing:2px;}}
    QPushButton,QToolButton {{background:{armor(p)};color:{p['ButtonText']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-bottom-color:{p['Dark']};border-radius:4px;padding:6px 11px;}}
    QPushButton:hover,QToolButton:hover {{background:{p['Mid']};border-color:{p['Accent']};}}
    QPushButton:pressed,QToolButton:pressed,QPushButton:checked,QToolButton:checked,QPushButton#primary {{background:{enamel(p)};color:{p['HighlightedText']};border-color:{p['Accent']};border-top-color:{p['Light']};}}
    QPushButton#primary:hover {{background:{p['Highlight']};color:{p['HighlightedText']};border:1px solid {p['Accent']};}}
    QPushButton:focus,QToolButton:focus {{border:2px solid {p['Accent']};}}
    QPushButton:disabled,QToolButton:disabled {{background:{p['Window']};color:{p['Disabled']};border-color:{p['Midlight']};}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-top-color:{p['Dark']};border-bottom-color:{p['Light']};border-radius:3px;padding:6px 8px;}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QTextEdit:focus,QPlainTextEdit:focus {{border-color:{p['Accent']};}}
    QLineEdit:disabled,QComboBox:disabled,QSpinBox:disabled {{color:{p['Disabled']};background:{p['Window']};}}
    QComboBox QAbstractItemView {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};}}
    QComboBox::down-arrow {{image:url("{arrow}");width:12px;height:8px;}}
    QGroupBox,QFrame#modernCard,QFrame#audioColumn,QFrame#presetCard,QFrame#changes {{background:{p['AlternateBase']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:5px;}}
    QGroupBox::title {{color:{p['Text']};font-weight:600;}}
    QWidget#modernRail {{background:{armor(p)};border:1px solid {p['Midlight']};border-bottom:2px solid {p['Accent']};border-radius:4px;}}
    QToolButton#railButton,QPushButton#railButton,QPushButton#launcherNav {{background:transparent;border-color:transparent;border-radius:4px;}}
    QToolButton#railButton:checked,QPushButton#railButton:checked,QPushButton#launcherNav:checked {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QTabWidget::pane {{border:1px solid {p['Midlight']};background:transparent;}}
    QTabBar::tab {{background:{armor(p)};color:{p['Text']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-top-left-radius:5px;border-top-right-radius:5px;padding:7px 14px;margin:2px 2px 0 0;}}
    QTabBar::tab:selected {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QTabBar::tab:hover {{border-color:{p['Accent']};}}
    QTreeView,QListView,QTableView {{background:{p['Base']};alternate-background-color:{p['AlternateBase']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:4px;}}
    QAbstractItemView::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QHeaderView::section,QTableCornerButton::section {{background:{armor(p)};color:{p['Text']};border:0;border-bottom:1px solid {p['Midlight']};padding:7px;}}
    QMenuBar {{background:{p['Window']};color:{p['Text']};}}
    QMenu,QToolTip {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};border-radius:4px;padding:5px;}}
    QMenu::item {{padding:6px 28px;border-radius:3px;}}
    QMenu::item:selected,QMenuBar::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QMenu::item:disabled {{color:{p['Disabled']};}}
    QCheckBox::indicator,QRadioButton::indicator {{background:{p['Base']};border:1px solid {p['Midlight']};}}
    QCheckBox::indicator:checked,QRadioButton::indicator:checked {{background:{p['Highlight']};border-color:{p['Accent']};}}
    QRadioButton::indicator {{width:12px;height:12px;border:2px solid {p['Midlight']};border-radius:8px;}}
    QSlider::groove:horizontal {{background:{p['Base']};height:5px;border:1px solid {p['Midlight']};border-radius:2px;}}
    QSlider::sub-page:horizontal {{background:{p['Accent']};}}
    QSlider::handle:horizontal {{background:{p['Highlight']};border:1px solid {p['Accent']};width:14px;margin:-5px 0;border-radius:3px;}}
    QProgressBar {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:3px;}}
    QProgressBar::chunk {{background:{p['Accent']};border-radius:2px;}}
    QScrollBar::handle:vertical,QScrollBar::handle:horizontal {{background:{p['Midlight']};border-radius:2px;}}
    '''


def files_style(p):
    return f'''QMainWindow,QWidget#filesBody,QWidget#hyperControlPanel,QToolBar,QFrame#addressRow {{background:{p['Window']};}}
    QToolBar#filesToolbar {{background:{armor(p)};border-top:1px solid {p['Light']};border-bottom:1px solid {p['Accent']};}}
    QTreeWidget#places {{background:{p['Base']};border:1px solid {p['Midlight']};border-radius:4px;}}
    QTreeWidget#places::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QFrame#panelHeader {{background:{armor(p)};border:0;border-top:1px solid {p['Light']};border-bottom:1px solid {p['Accent']};}}
    QFrame#panelHeader QLabel {{color:{p['Text']};}}
    QFrame#pickerActions,QStatusBar {{background:{p['Window']};border-top:1px solid {p['Midlight']};}}
    QFrame#defaultsHero,QFrame#ramMetric {{background:{p['AlternateBase']};border:1px solid {p['Midlight']};border-radius:5px;}}
    QToolButton#windowClose,QToolButton#windowMinimize,QToolButton#windowMaximize {{color:{p['Text']};}}
    QToolButton#windowClose:hover,QToolButton#windowMinimize:hover,QToolButton#windowMaximize:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QToolButton#windowClose:disabled,QToolButton#windowMinimize:disabled,QToolButton#windowMaximize:disabled {{color:{p['Disabled']};}}'''


def waybar_style(p):
    return f'''* {{font-family:"Inter","FiraCode Nerd Font",sans-serif;}}
    tooltip,menu {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};border-radius:4px;}}
    menuitem:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}'''


def bar_controls(p,root):
    return f'''#custom-launcher {{background-image:url("{root/'assets/starcraft-mark.svg'}");background-repeat:no-repeat;background-position:8px center;padding:0 12px 0 40px;color:{p['Text']};border:0;border-radius:4px;}}
    #workspaces button,#custom-keys,#new-workspace,#xetal-pins .pin {{background:linear-gradient(180deg,{p['Button']},{p['Base']});color:{p['Text']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:4px;}}
    #workspaces button.active,#xetal-pins .pin.active {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};box-shadow:inset 0 0 0 1px alpha({p['Accent']},.4),0 0 5px alpha({p['Accent']},.45);}}
    #workspaces button.urgent {{background:{p['Accent']};color:{p['Base']};}}
    #clock {{background:transparent;color:{p['Text']};border-left:1px solid {p['Midlight']};border-radius:0;padding:0 12px;}}
    #custom-updates {{color:{p['Link']};}}
    #custom-launcher:hover,#custom-keys:hover,#xetal-pins .pin:hover,#new-workspace:hover {{border-color:{p['Accent']};background-color:{p['Mid']};}}'''


def notification_style(p):
    return f'''.control-center,.notification {{background:linear-gradient(170deg,{p['Button']},{p['Window']} 18%,{p['Base']});color:{p['Text']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-bottom:2px solid {p['Accent']};border-radius:5px;}}
    .notification-content {{background:transparent;padding:13px;color:{p['Text']};}}
    .summary,.widget-title {{color:{p['Text']};font-family:"Inter",sans-serif;font-weight:600;}}
    .body,.time,.widget-label {{color:{p['PlaceholderText']};}}
    .notification-action,.close-button,.widget-title > button,.widget-buttons-grid > flowbox > flowboxchild > button {{background:{p['Button']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:4px;}}
    .notification-action:hover,.close-button:hover,.widget-title > button:hover {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    .widget-dnd,.widget-mpris {{background:{p['AlternateBase']};color:{p['Text']};border-radius:4px;padding:8px;}}
    .widget-dnd > switch:checked {{background:{p['Highlight']};}}
    .widget-mpris button {{color:{p['Text']};}}'''


def compositor(p):
    return f'''# StarCraft II: cyan focus, silver armor and a restrained engine glow.
general:col.active_border = rgb({p['Accent'][1:]}) rgb({p['Light'][1:]}) rgb({p['Highlight'][1:]}) 135deg
general:col.inactive_border = rgba({p['Midlight'][1:]}cc)
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
decoration:blur:vibrancy = 0.03
'''


def _contour(box,cut=7):
    from PyQt6.QtGui import QPainterPath
    c=min(cut,box.height()/4,box.width()/4);l,t,r,b=box.left(),box.top(),box.right(),box.bottom()
    path=QPainterPath();path.moveTo(l+c,t)
    for x,y in ((r-c,t),(r,t+c),(r,b-c),(r-c,b),(l+c,b),(l,b-c),(l,t+c)):
        path.lineTo(x,y)
    path.closeSubpath();return path


def paint_surface(painter,box,colors,radius=5,opacity=100,focused=False):
    """Clipped armor corners, double silver bevels, rivets and inset cyan conduits."""
    from PyQt6.QtCore import Qt,QPointF
    from PyQt6.QtGui import QColor,QLinearGradient,QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_surface(p,b,colors,radius,100,focused));return
    painter.save();path=_contour(box)
    fill=QLinearGradient(box.topLeft(),box.bottomLeft())
    for stop,key in ((0,'Button'),(.11,'Window'),(.55,'Base'),(1,'Window')):fill.setColorAt(stop,QColor(colors[key]))
    painter.fillPath(path,fill);painter.setClipPath(path,Qt.ClipOperation.IntersectClip)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(colors['Accent'] if focused else colors['Midlight']),1.5));painter.drawPath(path)
    painter.setPen(QPen(QColor(colors['Light']),.8));painter.drawPath(_contour(box.adjusted(2,2,-2,-2),6))
    painter.setPen(QPen(QColor(colors['Dark']),1));painter.drawPath(_contour(box.adjusted(4,4,-4,-4),5))
    # Fittings occupy the outer 6 px, leaving labels and hit targets clear.
    for x in (box.left()+5,box.right()-5):
        for y in (box.top()+12,box.bottom()-12):
            painter.setBrush(QColor(colors['Midlight']));painter.setPen(QPen(QColor(colors['Dark']),.7));painter.drawEllipse(QPointF(x,y),1.3,1.3)
    for y in (box.top()+2,box.bottom()-2):
        start=box.center().x()-min(30,box.width()/6);end=box.center().x()+min(30,box.width()/6)
        halo=QColor(colors['Accent']);halo.setAlpha(60)
        painter.setPen(QPen(halo,5));painter.drawLine(QPointF(start,y),QPointF(end,y))
        painter.setPen(QPen(QColor(colors['Accent']),1.6));painter.drawLine(QPointF(start+4,y),QPointF(end-4,y))
    painter.restore()


def paint_tile(painter,box,colors,opacity=100,selected=False,hovered=False):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor,QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_tile(p,b,colors,100,selected,hovered));return
    paint_surface(painter,box,colors,5,100,selected or hovered)
    if selected or hovered:
        painter.save();wash=QColor(colors['Highlight']);wash.setAlpha(240 if selected else 60)
        path=_contour(box.adjusted(3,3,-3,-3),4)
        painter.fillPath(path,wash);painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(QColor(colors['Accent']),1));painter.drawPath(path);painter.restore()

"""Killer Instinct 1994: four coordinated materials with shared accessible controls."""
from pathlib import Path


RADII = {'killerinstinct':3, 'kitemple':2, 'kiprimal':8, 'kifireice':2}


def armor(p,style='killerinstinct'):
    if style=='kitemple':
        return f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['Mid']},stop:.18 {p['Button']},stop:.8 {p['Window']},stop:1 {p['Base']})"
    if style=='kiprimal':
        return f"qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {p['Button']},stop:.4 {p['Window']},stop:1 {p['Base']})"
    if style=='kifireice':
        return f"qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {p['Mid']},stop:.48 {p['Window']},stop:.52 {p['Base']},stop:1 {p['AlternateBase']})"
    return f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {p['Button']},stop:.16 {p['Mid']},stop:.47 {p['Window']},stop:.51 {p['Base']},stop:1 {p['Window']})"


def enamel(p, style='killerinstinct'):
    from PyQt6.QtGui import QColor
    top=QColor(p['Highlight']).lighter(112).name()
    return f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {top},stop:.48 {p['Highlight']},stop:1 {p['Highlight']})"


def chrome_style(p, style='killerinstinct'):
    return f'''QToolButton {{background:{armor(p,style)};color:{p['Text']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-bottom-color:{p['Dark']};border-radius:{RADII[style]}px;padding:0;}}
    QToolButton:hover,QToolButton:pressed {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QToolButton:focus {{border:2px solid {p['Accent']};}}
    QToolButton:disabled {{color:{p['Disabled']};border-color:{p['Midlight']};}}'''


def qt_style(p, style='killerinstinct'):
    from PyQt6.QtGui import QColor
    from designs import qt_style as base
    arrow = Path(__file__).resolve().parent/'assets'/('ki-down-light.svg' if QColor(p['Text']).lightnessF() > .5 else 'ki-down-dark.svg')
    return base(p)+f'''
    QWidget {{font-family:"Inter";}}
    QMainWindow,QDialog,QMessageBox,QWidget#controlRoot {{background:{p['Window']};}}
    QMainWindow#fusionSettingsWindow {{background:transparent;}}
    QLabel#brand,QLabel#title,QLabel#dialogTitle {{color:{p['Text']};font-weight:600;}}
    QLabel#eyebrow {{color:{p['Accent']};letter-spacing:2px;}}
    QPushButton,QToolButton {{background:{armor(p,style)};color:{p['ButtonText']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-bottom-color:{p['Dark']};border-radius:{RADII[style]}px;padding:6px 11px;}}
    QPushButton:hover,QToolButton:hover {{background:{p['Mid']};border-color:{p['Accent']};}}
    QPushButton:pressed,QToolButton:pressed,QPushButton:checked,QToolButton:checked,QPushButton#primary {{background:{enamel(p,style)};color:{p['HighlightedText']};border-color:{p['Accent']};border-top-color:{p['Light']};}}
    QPushButton#primary:hover {{background:{p['Highlight']};color:{p['HighlightedText']};border:1px solid {p['Accent']};}}
    QPushButton:focus,QToolButton:focus {{border:2px solid {p['Accent']};}}
    QPushButton:disabled,QToolButton:disabled {{background:{p['Window']};color:{p['Disabled']};border-color:{p['Midlight']};}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-top-color:{p['Dark']};border-bottom-color:{p['Light']};border-radius:{RADII[style]}px;padding:6px 8px;}}
    QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QTextEdit:focus,QPlainTextEdit:focus {{border-color:{p['Accent']};}}
    QLineEdit:disabled,QComboBox:disabled,QSpinBox:disabled {{color:{p['Disabled']};background:{p['Window']};}}
    QComboBox QAbstractItemView {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};}}
    QComboBox::down-arrow {{image:url("{arrow}");width:12px;height:8px;}}
    QGroupBox,QFrame#modernCard,QFrame#audioColumn,QFrame#presetCard,QFrame#changes {{background:{p['AlternateBase']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:{RADII[style]}px;}}
    QGroupBox::title {{color:{p['Text']};font-weight:600;}}
    QWidget#modernRail {{background:{armor(p,style)};border:1px solid {p['Midlight']};border-bottom:2px solid {p['Link']};border-radius:{RADII[style]}px;}}
    QToolButton#railButton,QPushButton#railButton,QPushButton#launcherNav {{background:transparent;border-color:transparent;border-radius:{RADII[style]}px;}}
    QToolButton#railButton:checked,QPushButton#railButton:checked,QPushButton#launcherNav:checked {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QTabWidget::pane {{border:1px solid {p['Midlight']};background:transparent;}}
    QTabBar::tab {{background:{armor(p,style)};color:{p['Text']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-top-left-radius:{RADII[style]}px;border-top-right-radius:{RADII[style]}px;padding:7px 14px;margin:2px 2px 0 0;}}
    QTabBar::tab:selected {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    QTabBar::tab:hover {{border-color:{p['Accent']};}}
    QTreeView,QListView,QTableView {{background:{p['Base']};alternate-background-color:{p['AlternateBase']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:{RADII[style]}px;}}
    QAbstractItemView::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QHeaderView::section,QTableCornerButton::section {{background:{armor(p,style)};color:{p['Text']};border:0;border-bottom:1px solid {p['Midlight']};padding:7px;}}
    QMenuBar {{background:{p['Window']};color:{p['Text']};}}
    QMenu,QToolTip {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};border-radius:{RADII[style]}px;padding:5px;}}
    QMenu::item {{padding:6px 28px;border-radius:{RADII[style]}px;}}
    QMenu::item:selected,QMenuBar::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QMenu::item:disabled {{color:{p['Disabled']};}}
    QCheckBox::indicator,QRadioButton::indicator {{background:{p['Base']};border:1px solid {p['Midlight']};}}
    QCheckBox::indicator:checked,QRadioButton::indicator:checked {{background:{p['Highlight']};border-color:{p['Accent']};}}
    QRadioButton::indicator {{width:12px;height:12px;border:2px solid {p['Midlight']};border-radius:8px;}}
    QSlider::groove:horizontal {{background:{p['Base']};height:5px;border:1px solid {p['Midlight']};border-radius:2px;}}
    QSlider::sub-page:horizontal {{background:{p['Accent']};}}
    QSlider::handle:horizontal {{background:{p['Highlight']};border:1px solid {p['Accent']};width:14px;margin:-5px 0;border-radius:{RADII[style]}px;}}
    QProgressBar {{background:{p['Base']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:{RADII[style]}px;}}
    QProgressBar::chunk {{background:{p['Accent']};border-radius:2px;}}
    QScrollBar::handle:vertical,QScrollBar::handle:horizontal {{background:{p['Midlight']};border-radius:2px;}}
    '''


def files_style(p, style='killerinstinct'):
    return f'''QMainWindow,QWidget#filesBody,QWidget#hyperControlPanel,QToolBar,QFrame#addressRow {{background:{p['Window']};}}
    QToolBar#filesToolbar {{background:{armor(p,style)};border-top:1px solid {p['Light']};border-bottom:1px solid {p['Accent']};}}
    QTreeWidget#places {{background:{p['Base']};border:1px solid {p['Midlight']};border-radius:{RADII[style]}px;}}
    QTreeWidget#places::item:selected {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QFrame#panelHeader {{background:{armor(p,style)};border:0;border-top:1px solid {p['Light']};border-bottom:1px solid {p['Accent']};}}
    QFrame#panelHeader QLabel {{color:{p['Text']};}}
    QFrame#pickerActions,QStatusBar {{background:{p['Window']};border-top:1px solid {p['Midlight']};}}
    QFrame#defaultsHero,QFrame#ramMetric {{background:{p['AlternateBase']};border:1px solid {p['Midlight']};border-radius:{RADII[style]}px;}}
    QToolButton#windowClose,QToolButton#windowMinimize,QToolButton#windowMaximize {{color:{p['Text']};}}
    QToolButton#windowClose:hover,QToolButton#windowMinimize:hover,QToolButton#windowMaximize:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}
    QToolButton#windowClose:disabled,QToolButton#windowMinimize:disabled,QToolButton#windowMaximize:disabled {{color:{p['Disabled']};}}'''


def waybar_style(p, style='killerinstinct'):
    return f'''* {{font-family:"Inter","FiraCode Nerd Font",sans-serif;}}
    tooltip,menu {{background:{p['Window']};color:{p['Text']};border:1px solid {p['Accent']};border-radius:{RADII[style]}px;}}
    menuitem:hover {{background:{p['Highlight']};color:{p['HighlightedText']};}}'''


def bar_controls(p,root,style='killerinstinct'):
    return f'''#custom-launcher {{background-image:url("{root/'assets'/f'{style}-mark.svg'}");background-repeat:no-repeat;background-position:8px center;padding:0 12px 0 40px;color:{p['Text']};border:0;border-radius:{RADII[style]}px;}}
    #workspaces button,#custom-keys,#new-workspace,#xetal-pins .pin {{background:linear-gradient(180deg,{p['Button']},{p['Base']});color:{p['Text']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:{RADII[style]}px;}}
    #workspaces button.active,#xetal-pins .pin.active {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};box-shadow:inset 0 0 0 1px alpha({p['Accent']},.4),0 0 5px alpha({p['Accent']},.45);}}
    #workspaces button.urgent {{background:{p['Accent']};color:{p['Base']};}}
    #clock {{background:transparent;color:{p['Text']};border-left:1px solid {p['Midlight']};border-radius:0;padding:0 12px;}}
    #custom-updates {{color:{p['Link']};}}
    #custom-launcher:hover,#custom-keys:hover,#xetal-pins .pin:hover,#new-workspace:hover {{border-color:{p['Accent']};background-color:{p['Mid']};}}'''


def notification_style(p, style='killerinstinct'):
    return f'''.control-center,.notification {{background:linear-gradient(170deg,{p['Button']},{p['Window']} 18%,{p['Base']});color:{p['Text']};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-bottom:2px solid {p['Link']};border-radius:{RADII[style]}px;}}
    .notification-content {{background:transparent;padding:13px;color:{p['Text']};}}
    .summary,.widget-title {{color:{p['Text']};font-family:"Inter",sans-serif;font-weight:600;}}
    .body,.time,.widget-label {{color:{p['PlaceholderText']};}}
    .notification-action,.close-button,.widget-title > button,.widget-buttons-grid > flowbox > flowboxchild > button {{background:{p['Button']};color:{p['Text']};border:1px solid {p['Midlight']};border-radius:{RADII[style]}px;}}
    .notification-action:hover,.close-button:hover,.widget-title > button:hover {{background:{p['Highlight']};color:{p['HighlightedText']};border-color:{p['Accent']};}}
    .widget-dnd,.widget-mpris {{background:{p['AlternateBase']};color:{p['Text']};border-radius:{RADII[style]}px;padding:8px;}}
    .widget-dnd > switch:checked {{background:{p['Highlight']};}}
    .widget-mpris button {{color:{p['Text']};}}'''


def compositor(p, style='killerinstinct'):
    return f'''# Killer Instinct 1994: selected material, independent of saved effect preferences.
general:col.active_border = rgb({p['Accent'][1:]}) rgb({p['Light'][1:]}) rgb({p['Link'][1:]}) 135deg
general:col.inactive_border = rgba({p['Midlight'][1:]}cc)
general:border_size = 2
general:gaps_in = 5
general:gaps_out = 8
decoration:rounding = {RADII[style]}
decoration:shadow:enabled = true
decoration:shadow:range = 22
decoration:shadow:render_power = 3
decoration:shadow:color = rgba({p['Shadow'][1:]}bb)
decoration:blur:enabled = true
decoration:blur:size = 3
decoration:blur:passes = 2
decoration:blur:vibrancy = 0.03
'''


def bar_frame(p,style='killerinstinct'):
    """GTK counterparts of the four painted panel materials."""
    common=f'border:1px solid {p["Midlight"]};border-radius:{RADII[style]}px;'
    if style=='kitemple':
        return common+f'background:linear-gradient(180deg,{p["Mid"]},{p["Window"]} 18%,{p["Base"]});border-top-color:{p["Light"]};border-bottom-color:{p["Light"]};box-shadow:inset 0 0 0 2px {p["Base"]},inset 0 0 0 3px alpha({p["Light"]},.32);'
    if style=='kiprimal':
        return common+f'background:linear-gradient(145deg,{p["Button"]},{p["Window"]} 25%,{p["Base"]});border-top-color:{p["Light"]};border-bottom:2px solid {p["Accent"]};box-shadow:inset 0 2px alpha({p["Text"]},.08);'
    if style=='kifireice':
        return common+f'background:linear-gradient(105deg,{p["Mid"]},{p["Window"]} 40%,{p["Base"]} 60%,{p["AlternateBase"]});border-top-color:{p["Accent"]};border-bottom-color:{p["Link"]};box-shadow:inset 0 0 0 2px {p["Base"]};'
    return common+f'background:linear-gradient(180deg,{p["Button"]},{p["Window"]} 45%,{p["Base"]} 51%,{p["Window"]});border-top-color:{p["Light"]};border-bottom-color:{p["Accent"]};box-shadow:inset 0 0 0 2px {p["Base"]},inset 0 0 0 3px alpha({p["Light"]},.25);'


def contour(box,style):
    from PyQt6.QtGui import QPainterPath
    path=QPainterPath()
    if style in ('kitemple','kiprimal'):
        path.addRoundedRect(box,RADII[style],RADII[style]);return path
    c=min(6 if style=='killerinstinct' else 9,box.height()/4,box.width()/4)
    l,t,r,b=box.left(),box.top(),box.right(),box.bottom();path.moveTo(l+c,t)
    for x,y in ((r-c,t),(r,t+c),(r,b-c),(r-c,b),(l+c,b),(l,b-c),(l,t+c)):path.lineTo(x,y)
    path.closeSubpath();return path


def paint_surface(painter,box,colors,radius=3,opacity=100,focused=False,style='killerinstinct'):
    """Chrome cabinet, jade altar, weathered stone or split thermal steel."""
    from PyQt6.QtCore import Qt,QPointF,QRectF
    from PyQt6.QtGui import QColor,QLinearGradient,QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_surface(p,b,colors,radius,100,focused,style));return
    p=painter;c=lambda role:QColor(colors[role]);p.save();path=contour(box,style)
    fill=QLinearGradient(box.topLeft(),box.bottomRight() if style in ('kiprimal','kifireice') else box.bottomLeft())
    stops={'killerinstinct':((0,'Button'),(.16,'Mid'),(.46,'Window'),(.51,'Base'),(1,'Window')),'kitemple':((0,'Mid'),(.12,'Button'),(.3,'Window'),(1,'Base')),'kiprimal':((0,'Button'),(.28,'Window'),(1,'Base')),'kifireice':((0,'Mid'),(.45,'Window'),(.55,'Base'),(1,'AlternateBase'))}[style]
    for stop,role in stops:fill.setColorAt(stop,c(role))
    p.fillPath(path,fill);p.setClipPath(path,Qt.ClipOperation.IntersectClip);p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(c('Accent' if focused else 'Midlight'),1.4));p.drawPath(path)
    l,t,r,b=box.left(),box.top(),box.right(),box.bottom()
    def line(x1,y1,x2,y2,role='Light',width=1):p.setPen(QPen(c(role),width));p.drawLine(QPointF(x1,y1),QPointF(x2,y2))
    if style=='killerinstinct':
        p.setPen(QPen(c('Light'),.8));p.drawPath(contour(box.adjusted(2,2,-2,-2),style))
        p.setPen(QPen(c('Dark'),1));p.drawPath(contour(box.adjusted(4,4,-4,-4),style))
        grain=c('Light');grain.setAlpha(14);p.setPen(QPen(grain,.5))
        for y in range(int(t)+6,min(int(b)-5,int(t)+26),3):p.drawLine(QPointF(l+9,y),QPointF(r-9,y))
        for x in (l+12,r-12):
            line(x-3,t+3,x+3,t+3,'LinkVisited',1.7)
        line(l+14,b-2,r-14,b-2,'Accent',1)
    elif style=='kitemple':
        p.setPen(QPen(c('Light'),1));p.drawRoundedRect(box.adjusted(3,3,-3,-3),1,1)
        p.setPen(QPen(c('Dark'),1));p.drawRoundedRect(box.adjusted(5,5,-5,-5),1,1)
        for x,dx in ((l+6,1),(r-6,-1)):
            for y,dy in ((t+6,1),(b-6,-1)):
                line(x,y,x+dx*8,y);line(x,y,x,y+dy*8)
                line(x+dx*3,y+dy*3,x+dx*6,y+dy*3,'Accent',.8)
        line(l+20,b-3,r-20,b-3,'Light',.6)
    elif style=='kiprimal':
        p.setPen(QPen(c('Light'),.7));p.drawRoundedRect(box.adjusted(2,2,-2,-2),6,6)
        # Deterministic etched stone confined to the rim, never through labels.
        grain=c('Light');grain.setAlpha(40);p.setPen(QPen(grain,.7))
        for x in range(int(l)+12,int(r)-10,13):p.drawPoint(QPointF(x,t+4+(x%3)))
        for x,dx in ((l+15,1),(r-15,-1)):
            for j in range(3):line(x+dx*j*4,b-4,x+dx*(j*4+3),b-10,'Accent',.9)
    else:
        p.setPen(QPen(c('Light'),.8));p.drawPath(contour(box.adjusted(3,3,-3,-3),style))
        mid=box.center().x()
        for y in (t+2,b-2):
            line(l+12,y,mid-10,y,'Accent',1.7);line(mid+10,y,r-12,y,'Link',1.7)
        for x,dx,role in ((l+6,1,'Accent'),(r-6,-1,'Link')):
            line(x,t+12,x+dx*4,t+16,role);line(x,b-12,x+dx*4,b-16,role)
    p.restore()


def paint_tile(painter,box,colors,opacity=100,selected=False,hovered=False,style='killerinstinct'):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor,QPen
    if opacity<100:
        from candycloud import faded_layer
        faded_layer(painter,box,opacity,lambda p,b:paint_tile(p,b,colors,100,selected,hovered,style));return
    paint_surface(painter,box,colors,RADII[style],100,selected or hovered,style)
    if selected or hovered:
        painter.save();wash=QColor(colors['Highlight']);wash.setAlpha(245 if selected else 65)
        path=contour(box.adjusted(4,4,-4,-4),style);painter.fillPath(path,wash)
        painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(QColor(colors['Accent']),1));painter.drawPath(path);painter.restore()

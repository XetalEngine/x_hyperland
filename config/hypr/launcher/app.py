#!/usr/bin/env python3
"""Hyprland application menu. All menu preferences stay in this directory."""
from pathlib import Path
import argparse
import copy
import datetime
import json
import os
import subprocess
import sys
import time

from PyQt6.QtCore import Qt, QSize, QRectF, QTimer, QEvent, QEasingCurve, QPropertyAnimation, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPixmap, QLinearGradient, QPen, QIcon, QFont, QKeySequence, QShortcut
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QListView, QStyledItemDelegate, QStyle, QMenu,
    QGraphicsOpacityEffect, QMessageBox, QDialog, QSizeGrip, QStackedWidget, QInputDialog,
    QScrollArea, QLayout)
import catalog
import shortcuts
import pins
import geometry
import hotkeys
import favorite_layout
import capture_guard
import bar_toggle
from outside_click import CLICK_EVENT, check_pointer
from favorite_board import Board
from hotkey_dialog import HotkeyDialog
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'theme'))
import runtime as theme_runtime
from editor import ShortcutEditor
from window_chrome import close_button
from identity import Avatar, ProfileCard, launcher_background_path
from launcher_surfaces import paint_tile

STYLE = '''
QWidget { color: #e6edf8; font-family: "Noto Sans"; font-size: 13px; background: transparent; }
QLabel#brand { font-size: 24px; font-weight: 700; letter-spacing: 2px; }
QLabel#eyebrow { color: #68dece; font-size: 10px; font-weight: 600; letter-spacing: 2px; }
QLabel#muted { color: #93a4bb; font-size: 12px; }
QLabel#section { font-size: 17px; font-weight: 600; }
QLineEdit { background: rgba(9,15,27,180); border: 1px solid #34475e; border-radius: 10px;
 padding: 14px 16px; font-size: 16px; selection-background-color: #396c78; }
QLineEdit:focus { border: 1px solid #70dcca; background: rgba(12,22,35,220); }
QLineEdit#appSearch { padding: 7px 14px; font-size: 14px; }
QPushButton { border: 0; border-radius: 8px; text-align: left; padding: 11px 12px; color: #aab9ce; }
QPushButton:hover { background: rgba(105,152,181,35); color: #ffffff; }
QPushButton:checked { background: rgba(77,187,173,35); color: #83ead8; }
QListWidget { border: none; outline: 0; background: transparent; }
QScrollBar:vertical { width: 5px; background: transparent; margin: 4px 0; }
QScrollBar::handle:vertical { background: #41566e; border-radius: 2px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QMenu { background: #192435; border: 1px solid #42576e; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 9px 32px; border-radius: 4px; }
QMenu::item:selected { background: #2a4a55; }
QMenu::item:disabled { color: #71859b; }
QMenu::separator { height: 1px; background: #34485c; margin: 6px 10px; }
QDialog, QMessageBox { background: #14202f; color: #e6edf8; }
'''


def label(text, name=''):
    w = QLabel(text)
    w.setObjectName(name)
    return w


def launch(argv):
    subprocess.Popen([str(a) for a in argv], start_new_session=True, env=theme_runtime.environment(),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def leave_dashboard():
    shortcuts.leave_dashboard()


def icon_for(app):
    icon = app.get_icon()
    if icon:
        if hasattr(icon, 'get_file'):
            return QIcon(icon.get_file().get_path())
        if hasattr(icon, 'get_names'):
            for name in icon.get_names():
                candidate = QIcon.fromTheme(name)
                if not candidate.isNull():
                    return candidate
    return QIcon.fromTheme('application-x-executable')


class Tiles(QStyledItemDelegate):
    def __init__(self, parent):
        super().__init__(parent)
        self.hover = -1
        self.amount = 0.0
        self.animation = QPropertyAnimation(self, b'glow')
        self.animation.setDuration(160)

    @pyqtProperty(float)
    def glow(self):
        return self.amount

    @glow.setter
    def glow(self, value):
        self.amount = value
        self.parent().viewport().update()

    def entered(self, item):
        self.hover = self.parent().row(item)
        self.animation.stop()
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.start()

    def paint(self, painter, option, index):
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        self.draw(painter, option.rect, index.data(Qt.ItemDataRole.DecorationRole),
                  index.data(Qt.ItemDataRole.DisplayRole), index.data(hotkeys.ROLE),
                  bool(option.state & QStyle.StateFlag.State_Selected),
                  self.amount if hovered and index.row() == self.hover else 0)

    @staticmethod
    def draw(painter, rect, icon, name, bindings, selected=False, opacity=0, small=False):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(rect.adjusted(5, 4, -5, -4))
        style=theme_runtime.design();modern=style=='modern';colors=theme_runtime.colors()
        paint_tile(painter,box,colors,style,theme_runtime.mode(),theme_runtime.launcher_surfaces()[style]['tile_opacity'],selected,opacity)
        if small:
            size = 27 + round(opacity * 2)
            icon.paint(painter, round(box.center().x() - size / 2), round(box.center().y() - size / 2), size, size)
            painter.restore()
            return
        size = 38 + round(opacity * 3)
        icon.paint(painter, int(box.center().x() - size / 2), int(box.top() + 9 - opacity * 2), size, size)
        painter.setPen(QColor(theme_runtime.colors()['Text']))
        painter.setFont(QFont('Noto Sans', 9))
        text_box = QRectF(box.left() + 7, box.top() + 51, box.width() - 14, 31)
        if len(name) > 30:
            name = name[:28] + '…'
        painter.drawText(text_box, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, name)
        if bindings is not None:
            text=bindings[0]+(f'  +{len(bindings)-1}' if len(bindings)>1 else '') if bindings else 'No hotkey'
            painter.setFont(QFont('Noto Sans',8))
            text=painter.fontMetrics().elidedText(text,Qt.TextElideMode.ElideRight,int(box.width()-20))
            badge=QRectF(box.left()+8,box.top()+85,box.width()-16,16)
            light=theme_runtime.mode()=='light'
            painter.setBrush(QColor(colors['Button'] if modern else '#cce6e5' if light else '#233c48') if bindings else Qt.BrushStyle.NoBrush)
            painter.setPen(Qt.PenStyle.NoPen);painter.drawRoundedRect(badge,5,5)
            painter.setPen(QColor(colors['Accent'] if bindings else colors['PlaceholderText']) if modern else QColor(('#236b66' if light else '#91e2d8') if bindings else ('#516579' if light else '#8c9fb4')))
            painter.drawText(badge,Qt.AlignmentFlag.AlignCenter,text)
        painter.restore()

    def sizeHint(self, option, index):
        return self.parent().gridSize()


class LaunchGrid(QListWidget):
    clickedApp = pyqtSignal(QListWidgetItem, bool)

    def mouseReleaseEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and item:
            self.clickedApp.emit(item, bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier))


class Menu(QWidget):
    def __init__(self, preview=False):
        super().__init__(None, Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle('Xetal applications')
        self.setMinimumSize(*geometry.MINIMUM)
        self.resize(*(geometry.DEFAULT if preview else geometry.size()))
        self.setMouseTracking(True)
        self.preview = preview
        self.size_grip = QSizeGrip(self)
        self.size_grip.setToolTip('Drag to resize the Apps menu')
        self.size_grip.setStyleSheet('background: transparent;')
        self.interaction_depth = 0
        self.started = time.monotonic()
        self.pointer_generation = 0
        self.pending_outside_click = False
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.close_if_outside)
        self.apps = catalog.applications()
        self.pinned = catalog.favorites()
        self.hotkeys=hotkeys.ShortcutIndex(self)
        self.layout_store = favorite_layout.Store()
        self.favorite_layout = {'version': 1, 'groups': []}
        self.layout_token = None
        self.layout_error = ''
        self.page = 'Favorites'
        self.filter_category = ''
        outer = QHBoxLayout(self);self.outer=outer
        outer.setContentsMargins(24, 26, 24, 20)
        outer.setSpacing(20)
        sidebar_widget = QWidget()
        sidebar_widget.setFixedWidth(185)
        sidebar = QVBoxLayout(sidebar_widget)
        sidebar.setContentsMargins(0, 0, 0, 0)
        sidebar.setSpacing(6)
        self.raw_header=QWidget();raw_row=QHBoxLayout(self.raw_header);raw_row.setContentsMargins(0,0,0,0);raw_row.setSpacing(10)
        self.raw_avatar=Avatar(50);raw_row.addWidget(self.raw_avatar)
        self.raw_avatar.clicked.connect(lambda:self.run_command([catalog.ROOT/'scripts/control-center.sh','--tab','theme']))
        raw_titles=QVBoxLayout();raw_titles.setSpacing(5)
        self.raw_brand=label('XETAL', 'brand');self.raw_brand.setStyleSheet('font-size:19px; letter-spacing:3px;');raw_titles.addWidget(self.raw_brand)
        self.raw_eyebrow=label('YOUR WORKSPACE', 'eyebrow');self.raw_eyebrow.setStyleSheet('font-size:8px; letter-spacing:1px;');raw_titles.addWidget(self.raw_eyebrow)
        raw_row.addLayout(raw_titles,1);sidebar.addWidget(self.raw_header)
        self.profile=ProfileCard(compact=True,backdrop=False);self.profile.setMaximumHeight(145);sidebar.addWidget(self.profile)
        self.profile.avatar.clicked.connect(lambda:self.run_command([catalog.ROOT/'scripts/control-center.sh','--tab','home']))
        sidebar.addSpacing(24)
        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setStyleSheet('QScrollArea {background:transparent; border:0;}')
        navigation_widget = QWidget()
        navigation = QVBoxLayout(navigation_widget)
        navigation.setContentsMargins(0, 0, 0, 0)
        navigation.setSpacing(6)
        navigation.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.nav = []
        for name, icon in [('Favorites', 'starred'), ('All apps', 'view-grid'),
                           ('Development', 'applications-development'), ('Internet', 'applications-internet'),
                           ('Media', 'applications-multimedia'), ('Games', 'applications-games'),
                           ('Utilities', 'applications-utilities')]:
            button = QPushButton(QIcon.fromTheme(icon), '  ' + name)
            button.setObjectName('launcherNav')
            button.setCheckable(True)
            button.setFixedWidth(180)
            button.clicked.connect(lambda checked=False, n=name: self.select_page(n))
            navigation.addWidget(button)
            self.nav.append((name, button))
        navigation.addStretch()
        for name, icon, command in [
            ('Files', 'folder', [catalog.ROOT/'scripts/dolphin.sh']),
            ('Theme', 'preferences-desktop-theme', [catalog.ROOT/'scripts/wallpaper.sh']),
            ('Control desk', 'preferences-system', [catalog.ROOT/'scripts/control-center.sh', '--tab', 'hotkeys']),
            ('Session & power', 'system-shutdown', [catalog.ROOT/'scripts/control-center.sh', '--tab', 'system'])]:
            button = QPushButton(QIcon.fromTheme(icon), '  ' + name)
            button.setObjectName('launcherNav')
            button.setFixedWidth(180)
            button.clicked.connect(lambda checked=False, c=command: self.run_command(c))
            navigation.addWidget(button)
        self.sidebar_scroll.setWidget(navigation_widget)
        sidebar.addWidget(self.sidebar_scroll, 1)
        sidebar.addSpacing(10)
        self.raw_account=label('●  ' + os.environ.get('USER', 'xetal'), 'eyebrow');sidebar.addWidget(self.raw_account)
        self.raw_session=label('Hyprland session', 'muted');sidebar.addWidget(self.raw_session)
        outer.addWidget(sidebar_widget)
        main = QVBoxLayout()
        main.setSpacing(16)
        greeting = QHBoxLayout()
        greeting.setSpacing(8)
        self.close_button=close_button(self,title='Close Apps')
        self.heading = label('Favorites', 'section')
        greeting.addWidget(self.heading)
        greeting.addStretch()
        self.add_group_button = QPushButton('+ New group')
        self.add_group_button.setStyleSheet('padding:5px 8px; color:palette(link);')
        self.add_group_button.clicked.connect(lambda: self.new_group())
        greeting.addWidget(self.add_group_button)
        self.create_button = QPushButton(QIcon.fromTheme('list-add'), 'New shortcut')
        self.create_button.setStyleSheet('padding:5px 8px;')
        self.create_button.clicked.connect(lambda: self.perform('new'))
        greeting.addWidget(self.create_button)
        self.count = label('', 'muted')
        greeting.addWidget(self.count)
        self.clock = label('', 'muted')
        greeting.addWidget(self.clock)
        greeting.addWidget(self.close_button)
        main.addLayout(greeting)
        self.search = QLineEdit()
        self.search.setObjectName('appSearch')
        self.search.setPlaceholderText('Search apps, tools, and favorites…')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.populate)
        self.search.returnPressed.connect(self.activate_current)
        self.search.installEventFilter(self)
        main.addWidget(self.search)
        self.grid = LaunchGrid()
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setGridSize(QSize(142, 112))
        self.grid.setWrapping(True)
        self.grid.setWordWrap(True)
        self.grid.setMouseTracking(True)
        self.grid.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.delegate = Tiles(self.grid)
        self.grid.setItemDelegate(self.delegate)
        self.grid.itemEntered.connect(self.delegate.entered)
        self.grid.itemActivated.connect(self.open_app)
        self.grid.clickedApp.connect(self.open_app)
        self.grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self.context_menu)
        self.favorites_board = Board(Tiles.draw)
        self.favorites_board.activated.connect(
            lambda ident, floating: self.launch_app(ident, floating=True if floating else None))
        self.favorites_board.selectedChanged.connect(self.select_favorite)
        self.favorites_board.appMenuRequested.connect(self.app_context_at)
        self.favorites_board.groupMenuRequested.connect(self.group_context_at)
        self.favorites_board.backgroundMenuRequested.connect(self.group_background_menu)
        self.favorites_board.newGroupRequested.connect(self.new_group)
        self.favorites_board.renameRequested.connect(self.rename_group)
        self.favorites_board.dropped.connect(self.move_favorite)
        self.favorites_board.dragStateChanged.connect(self.drag_state)
        self.views = QStackedWidget()
        self.views.addWidget(self.grid)
        self.views.addWidget(self.favorites_board)
        main.addWidget(self.views, 1)
        self.status = label('', 'muted')
        self.status.setWordWrap(True)
        self.status.hide()
        main.addWidget(self.status)
        outer.addLayout(main, 1)
        QShortcut(QKeySequence('Escape'), self).activated.connect(self.close)
        QShortcut(QKeySequence('Ctrl+F'), self).activated.connect(self.search.setFocus)
        QShortcut(QKeySequence('F2'), self).activated.connect(self.edit_current)
        QShortcut(QKeySequence('Ctrl+N'), self).activated.connect(lambda: self.perform('new'))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()
        self.fade = None
        self.select_page('Favorites')
        self.hotkeys.changed.connect(self.update_hotkeys)
        self.apply_design()
        if hasattr(QApplication.instance(),'hypr_theme'):QApplication.instance().hypr_theme.changed.connect(self.apply_design)
        QApplication.instance().aboutToQuit.connect(self.deleteLater)
        QTimer.singleShot(100, self.search.setFocus)

    def apply_design(self):
        modern=theme_runtime.design()=='modern'
        self.profile.setVisible(modern);self.profile.refresh()
        self.raw_header.setVisible(not modern);self.raw_avatar.refresh()
        for widget in (self.raw_brand,self.raw_eyebrow,self.raw_account,self.raw_session):widget.setVisible(not modern)
        self.outer.setContentsMargins(*(18,18,18,16) if modern else (24,26,24,20))
        self.outer.setSpacing(18 if modern else 20)
        self.refresh_backdrop()
        self.favorites_board.refresh_surfaces()
        self.update();self.grid.viewport().update();self.favorites_board.viewport().update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if getattr(self,'backdrop_image',None) and not self.backdrop_image.isNull():
            box=QRectF(self.rect()).adjusted(.5,.5,-.5,-.5)
            path=QPainterPath();path.addRoundedRect(box,20 if theme_runtime.design()=='modern' else 17,20 if theme_runtime.design()=='modern' else 17)
            painter.save();painter.setClipPath(path);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.fillRect(box,QColor(theme_runtime.colors()['Window']))
            picture=self.backdrop_image;scale=max(box.width()/picture.width(),box.height()/picture.height())
            target=QRectF(0,0,picture.width()*scale,picture.height()*scale);target.moveCenter(box.center())
            painter.drawPixmap(target,picture,QRectF(picture.rect()))
            shade=QColor(theme_runtime.colors()['Window']);shade.setAlpha(236 if theme_runtime.mode()=='light' else 242 if theme_runtime.mode()=='contrast' else 210)
            painter.fillRect(box,shade);painter.restore()
            painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(QColor(theme_runtime.colors()['Midlight']),1));painter.drawPath(path)
            return
        if theme_runtime.design()=='modern':
            colors=theme_runtime.colors();painter.setBrush(QColor(colors['Window']));painter.setPen(QPen(QColor(colors['Midlight']),1))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),20,20)
            return
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        if theme_runtime.mode() == 'light':
            gradient.setColorAt(0, QColor(246, 250, 255, 250))
            gradient.setColorAt(.6, QColor(235, 243, 250, 247))
            gradient.setColorAt(1, QColor(226, 241, 243, 250))
        else:
            gradient.setColorAt(0, QColor(17, 28, 44, 237))
            gradient.setColorAt(.6, QColor(16, 23, 38, 225))
            gradient.setColorAt(1, QColor(28, 29, 49, 233))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(98, 164, 179, 110), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 17, 17)
        painter.setPen(QColor(140, 172, 200, 35))
        painter.drawLine(226, 30, 226, self.height() - 30)

    def refresh_backdrop(self,*_):
        screen=self.screen()
        path=launcher_background_path(screen.name() if screen else None) if theme_runtime.launcher_wallpaper() else None
        if path!=getattr(self,'backdrop_source',None) or not hasattr(self,'backdrop_image'):
            self.backdrop_source=path;self.backdrop_image=QPixmap(str(path)) if path else QPixmap()
        self.update()

    def showEvent(self,event):
        super().showEvent(event)
        if not getattr(self,'backdrop_screen_connected',False) and self.windowHandle():
            self.windowHandle().screenChanged.connect(self.refresh_backdrop);self.backdrop_screen_connected=True
        self.refresh_backdrop()

    def resize_edges(self, point):
        edges = Qt.Edge(0)
        if point.x() < 9: edges |= Qt.Edge.LeftEdge
        elif point.x() >= self.width() - 9: edges |= Qt.Edge.RightEdge
        if point.y() < 9: edges |= Qt.Edge.TopEdge
        elif point.y() >= self.height() - 9: edges |= Qt.Edge.BottomEdge
        return edges

    def mouseMoveEvent(self, event):
        edges = self.resize_edges(event.position())
        horizontal = bool(edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge))
        vertical = bool(edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge))
        if horizontal and vertical:
            cursor = Qt.CursorShape.SizeFDiagCursor if bool(edges & Qt.Edge.LeftEdge) == bool(edges & Qt.Edge.TopEdge) else Qt.CursorShape.SizeBDiagCursor
        elif horizontal: cursor = Qt.CursorShape.SizeHorCursor
        elif vertical: cursor = Qt.CursorShape.SizeVerCursor
        else: cursor = Qt.CursorShape.ArrowCursor
        self.setCursor(cursor)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        edges = self.resize_edges(event.position())
        if event.button() == Qt.MouseButton.LeftButton and edges and self.windowHandle():
            self.started = time.monotonic()
            if self.windowHandle().startSystemResize(edges):
                event.accept(); return
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'size_grip'):
            self.size_grip.setGeometry(self.width() - 24, self.height() - 24, 18, 18)
            self.size_grip.raise_()
        if hasattr(self, 'clock'):
            self.tick()
        self.started = time.monotonic()

    def tick(self):
        now = datetime.datetime.now()
        self.clock.setText(now.strftime('%a, %b %d   ·   %H:%M' if self.width() >= 1100 else '%H:%M'))
        self.clock.setToolTip(now.strftime('%A, %B %d'))

    def report(self, message=''):
        self.status.setText(message)
        self.status.setVisible(bool(message))

    def select_page(self, name):
        self.page = name
        for title, button in self.nav:
            button.setChecked(title == name)
        self.search.clear()
        self.populate()
        if self.fade:
            self.fade.stop()
        self.fade_effect = QGraphicsOpacityEffect(self.views)
        self.views.setGraphicsEffect(self.fade_effect)
        self.fade = QPropertyAnimation(self.fade_effect, b'opacity', self)
        self.fade.setDuration(180)
        self.fade.setStartValue(.25)
        self.fade.setEndValue(1.0)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade.start()

    def populate(self):
        selected = self.grid.currentItem().data(Qt.ItemDataRole.UserRole) if self.grid.currentItem() else None
        self.reload_layout()
        query = self.search.text().casefold().strip()
        categories = {'Development': ('Development',), 'Internet': ('Network',),
                      'Media': ('AudioVideo', 'Graphics'), 'Games': ('Game',),
                      'Utilities': ('Utility', 'System', 'Settings', 'Office')}
        apps = list(self.apps.values())
        if query:
            def rank(app):
                name = app.get_display_name().casefold()
                return (not name.startswith(query), app.get_id() not in self.pinned, name)
            apps = [a for a in apps if all(token in ' '.join([a.get_display_name(), a.get_description() or '',
                    a.get_executable() or '', a.get_categories() or '', ' '.join(a.get_keywords() or [])]).casefold()
                    for token in query.split())]
            apps.sort(key=rank)
        elif self.page == 'Favorites':
            groups = sorted(self.favorite_layout['groups'], key=lambda group: group['column'])
            apps = [self.apps[tile['app']] for group in groups for tile in group['tiles'] if tile['app'] in self.apps]
        else:
            if self.page in categories:
                apps = [a for a in apps if any(c in (a.get_categories() or '').split(';') for c in categories[self.page])]
            apps.sort(key=lambda a: a.get_display_name().casefold())
        self.grid.clear()
        for app in apps:
            item = QListWidgetItem(icon_for(app), app.get_display_name())
            item.setData(Qt.ItemDataRole.UserRole, app.get_id())
            item.setToolTip(app.get_display_name() + '\n' + (app.get_description() or ''))
            self.grid.addItem(item)
        self.update_hotkeys()
        if apps:
            row = next((i for i, app in enumerate(apps) if app.get_id() == selected), 0)
            self.grid.setCurrentRow(row)
        current = self.grid.currentItem().data(Qt.ItemDataRole.UserRole) if self.grid.currentItem() else None
        self.favorites_board.set_layout(self.favorite_layout, self.favorite_items(), current)
        grouped = self.page == 'Favorites' and not query
        self.views.setCurrentWidget(self.favorites_board if grouped else self.grid)
        self.add_group_button.setVisible(grouped)
        self.heading.setText('Search results' if query else self.page)
        self.count.setText(f'{len(apps)} apps')
        if hasattr(self, 'status'):
            self.report(self.layout_error if grouped and self.layout_error else
                        'No matching applications. Try a different name.' if not apps else '')

    def update_hotkeys(self):
        for row in range(self.grid.count()):
            item=self.grid.item(row);entry=self.apps[item.data(Qt.ItemDataRole.UserRole)]
            labels=self.hotkeys.labels(entry)
            item.setData(hotkeys.ROLE,labels if entry.get_id() in self.pinned else None)
            tip=entry.get_display_name()+'\n'+(entry.get_description() or '')
            if labels:tip+='\nLaunch: '+', '.join(labels)
            elif entry.get_id() in self.pinned:tip+='\nRight-click → Set launch hotkey…'
            item.setToolTip(tip)
        if hasattr(self, 'favorites_board') and self.favorites_board.tiles:
            self.favorites_board.update_items(self.favorite_items())

    def favorite_items(self):
        result = {}
        for ident in self.pinned:
            entry = self.apps.get(ident)
            if entry:
                bindings = self.hotkeys.labels(entry)
                tip = entry.get_display_name() + '\n' + (entry.get_description() or '')
                if bindings:
                    tip += '\nLaunch: ' + ', '.join(bindings)
                result[ident] = {'name': entry.get_display_name(), 'icon': icon_for(entry),
                                 'hotkeys': bindings, 'tooltip': tip}
        return result

    def reload_layout(self):
        try:
            self.favorite_layout, self.layout_token = self.layout_store.load(self.pinned)
            self.layout_error = ''
        except (OSError, ValueError, TypeError) as exc:
            self.favorite_layout = favorite_layout.reconcile({'version': 1, 'groups': []}, self.pinned)
            self.layout_token = None
            self.layout_error = 'Could not read saved layout: ' + str(exc)

    def change_layout(self, change, selected=None):
        try:
            if self.layout_token is None:
                raise ValueError(self.layout_error or 'Reload Favorites before editing its layout.')
            data = copy.deepcopy(self.favorite_layout)
            change(data)
            if data == self.favorite_layout:
                return
            self.layout_token = self.layout_store.save(data, self.layout_token)
            self.favorite_layout = data
            self.favorites_board.set_layout(data, self.favorite_items(), selected or self.favorites_board.selected)
            self.report()
        except (OSError, ValueError, StopIteration) as exc:
            self.report('Could not save layout: ' + str(exc))

    def select_favorite(self, ident):
        for row in range(self.grid.count()):
            if self.grid.item(row).data(Qt.ItemDataRole.UserRole) == ident:
                self.grid.setCurrentRow(row)
                break

    def drag_state(self, active):
        self.interaction_depth += 1 if active else -1
        self.started = time.monotonic()

    def new_group(self, column=None):
        if column is None:
            selected = next((g for g in self.favorite_layout['groups'] if g['id'] == self.favorites_board.selected_group), None)
            column = selected['column'] if selected else 0
        self.interaction_depth += 1
        try:
            title, accepted = QInputDialog.getText(self, 'New favorite group', 'Group title:')
            if accepted and title.strip():
                self.change_layout(lambda data: data['groups'].append(favorite_layout.group(title.strip(), column)))
        finally:
            self.interaction_depth -= 1
            self.started = time.monotonic()

    def rename_group(self, ident):
        group = favorite_layout.find_group(self.favorite_layout, ident)
        self.interaction_depth += 1
        try:
            title, accepted = QInputDialog.getText(self, 'Rename group', 'Group title:', text=group['title'])
            if accepted and title.strip():
                self.change_layout(lambda data: favorite_layout.find_group(data, ident).update(title=title.strip()))
        finally:
            self.interaction_depth -= 1
            self.started = time.monotonic()

    def move_favorite(self, payload, target):
        def change(data):
            if payload['kind'] == 'group':
                favorite_layout.move_group(data, payload['id'], target['column'], target['before'])
            else:
                ident = target['group']
                if ident is None:
                    group = favorite_layout.group('New group', target['column'])
                    data['groups'].append(group)
                    ident = group['id']
                favorite_layout.place_tile(data, payload['id'], ident, target['cell'])
        self.change_layout(change, payload['id'] if payload['kind'] == 'tile' else None)

    def group_context_at(self, ident, position):
        group = favorite_layout.find_group(self.favorite_layout, ident)
        menu = QMenu(self)
        menu.addAction('Rename group…').setData('rename')
        left = menu.addAction('Move group one column left'); left.setData('left'); left.setEnabled(group['column'] > 0)
        right = menu.addAction('Move group one column right'); right.setData('right'); right.setEnabled(group['column'] < 63)
        menu.addSeparator()
        remove = menu.addAction('Remove group · keep its apps'); remove.setData('remove')
        remove.setEnabled(len(self.favorite_layout['groups']) > 1 or not group['tiles'])
        self.interaction_depth += 1
        try:
            action = menu.exec(position)
            if action:
                if action.data() == 'rename': self.rename_group(ident)
                elif action.data() == 'remove': self.change_layout(lambda data: favorite_layout.remove_group(data, ident))
                else:
                    column = group['column'] + (-1 if action.data() == 'left' else 1)
                    self.change_layout(lambda data: favorite_layout.move_group(data, ident, column))
        finally:
            menu.deleteLater()
            self.interaction_depth -= 1
            self.started = time.monotonic()

    def group_background_menu(self, column, position):
        menu = QMenu(self)
        menu.addAction('New group…').setData('group')
        menu.addAction('New shortcut…').setData('shortcut')
        self.interaction_depth += 1
        try:
            action = menu.exec(position)
            if action:
                if action.data() == 'group': self.new_group(column)
                else: self.perform('new')
        finally:
            menu.deleteLater()
            self.interaction_depth -= 1
            self.started = time.monotonic()

    def run_command(self, command):
        leave_dashboard()
        launch(command)
        self.close()

    def activate_current(self):
        if self.views.currentWidget() == self.favorites_board:
            board = self.favorites_board
            target = board.tiles.get(board.selected)
            if target is None or target.isHidden():
                target = next((tile for tile in board.tiles.values() if not tile.isHidden()), None)
            if target:
                self.launch_app(target.ident)
            return
        if self.grid.currentItem():
            self.open_app(self.grid.currentItem())

    def open_app(self, item, floating=False):
        if self.interaction_depth:
            return
        app_id = item.data(Qt.ItemDataRole.UserRole)
        self.launch_app(app_id, floating=True if floating else None)

    def launch_app(self, app_id, terminal=None, floating=None):
        try:
            leave_dashboard()
            self.apps[app_id].launch(terminal=terminal,floating=floating)
            self.close()
        except Exception as exc:
            self.report('Could not open this app: ' + str(exc))

    def context_menu(self, point):
        item = self.grid.currentItem() if point.x() < 0 else self.grid.itemAt(point)
        if item:
            self.grid.setCurrentItem(item)
        app_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        position = self.grid.visualItemRect(item).center() if point.x() < 0 and item else point
        self.app_context_at(app_id, self.grid.viewport().mapToGlobal(position))

    def app_context_at(self, app_id, position):
        if app_id:
            self.select_favorite(app_id)
        menu = self.build_context_menu(app_id)
        self.interaction_depth += 1
        try:
            action = menu.exec(position)
            if action and action.data():
                self.perform(action.data(), app_id)
        finally:
            self.interaction_depth -= 1
            menu.deleteLater()
            self.started = time.monotonic()
            if self.isVisible():
                self.activateWindow()

    def build_context_menu(self, app_id=None):
        menu = QMenu(self)
        def add(text, icon, action, enabled=True):
            item = menu.addAction(QIcon.fromTheme(icon), text)
            item.setData(action); item.setEnabled(enabled)
            return item
        if app_id:
            entry = self.apps[app_id]
            title = menu.addAction(entry.get_display_name().replace('&', '&&'))
            title.setEnabled(False)
            add('Open', 'system-run', 'open')
            add('Launch floating', 'window-new', 'open-floating')
            add('Open in terminal', 'utilities-terminal', 'terminal')
            menu.addSeparator()
            add('Unpin from Favorites' if app_id in self.pinned else 'Pin to Favorites', 'starred', 'pin')
            on_bar = app_id in pins.pinned()
            add('Unpin from bar' if on_bar else 'Pin to bar · beside Keys',
                'window-unpin' if on_bar else 'window-pin', 'bar-pin')
            add('Duplicate into Favorites…', 'edit-copy', 'duplicate')
            if app_id in self.pinned:
                sizes = menu.addMenu('Tile size')
                current = favorite_layout.find_tile(self.favorite_layout, app_id)[1]['size']
                for size, title in [('medium', 'Medium · icon, name and hotkey'), ('small', 'Small · icon only')]:
                    action = sizes.addAction(title); action.setData('tile-size:' + size)
                    action.setCheckable(True); action.setChecked(current == size)
                groups = menu.addMenu('Move to group')
                for group in self.favorite_layout['groups']:
                    action = groups.addAction(group['title'].replace('&', '&&'))
                    action.setData('tile-group:' + group['id'])
            menu.addSeparator()
            add('Change launch hotkey…' if self.hotkeys.bindings(entry) else 'Set launch hotkey…',
                'preferences-desktop-keyboard-shortcuts', 'hotkey')
            add('Change icon…', 'preferences-desktop-icons', 'icon')
            check = add('Always run in terminal', 'utilities-terminal', 'toggle-terminal')
            check.setIcon(QIcon())
            check.setCheckable(True); check.setChecked(entry.fields['terminal'])
            check=add('Always start floating','window-new','toggle-floating')
            check.setIcon(QIcon());check.setCheckable(True);check.setChecked(entry.fields['floating'])
            menu.addSeparator()
            add('Copy command', 'edit-copy', 'copy-command')
            add('Show shortcut file', 'document-open-folder', 'show-file', bool(entry.source))
            add('Restore original settings', 'edit-undo', 'reset', bool(entry.changes) and not entry.custom)
            if entry.custom:
                add('Delete this shortcut copy…', 'edit-delete', 'delete')
            menu.addSeparator()
            add('Properties', 'document-properties', 'edit')
        else:
            add('New shortcut…', 'list-add', 'new')
            add('New favorite group…', 'folder-new', 'new-group')
        return menu

    def refresh_apps(self, selected_id=None):
        self.apps = catalog.applications()
        self.pinned = catalog.favorites()
        self.populate()
        for row in range(self.grid.count()):
            if self.grid.item(row).data(Qt.ItemDataRole.UserRole) == selected_id:
                self.grid.setCurrentRow(row)
                self.favorites_board.select(selected_id)
                break

    def edit_current(self):
        for ident, header in self.favorites_board.headers.items():
            if header.hasFocus():
                self.rename_group(ident)
                return
        item = self.grid.currentItem()
        if item:
            self.perform('edit', item.data(Qt.ItemDataRole.UserRole))

    def edit_shortcut(self, entry=None, duplicate=False, change_icon=False):
        dialog = ShortcutEditor(entry, self, duplicate=duplicate)
        if change_icon:
            QTimer.singleShot(0, lambda: dialog.browse('icon'))
        while dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                if duplicate or entry is None:
                    ident = shortcuts.duplicate(entry, dialog.fields)
                    catalog.pin(ident, True)
                else:
                    ident = shortcuts.save(entry, dialog.fields)
                self.refresh_apps(ident)
                self.report('Shortcut saved.')
                break
            except (OSError, ValueError) as exc:
                dialog.error.setText('Could not save: ' + str(exc))
        dialog.deleteLater()

    def perform(self, action, app_id=None):
        entry = self.apps.get(app_id)
        self.interaction_depth += 1
        try:
            if action.startswith('tile-size:'):
                self.change_layout(lambda data: favorite_layout.resize_tile(data, app_id, action.split(':', 1)[1]), app_id)
            elif action.startswith('tile-group:'):
                self.change_layout(lambda data: favorite_layout.move_tile(data, app_id, action.split(':', 1)[1]), app_id)
            elif action == 'new-group':
                self.new_group()
            elif action in ('open', 'terminal', 'open-floating'):
                self.launch_app(app_id, True if action == 'terminal' else None,
                                True if action=='open-floating' else None)
            elif action == 'pin':
                catalog.pin(app_id, app_id not in self.pinned)
                self.refresh_apps(app_id)
            elif action == 'bar-pin':
                enabled = app_id not in pins.pinned()
                pins.pin(app_id, enabled)
                self.report('Pinned beside Keys.' if enabled else 'Unpinned from the bar.')
            elif action in ('edit', 'duplicate', 'icon', 'new'):
                self.edit_shortcut(None if action == 'new' else entry,
                                   duplicate=action == 'duplicate', change_icon=action == 'icon')
            elif action == 'hotkey':
                dialog=HotkeyDialog(entry,self,self.hotkeys.store)
                if dialog.exec()==QDialog.DialogCode.Accepted:
                    self.hotkeys.reload();self.update_hotkeys()
                    self.report('Hotkeys updated.')
                dialog.deleteLater()
            elif action == 'toggle-terminal':
                shortcuts.save(entry, {**entry.fields, 'terminal': not entry.fields['terminal']})
                self.refresh_apps(app_id)
            elif action == 'toggle-floating':
                shortcuts.save(entry,{**entry.fields,'floating':not entry.fields['floating']})
                self.refresh_apps(app_id)
                self.report('Floating preference saved.')
            elif action == 'copy-command':
                QApplication.clipboard().setText(entry.get_commandline())
                self.report('Command copied.')
            elif action == 'show-file':
                self.run_command([catalog.ROOT/'scripts/dolphin.sh', '--select', entry.source])
            elif action == 'reset':
                shortcuts.reset(entry)
                self.refresh_apps(app_id)
                self.report('Original shortcut settings restored.')
            elif action == 'delete':
                prompt = QMessageBox(self)
                prompt.setWindowTitle('Delete shortcut copy?')
                prompt.setTextFormat(Qt.TextFormat.PlainText)
                prompt.setText('Delete “' + entry.get_display_name() + '” from this menu?')
                prompt.setInformativeText('The installed application and its original shortcut are kept.')
                delete = prompt.addButton('Delete copy', QMessageBox.ButtonRole.DestructiveRole)
                cancel = prompt.addButton(QMessageBox.StandardButton.Cancel)
                prompt.setDefaultButton(cancel); prompt.setEscapeButton(cancel); prompt.exec()
                if prompt.clickedButton() == delete:
                    shortcuts.remove_copy(entry)
                    catalog.pin(app_id, False)
                    pins.pin(app_id, False)
                    self.refresh_apps()
        except Exception as exc:
            self.report('Could not update shortcut: ' + str(exc))
        finally:
            self.interaction_depth -= 1
            self.started = time.monotonic()
            if self.isVisible():
                self.activateWindow()

    def eventFilter(self, watched, event):
        if watched == self.search and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Down:
            if self.views.currentWidget() == self.favorites_board:
                self.favorites_board.focus_selected()
            else:
                self.grid.setFocus()
            return True
        return super().eventFilter(watched, event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and hasattr(self, 'dismiss_timer'):
            if self.isActiveWindow() or self.preview:
                self.pending_outside_click = False
                self.pointer_generation += 1
                self.dismiss_timer.stop()
            else:
                self.dismiss_timer.start(120)
        super().changeEvent(event)

    def handle_compositor_events(self, watcher):
        while watcher.canReadLine():
            if bytes(watcher.readLine()).strip() == CLICK_EVENT:
                self.pointer_clicked()

    def dismissal_protected(self):
        return (self.interaction_depth or capture_guard.active()
                or QApplication.activePopupWidget() or QApplication.activeModalWidget())

    def pointer_clicked(self):
        self.pointer_generation += 1
        generation = self.pointer_generation
        self.pending_outside_click = False
        if self.preview or not self.isVisible() or self.dismissal_protected():
            return

        def checked(outside):
            if (generation != self.pointer_generation or outside is not True
                    or not self.isVisible() or self.dismissal_protected()):
                return
            # Clicking wallpaper need not deactivate a Wayland toplevel.
            self.pending_outside_click = True
            self.close_if_outside()

        check_pointer(self, checked)

    def close_if_outside(self):
        self.dismiss_timer.stop()
        if (self.preview or not self.isVisible()
                or (self.isActiveWindow() and not self.pending_outside_click)):
            return
        # Focus may already be elsewhere when capture or an editor finishes;
        # there may be no second activation event to trigger dismissal.
        if self.dismissal_protected():
            self.pending_outside_click = False
            self.dismiss_timer.start(120)
            return
        remaining = .6 - (time.monotonic() - self.started)
        if remaining > 0:
            self.dismiss_timer.start(max(1, int(remaining * 1000) + 1))
            return
        bar_toggle.remember()
        self.close()

    def closeEvent(self, event):
        if QApplication.activeModalWidget() and self.interaction_depth:
            event.ignore()
            return
        self.dismiss_timer.stop()
        self.pointer_generation += 1
        self.pending_outside_click = False
        if not self.preview:
            try: geometry.save(self.width(), self.height())
            except OSError: pass
        super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview')
    parser.add_argument('--from-bar',action='store_true',help='Toggle from the Apps button')
    parser.add_argument('--edit', help='Open the shortcut editor for this application ID')
    parser.add_argument('--initial-size', type=int, nargs=2, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.preview and not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        return 1
    app = QApplication(sys.argv[:1])
    app.setApplicationName('xetal-launcher')
    app.setDesktopFileName('xetal-launcher')
    theme_runtime.install(app, STYLE)
    QIcon.setThemeSearchPaths([str(Path.home()/'.local/share/icons'), '/usr/share/icons'])
    QIcon.setFallbackThemeName('hicolor')
    QIcon.setThemeName('Papirus-Light' if theme_runtime.mode() == 'light' else 'Papirus-Dark')
    server = None
    if not args.preview:
        instance = Path(os.environ['XDG_RUNTIME_DIR']) / 'hypr' / os.environ['HYPRLAND_INSTANCE_SIGNATURE']
        address = str(instance/'xetal-launcher.sock')
        peer = QLocalSocket()
        peer.connectToServer(address)
        if peer.waitForConnected(100):
            bar_toggle.clear()
            peer.write((json.dumps({'edit': args.edit}) + '\n').encode() if args.edit else b'toggle\n')
            peer.waitForBytesWritten(100)
            return 0
        if args.from_bar and not args.edit and bar_toggle.consume():
            return 0
        bar_toggle.clear()
        QLocalServer.removeServer(address)
        server = QLocalServer()
        if not server.listen(address):
            return 1
    window = Menu(bool(args.preview))
    if args.initial_size and all(0 < value <= 16384 for value in args.initial_size):
        window.setMinimumSize(*(min(base, value) for base, value in zip(geometry.MINIMUM, args.initial_size)))
        window.resize(*args.initial_size)
    if server:
        def accept_request():
            peer = server.nextPendingConnection()
            def receive():
                if not peer.canReadLine():
                    return
                message = bytes(peer.readLine()).strip()
                peer.disconnectFromServer()
                peer.deleteLater()
                if message == b'toggle':
                    window.close()
                    return
                try:
                    ident = json.loads(message).get('edit')
                    if ident and not window.interaction_depth:
                        window.refresh_apps(ident)
                        if ident in window.apps:
                            window.show(); window.activateWindow()
                            window.perform('edit', ident)
                except (ValueError, AttributeError):
                    pass
            peer.readyRead.connect(receive)
            receive()
        server.newConnection.connect(accept_request)
        watcher = QLocalSocket(app)
        watcher.connectToServer(str(instance/'.socket2.sock'))
        watcher.readyRead.connect(lambda: window.handle_compositor_events(watcher))
        watcher.disconnected.connect(app.quit)
    window.show()
    if window.screen() and not args.initial_size:
        available = window.screen().availableGeometry()
        window.resize(min(window.width(), available.width() - 48), min(window.height(), available.height() - 70))
    if args.edit and args.edit in window.apps:
        QTimer.singleShot(0, lambda: window.perform('edit', args.edit))
    if args.preview:
        QTimer.singleShot(600, lambda: (window.grab().save(args.preview), app.quit()))
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())

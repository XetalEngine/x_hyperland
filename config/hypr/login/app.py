#!/usr/bin/python3
"""Fusion's native, theme-aware greetd sign-in screen.

This is a greeter, not an overlay over an authenticated person's desktop.
Only greetd handles PAM and launches the selected user's desktop session.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import socket
import sys

from PyQt6.QtCore import (QObject, QPointF, QRectF, QSize, Qt,
                         QSignalBlocker, QTimer, pyqtSignal)
from PyQt6.QtGui import (QColor, QFont, QFontDatabase, QImageReader,
                        QMovie, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtWidgets import (QApplication, QComboBox, QFrame, QGraphicsDropShadowEffect,
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)

from model import DESIGNS, accounts, presentation, read_json, sessions, session_environment
from protocol import Decoder, Flow, encode

HERE = Path(__file__).resolve().parent


def label(text='', name='', parent=None):
    item = QLabel(text, parent)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setObjectName(name)
    return item


class Avatar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(112, 112)
        self.movie = None
        self.image = QPixmap()
        self.accent = QColor('#88b6d9')
        self.initial = ''

    def load(self, path, initial, accent):
        if self.movie:
            self.movie.stop(); self.movie.deleteLater(); self.movie = None
        self.initial, self.accent = initial, QColor(accent)
        self.image = QPixmap(str(path)) if path else QPixmap()
        if path and QImageReader(str(path)).supportsAnimation():
            self.movie = QMovie(str(path), parent=self)
            self.movie.setScaledSize(QSize(224, 224))
            self.movie.frameChanged.connect(self.update)
            self.movie.start()
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        box = QRectF(self.rect()).adjusted(7, 7, -7, -7)
        clip = QPainterPath(); clip.addEllipse(box)
        painter.setClipPath(clip)
        background = QColor(self.accent); background.setAlpha(38)
        painter.fillRect(box, background)
        picture = self.movie.currentPixmap() if self.movie else self.image
        if not picture.isNull():
            side = min(picture.width(), picture.height())
            source = QRectF((picture.width()-side)/2, (picture.height()-side)/2, side, side)
            painter.drawPixmap(box, picture, source)
        else:
            painter.setFont(QFont('Sans', 32, QFont.Weight.Light)); painter.setPen(self.accent)
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, self.initial[:1].upper())
        painter.setClipping(False)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self.accent, 2)); painter.drawEllipse(box)
        faint = QColor(self.accent); faint.setAlpha(45)
        painter.setPen(QPen(faint, 1)); painter.drawEllipse(box.adjusted(-6, -6, 6, 6))


class Controller(QObject):
    status = pyqtSignal(str, str)
    userChanged = pyqtSignal(int)
    sessionChanged = pyqtSignal(int)

    def __init__(self, preview=False, theme=None, mode=None):
        super().__init__()
        self.preview, self.theme_override, self.mode_override = preview, theme, mode
        self.users, self.desktops = accounts(), sessions()
        if preview and not self.users:
            self.users = [{'username': 'alex', 'name': 'Alex Morgan', 'uid': os.getuid()}]
        if preview and not self.desktops:
            from model import Session
            self.desktops = [Session('wayland:hyprland.desktop', 'Hyprland', 'wayland', 'Hyprland', ('start-hyprland',))]
        self.user_index = self.session_index = 0
        self.phase = 'busy'
        self.settings = Path.home()/'.local/state/xetal-fusion-login/choices.json'
        self.saved = read_json(self.settings)
        if not isinstance(self.saved.get('sessions', {}), dict): self.saved['sessions'] = {}
        for index, user in enumerate(self.users):
            if user['username'] == self.saved.get('username'): self.user_index = index
        self.restore_session()
        self.flow = Flow(self.send, self.notify, self.command)
        self.peer = QLocalSocket(self)
        self.decoder = Decoder()
        self.peer.connected.connect(self.begin)
        self.peer.readyRead.connect(self.read)
        self.peer.errorOccurred.connect(lambda *_: self.notify('fatal', 'Cannot reach the sign-in service. Please restart the computer or use another console.')
                                       if self.phase != 'launched' else None)

    def look(self):
        user = self.users[self.user_index]
        result = presentation(user)
        if self.preview:
            # Preview can read its own profile; the actual greeter reads public copies only.
            from profile import read
            root = HERE.parent
            state = read(root/'theme/state.json')
            avatar = state.get('avatar', 'assets/account.gif')
            if isinstance(avatar, str) and avatar != 'auto':
                path = Path(avatar).expanduser()
                if not path.is_absolute(): path = root/'theme'/path
                if path.is_file(): result['avatar'] = path
            choices = read(root/'wallpaper/selection.json')
            for item in choices.values():
                if isinstance(item, dict) and isinstance(item.get('path'), str) and Path(item['path']).is_file():
                    result['wallpaper'] = Path(item['path']); break
            result['design'] = state.get('design', 'modern')
            result['mode'] = state.get('mode', 'dark')
        result['design'] = self.theme_override or result['design']
        result['mode'] = self.mode_override or result['mode']
        if result['design'] not in DESIGNS: result['design'] = 'modern'
        if not result['avatar']:
            fallback = HERE/'account.gif' if (HERE/'account.gif').exists() else HERE.parent/'theme/assets/account.gif'
            result['avatar'] = fallback if fallback.is_file() else None
        return result

    def restore_session(self):
        if not self.users: return
        selected = self.saved.get('sessions', {}).get(self.users[self.user_index]['username'])
        self.session_index = next((i for i, session in enumerate(self.desktops) if session.identifier == selected), 0)

    def start(self):
        if not self.users or not self.desktops:
            self.notify('fatal', 'No desktop accounts or installed desktop sessions were found.'); return
        if self.preview: self.notify('secret', 'Password:'); return
        path = os.environ.get('GREETD_SOCK')
        if not path:
            self.notify('fatal', 'Start Fusion sign-in through its login service.'); return
        self.peer.connectToServer(path)

    def begin(self): self.flow.select(self.users[self.user_index]['username'])

    def send(self, message): self.peer.write(encode(message))

    def read(self):
        try:
            for message in self.decoder.feed(bytes(self.peer.readAll())): self.flow.receive(message)
        except (ValueError, RuntimeError): self.notify('fatal', 'The sign-in service connection was interrupted.')

    def notify(self, phase, message):
        self.phase = phase
        self.status.emit(phase, message)
        if phase == 'launched':
            saved = {'username': self.users[self.user_index]['username'],
                     'sessions': {**self.saved.get('sessions', {}),
                                  self.users[self.user_index]['username']: self.desktops[self.session_index].identifier}}
            try:
                from profile import atomic
                self.settings.parent.mkdir(parents=True, exist_ok=True)
                atomic(self.settings, (json.dumps(saved)+'\n').encode())
            except OSError: pass
            # Exiting this UI makes greeter-session.sh terminate its compositor.
            QTimer.singleShot(450, QApplication.instance().quit)

    def select_user(self, index):
        if index == self.user_index or self.phase in ('busy', 'starting', 'launched', 'fatal'): return
        self.user_index = index
        self.restore_session()
        self.userChanged.emit(index); self.sessionChanged.emit(self.session_index)
        if self.preview: self.notify('secret', 'Password:')
        else: self.flow.select(self.users[index]['username'])

    def select_session(self, index):
        if index == self.session_index: return
        self.session_index = index
        self.sessionChanged.emit(index)

    def command(self):
        session = self.desktops[self.session_index]
        return ([str(HERE/'launch.py'), '--session', session.identifier], session_environment(session))

    def submit(self, text):
        if self.preview:
            self.status.emit('message', 'Preview only. No password is checked or saved.'); return
        if self.phase == 'error': self.flow.select(self.users[self.user_index]['username'])
        elif self.phase in ('secret', 'visible', 'ready'): self.flow.answer(text)


class SignIn(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle('Hyper Fusion / Sign in')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(760, 680)
        self.wallpaper = QPixmap()
        outer = QVBoxLayout(self); outer.setContentsMargins(52, 35, 52, 27); outer.setSpacing(20)
        header = QHBoxLayout()
        self.brand = label('◈   H Y P E R   F U S I O N', 'brand')
        header.addWidget(self.brand); header.addStretch()
        self.time = label('', 'clock'); self.time.setAlignment(Qt.AlignmentFlag.AlignRight)
        header.addWidget(self.time); outer.addLayout(header)
        self.body = body = QHBoxLayout(); body.setSpacing(70); body.addStretch(0)
        self.hero = QWidget(); hero = QVBoxLayout(self.hero)
        hero.setContentsMargins(0, 0, 0, 0); hero.addStretch(2)
        self.theme_badge = label('', 'badge'); hero.addWidget(self.theme_badge)
        hero.addSpacing(18)
        self.headline = label('A little\nextraordinary.', 'headline'); hero.addWidget(self.headline)
        hero.addSpacing(18)
        self.caption = label('Your space. Your pace.\nSign in and make it yours.', 'caption'); hero.addWidget(self.caption)
        hero.addStretch(3)
        self.orbit_caption = label('D E S I G N E D   A R O U N D   Y O U', 'micro'); hero.addWidget(self.orbit_caption)
        body.addWidget(self.hero, 1)
        self.card = QFrame(); self.card.setObjectName('card'); self.card.setFixedWidth(438)
        self.form = form = QVBoxLayout(self.card); form.setContentsMargins(38, 30, 38, 30); form.setSpacing(8)
        self.avatar = Avatar(); form.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignHCenter)
        form.addSpacing(8)
        self.greeting = label('Welcome back.', 'greeting'); self.greeting.setAlignment(Qt.AlignmentFlag.AlignCenter)
        form.addWidget(self.greeting)
        self.fullname = label('', 'fullname'); self.fullname.setAlignment(Qt.AlignmentFlag.AlignCenter); form.addWidget(self.fullname)
        self.username = label('', 'username'); self.username.setAlignment(Qt.AlignmentFlag.AlignCenter); form.addWidget(self.username)
        self.user_select = QComboBox(); self.user_select.setAccessibleName('User account')
        self.user_select.setObjectName('userSelect')
        for user in controller.users: self.user_select.addItem(user['name']+'  ·  '+user['username'])
        self.user_select.setCurrentIndex(controller.user_index)
        self.user_select.setVisible(len(controller.users) > 1)
        self.user_select.currentIndexChanged.connect(controller.select_user); form.addWidget(self.user_select)
        form.addSpacing(16)
        self.prompt = label('Password', 'fieldLabel'); form.addWidget(self.prompt)
        self.password_box = QFrame(); self.password_box.setObjectName('passwordBox')
        password_layout = QHBoxLayout(self.password_box); password_layout.setContentsMargins(15, 0, 8, 0)
        self.password = QLineEdit(); self.password.setPlaceholderText('Enter your password')
        self.password.setAccessibleName('Password'); self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.password.setInputMethodHints(Qt.InputMethodHint.ImhSensitiveData | Qt.InputMethodHint.ImhNoPredictiveText)
        self.password.returnPressed.connect(self.submit); password_layout.addWidget(self.password)
        self.reveal = QPushButton('◉'); self.reveal.setObjectName('reveal'); self.reveal.setFixedSize(34, 38)
        self.reveal.setAccessibleName('Hold to show password'); self.reveal.setToolTip('Hold to show password')
        self.reveal.pressed.connect(lambda: self.password.setEchoMode(QLineEdit.EchoMode.Normal))
        self.reveal.released.connect(lambda: self.password.setEchoMode(QLineEdit.EchoMode.Password))
        password_layout.addWidget(self.reveal); form.addWidget(self.password_box)
        self.message = label('', 'message'); self.message.setWordWrap(True); self.message.setMinimumHeight(35)
        form.addWidget(self.message)
        self.enter = QPushButton('Enter your workspace   →'); self.enter.setObjectName('enter'); self.enter.setMinimumHeight(52)
        self.enter.clicked.connect(self.submit); form.addWidget(self.enter)
        form.addSpacing(14)
        form.addWidget(label('DESKTOP SESSION', 'fieldLabel'))
        self.desktop_select = QComboBox(); self.desktop_select.setAccessibleName('Desktop session')
        for session in controller.desktops:
            self.desktop_select.addItem(session.name+'  ·  '+('Wayland' if session.kind == 'wayland' else 'X11'))
        self.desktop_select.setCurrentIndex(controller.session_index)
        self.desktop_select.currentIndexChanged.connect(controller.select_session); form.addWidget(self.desktop_select)
        form.addSpacing(16)
        self.trust = label('Protected by your Linux account', 'trust'); self.trust.setAlignment(Qt.AlignmentFlag.AlignCenter)
        form.addWidget(self.trust)
        body.addWidget(self.card, 0, Qt.AlignmentFlag.AlignVCenter)
        body.addStretch(0); outer.addLayout(body, 1)
        footer = QHBoxLayout(); self.host = label(socket.gethostname(), 'micro'); footer.addWidget(self.host)
        footer.addStretch(); self.footer = label('YOUR WORKSPACE.  READY FOR YOU.', 'micro'); footer.addWidget(self.footer)
        outer.addLayout(footer)
        controller.status.connect(self.update_status)
        controller.userChanged.connect(self.update_user)
        controller.sessionChanged.connect(self.update_session)
        self.update_user(controller.user_index)
        self.tick(); self.clock_timer = QTimer(self); self.clock_timer.timeout.connect(self.tick); self.clock_timer.start(1000)
        if controller.preview: self.footer.setText('DESIGN PREVIEW  ·  AUTHENTICATION DISABLED')

    def tick(self): self.time.setText(datetime.now().strftime('%H:%M   /   %A, %d %B'))

    def update_user(self, index):
        if not self.controller.users: return
        user, look = self.controller.users[index], self.controller.look()
        self.fullname.setText(user['name']); self.username.setText('@'+user['username'])
        blocker = QSignalBlocker(self.user_select); self.user_select.setCurrentIndex(index); del blocker
        palette_file = HERE/'palettes.json' if (HERE/'palettes.json').is_file() else HERE.parent/'theme/palettes.json'
        palettes = json.loads(palette_file.read_text())
        design, mode = look['design'], look['mode']
        self.colors = (palettes if design == 'raw' else palettes[design])[mode]
        self.design, self.mode = design, mode
        self.avatar.load(look['avatar'], user['name'], self.colors['Accent'])
        self.wallpaper = QPixmap(str(look['wallpaper'])) if look['wallpaper'] else QPixmap()
        self.theme_badge.setText('●   '+DESIGNS[design].upper())
        font = 'Inter' if design in ('breakpoint', 'binaryknife', 'tidalglass', 'porcelainink', 'obsidianforge', 'candycloud', 'shadowedge') else 'Noto Sans'
        radius = 3 if design == 'shadowedge' else 26 if design == 'candycloud' else 3 if design == 'obsidianforge' else 2 if design == 'porcelainink' else 7 if design == 'binaryknife' else 16 if design == 'breakpoint' else 28 if design == 'modern' else 20
        p = self.colors
        self.setStyleSheet(f'''
            QWidget {{ color:{p['Text']}; font-family:'{font}'; font-size:14px; background:transparent; }}
            QLabel#brand {{font-size:13px; font-weight:700; color:{p['Accent']};}}
            QLabel#clock {{font-size:13px; color:{p['PlaceholderText']};}}
            QLabel#badge {{font-size:11px; font-weight:700; color:{p['Accent']}; letter-spacing:2px;}}
            QLabel#headline {{font-size:64px; font-weight:300; letter-spacing:-2px;}}
            QLabel#caption {{font-size:17px; color:{p['PlaceholderText']};}}
            QLabel#micro {{font-size:10px; color:{p['PlaceholderText']}; letter-spacing:1px;}}
            QFrame#card {{background:{p['Window']}; border:1px solid {p['Midlight']}; border-radius:{radius}px;}}
            QLabel#greeting {{font-size:12px; color:{p['PlaceholderText']};}}
            QLabel#fullname {{font-size:27px; font-weight:600;}}
            QLabel#username {{font-size:12px; color:{p['PlaceholderText']};}}
            QLabel#fieldLabel {{font-size:10px; font-weight:600; color:{p['PlaceholderText']}; letter-spacing:1px;}}
            QFrame#passwordBox {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:{min(radius,12)}px; min-height:52px;}}
            QLineEdit {{border:0; background:transparent; font-size:15px; selection-background-color:{p['Accent']};}}
            QPushButton#reveal {{background:transparent; border:0; color:{p['PlaceholderText']}; font-size:18px;}}
            QPushButton#reveal:hover {{color:{p['Accent']};}}
            QLabel#message {{font-size:11px; color:{p['PlaceholderText']};}}
            QPushButton#enter {{background:{p['Highlight'] if design in ('tidalglass','porcelainink','obsidianforge','candycloud','shadowedge') else p['Accent']}; color:{p['HighlightedText']}; border:0; border-radius:{min(radius,12)}px; font-size:13px; font-weight:700;}}
            QPushButton#enter:hover {{background:{p['Highlight']};}}
            QPushButton#enter:focus {{border:2px solid {p['Text']};}}
            QPushButton#enter:disabled {{background:{p['Button']}; color:{p['PlaceholderText']};}}
            QComboBox {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:{min(radius,9)}px; padding:10px 13px; font-size:12px;}}
            QComboBox:focus {{border:1px solid {p['Accent']};}}
            QComboBox::drop-down {{border:0; width:28px;}}
            QComboBox QAbstractItemView {{background:{p['Base']}; color:{p['Text']}; selection-background-color:{p['Highlight']}; selection-color:{p['HighlightedText']}; padding:8px;}}
            QLabel#trust {{font-size:10px; color:{p['PlaceholderText']};}}
        ''')
        shadow = QGraphicsDropShadowEffect(self.card); shadow.setBlurRadius(65); shadow.setOffset(0, 18)
        shadow.setColor(QColor(0, 0, 0, 85)); self.card.setGraphicsEffect(shadow)
        self.password.clear(); self.update()

    def update_session(self, index):
        blocker = QSignalBlocker(self.desktop_select); self.desktop_select.setCurrentIndex(index); del blocker

    def update_status(self, phase, message):
        can_type = phase in ('secret', 'visible')
        self.password.setEnabled(can_type); self.reveal.setEnabled(phase == 'secret')
        self.user_select.setEnabled(phase in ('secret', 'visible', 'ready', 'error'))
        self.desktop_select.setEnabled(phase in ('secret', 'visible', 'ready', 'error'))
        self.enter.setEnabled(can_type or phase in ('ready', 'error'))
        if phase in ('busy', 'starting', 'launched', 'error', 'fatal'): self.password.clear()
        self.password.setEchoMode(QLineEdit.EchoMode.Normal if phase == 'visible' else QLineEdit.EchoMode.Password)
        if can_type:
            self.prompt.setText(message.strip().rstrip(':') or 'Password')
            self.password.setPlaceholderText('Enter your password' if phase == 'secret' else 'Enter your response')
            self.message.setText(''); self.password.setFocus()
        elif phase == 'busy': self.message.setText('Checking your account…')
        elif phase == 'ready': self.message.setText('You’re signed in. Your desktop is ready.')
        elif phase in ('starting', 'launched'): self.message.setText('Opening your workspace…')
        else: self.message.setText(message)
        self.enter.setText('Try again   →' if phase == 'error' else 'Opening your workspace…' if phase in ('starting','launched') else 'Enter your workspace   →')
        if phase == 'ready':
            # Continue after authentication without asking for the same password twice.
            QTimer.singleShot(0, lambda: self.controller.submit('') if self.controller.phase == 'ready' else None)

    def submit(self):
        text = self.password.text()
        self.password.clear()
        self.controller.submit(text)
        text = None

    def resizeEvent(self, event):
        compact = self.width() < 1120
        self.hero.setVisible(not compact)
        self.body.setStretch(0, 1 if compact else 0)
        self.body.setStretch(3, 1 if compact else 0)
        self.form.setContentsMargins(30 if compact else 38, 20 if compact else 30, 30 if compact else 38, 20 if compact else 30)
        self.form.setSpacing(6 if compact else 8)
        self.avatar.setFixedSize(96 if compact else 112, 96 if compact else 112)
        self.layout().setContentsMargins(25 if compact else 52, 30, 25 if compact else 52, 25)
        super().resizeEvent(event)

    def closeEvent(self, event):
        if self.controller.preview or self.controller.phase == 'launched': event.accept()
        else: event.ignore()

    def paintEvent(self, _):
        if not hasattr(self, 'colors'): return
        p = QPainter(self); p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect()); c = self.colors
        p.fillRect(rect, QColor(c['Base']))
        if not self.wallpaper.isNull():
            ratio = max(rect.width()/self.wallpaper.width(), rect.height()/self.wallpaper.height())
            target = QRectF(0, 0, self.wallpaper.width()*ratio, self.wallpaper.height()*ratio); target.moveCenter(rect.center())
            p.setOpacity(.1 if self.mode != 'contrast' else .03); p.drawPixmap(target, self.wallpaper, QRectF(self.wallpaper.rect())); p.setOpacity(1)
        glow = QRadialGradient(QPointF(rect.width()*.24, rect.height()*.48), rect.width()*.53)
        color = QColor(c['Accent']); color.setAlpha(27 if self.mode != 'contrast' else 9)
        glow.setColorAt(0, color); color = QColor(c['Accent']); color.setAlpha(0); glow.setColorAt(1, color); p.fillRect(rect, glow)
        if self.hero.isVisible():
            center = QPointF(rect.width()*.28, rect.height()*.47)
            faint = QColor(c['Accent']); faint.setAlpha(28)
            p.setPen(QPen(faint, 1)); p.setBrush(Qt.BrushStyle.NoBrush)
            for radius in (235, 330, 440): p.drawEllipse(center, radius, radius)
            for angle in (25, 150, 290):
                point = center+QPointF(math.cos(math.radians(angle))*330, math.sin(math.radians(angle))*330)
                dot = QColor(c['Accent']); dot.setAlpha(140); p.setBrush(dot); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(point, 3, 3)
                p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(faint, 1))
        # A crisp accent on the frame keeps the sharp themes' identity.
        p.fillRect(QRectF(0, 0, rect.width(), 2), QColor(c['Accent']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', action='store_true', help='Design preview; never authenticates.')
    parser.add_argument('--theme', choices=DESIGNS)
    parser.add_argument('--mode', choices=('dark', 'light', 'contrast'))
    parser.add_argument('--output', type=Path, help='Save a design preview image and exit.')
    parser.add_argument('--width', type=int, default=1600)
    parser.add_argument('--height', type=int, default=1000)
    args = parser.parse_args()
    if args.output and not args.preview: parser.error('--output requires --preview')
    app = QApplication(sys.argv[:1]); app.setApplicationName('Fusion Sign-in')
    QImageReader.setAllocationLimit(96)
    for font_directory in (HERE/'fonts', HERE.parent/'assets/fonts'):
        if font_directory.is_dir():
            for path in font_directory.iterdir():
                if path.suffix in ('.ttf', '.otf'): QFontDatabase.addApplicationFont(str(path))
    controller = Controller(args.preview, args.theme, args.mode)
    windows = []
    def create(screen):
        window = SignIn(controller); windows.append(window)
        if args.preview: window.resize(args.width, args.height); window.show()
        else:
            window.winId(); window.windowHandle().setScreen(screen); window.setGeometry(screen.geometry()); window.showFullScreen()
    if args.preview: create(app.primaryScreen())
    else:
        for screen in app.screens(): create(screen)
        app.screenAdded.connect(create)
    QTimer.singleShot(0, controller.start)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        QTimer.singleShot(350, lambda: (windows[0].grab().save(str(args.output)), app.quit()))
    return app.exec()


if __name__ == '__main__': raise SystemExit(main())

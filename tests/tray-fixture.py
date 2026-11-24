"""A real Qt tray app for the private multi-monitor tray activation check."""
import json
from pathlib import Path
import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QSystemTrayIcon

root = Path(sys.argv[1])
app = QApplication(['fusion-tray-fixture'])
app.setQuitOnLastWindowClosed(False)
windows = {}
state = {'activations': 0, 'context_menus': 0}


def save():
    (root/'app-state.json').write_text(json.dumps(state))


def show(name):
    if name not in windows:
        window = QLabel(name); window.setWindowTitle(name); window.resize(350, 180)
        windows[name] = window
    windows[name].show()


def activated(reason):
    if reason == QSystemTrayIcon.ActivationReason.Trigger:
        state['activations'] += 1
        window = windows.get('Tray owner')
        if window and window.isVisible(): window.hide()
        else: show('Tray owner')
    elif reason == QSystemTrayIcon.ActivationReason.Context:
        state['context_menus'] += 1
    save()


def command():
    path = root/'app-command.json'
    if not path.exists(): return
    data = json.loads(path.read_text()); path.unlink()
    if data['action'] == 'show': show(data['name'])
    elif data['action'] == 'hide': windows[data['name']].hide()
    state['last_command'] = data['id']; save()


icon = QPixmap(24, 24); icon.fill(QColor('#cc66ff'))
tray = QSystemTrayIcon(QIcon(icon)); tray.setToolTip('Fusion tray fixture')
menu = QMenu(); menu.addAction('Fixture menu action')
tray.setContextMenu(menu); tray.activated.connect(activated)
tray.show(); show('Tray owner'); save()
timer = QTimer(); timer.timeout.connect(command); timer.start(30)
sys.exit(app.exec())

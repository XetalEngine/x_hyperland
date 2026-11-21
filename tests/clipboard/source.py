"""Synthetic clipboard source used only in the disposable test compositor."""
import base64
import json
from pathlib import Path
import sys
from PyQt6.QtCore import QByteArray, QMimeData, QTimer
from PyQt6.QtWidgets import QApplication, QLabel

path = Path(sys.argv[1])
app = QApplication([sys.argv[0]])
app.setDesktopFileName('fusion-clipboard-fixture')
window = QLabel('Disposable clipboard source'); window.resize(350, 160); window.show()


def copy():
    data = QMimeData()
    for mime, value in json.loads(path.read_text()).items():
        data.setData(mime, QByteArray(base64.b64decode(value)))
    app.clipboard().setMimeData(data)
    path.with_suffix('.ready').touch()


QTimer.singleShot(500, copy)
app.exec()

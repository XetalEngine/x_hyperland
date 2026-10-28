#!/usr/bin/env python3
"""sudo -A helper. The response is written only to sudo's stdout pipe."""
from pathlib import Path
import sys
from PyQt6.QtWidgets import QApplication, QInputDialog, QLineEdit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'theme'))
import runtime


def main():
    app = QApplication([sys.argv[0]])
    app.setDesktopFileName('xetal-auth')
    runtime.install(app)
    dialog = QInputDialog()
    dialog.setWindowTitle('Administrator authentication')
    dialog.setLabelText(sys.argv[1] if len(sys.argv) > 1 else 'Enter your password to continue:')
    dialog.setTextEchoMode(QLineEdit.EchoMode.Password)
    dialog.setOkButtonText('Authenticate')
    dialog.resize(440, 150)
    if not dialog.exec(): return 1
    sys.stdout.write(dialog.textValue() + '\n')
    sys.stdout.flush()
    return 0


if __name__ == '__main__': raise SystemExit(main())

#!/usr/bin/env python3
"""Standalone Theme window, also used by Dolphin image actions."""
import argparse
import os
from pathlib import Path
import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QMessageBox
from PyQt6.QtCore import QTimer
from PyQt6.QtNetwork import QLocalSocket
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'control_center'))
from app import STYLE, async_run, theme_runtime, ThemePage
from window_chrome import window_controls
import wheel_guard

class ThemeWindow(QWidget):
    def __init__(self,filename=''):
        super().__init__();self.setWindowTitle('Hyprland Theme');self.resize(1100,780);self.setMinimumSize(850,650)
        wheel_guard.install(QApplication.instance())
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.page=ThemePage(async_run,filename);layout.addWidget(self.page);self.page.refresh()
        self.window_controls=window_controls(self,title='Close Theme');self.close_button=self.window_controls.close
        self.page.layout().itemAt(0).layout().addWidget(self.window_controls)
    def closeEvent(self,event):
        if self.page.busy:
            event.ignore();return
        if self.page.dirty and QMessageBox.question(self,'Discard theme edits?','Discard your unsaved theme and wallpaper choices?',
            QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Discard:
            event.ignore();return
        super().closeEvent(event)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('filename',nargs='?',default='');parser.add_argument('--preview');args=parser.parse_args()
    app=QApplication(sys.argv[:1]);app.setApplicationName('hypr-theme');app.setDesktopFileName('hypr-theme');theme_runtime.install(app,STYLE)
    window=ThemeWindow(args.filename);window.show()
    if args.preview:QTimer.singleShot(600,lambda:(window.grab().save(args.preview),app.quit()))
    elif os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        watcher=QLocalSocket(app);watcher.connectToServer(str(Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/os.environ['HYPRLAND_INSTANCE_SIGNATURE']/'.socket2.sock'))
        watcher.readyRead.connect(lambda:watcher.readAll());watcher.disconnected.connect(app.quit)
    return app.exec()

if __name__=='__main__':raise SystemExit(main())

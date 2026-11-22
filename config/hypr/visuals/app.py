#!/usr/bin/env python3
"""Standalone visual controls, glass test surface, and workspace overview."""
import argparse
from pathlib import Path
import sys
from PyQt6.QtCore import Qt,QObject,QThread,pyqtSignal
from PyQt6.QtGui import QColor,QPainter
from PyQt6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLabel,QPushButton
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'theme'))
import runtime


class Worker(QThread):
    result=pyqtSignal(object);error=pyqtSignal(str)
    def __init__(self,fn,parent):super().__init__(parent);self.fn=fn
    def run(self):
        try:self.result.emit(self.fn())
        except Exception as error:self.error.emit(str(error))


class Jobs(QObject):
    def __init__(self,parent):super().__init__(parent);self.workers=set()
    def run(self,fn,done,failed):
        worker=Worker(fn,self);self.workers.add(worker);worker.result.connect(done);worker.error.connect(failed)
        worker.finished.connect(lambda:self.workers.discard(worker));worker.finished.connect(worker.deleteLater);worker.start()


class GlassSample(QWidget):
    def __init__(self):
        super().__init__();self.setWindowTitle('Glass sample · Hyper Fusion');self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint);self.setProperty('xetalOverlay',True);self.resize(600,340)
        layout=QVBoxLayout(self);layout.setContentsMargins(35,35,35,35)
        for text in ('Glass sample','Place this over a wallpaper or a colorful window.','Move or click here to test interactive materials.','Text remains opaque while the background is translucent.'):
            label=QLabel(text);label.setWordWrap(True);label.setStyleSheet('background:transparent;color:white;font-size:18px;');layout.addWidget(label)
        close=QPushButton('Close sample');close.clicked.connect(self.close);layout.addWidget(close)
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor('#76ddd0'));painter.setBrush(QColor(20,30,40,100));painter.drawRoundedRect(self.rect().adjusted(1,1,-1,-1),18,18)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',nargs='?',default='settings',choices=('settings','sample','overview'))
    args=parser.parse_args();app=QApplication(sys.argv[:1]);app.setApplicationName('fusion-'+args.action);app.setDesktopFileName('fusion-'+args.action)
    app.setStyle('Fusion');runtime.install(app)
    jobs=Jobs(app)
    if args.action=='sample':window=GlassSample()
    elif args.action=='overview':
        from visuals.overview import Overview
        window=Overview(jobs.run)
    else:
        sys.path.insert(0,str(ROOT/'control_center'))
        from visuals.appearance import AppearancePage
        window=AppearancePage(jobs.run);window.setWindowTitle('Window appearance · Hyper Fusion');window.resize(1000,780)
        window.refresh()
    screen=app.primaryScreen()
    if screen:
        area=screen.availableGeometry();window.resize(min(window.width(),area.width()-40),min(window.height(),area.height()-40))
    window.show();result=app.exec()
    for worker in tuple(jobs.workers):worker.wait()
    return result


if __name__=='__main__':sys.exit(main())

#!/usr/bin/env python3
"""Native Fusion interface for the bundled, pinned 7-Zip engine."""
from pathlib import Path
import argparse
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'theme'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox
from ui import ArchiveBrowser, CompressDialog, ExtractDialog, JobController
from theme import runtime


def main():
    parser=argparse.ArgumentParser(description='7-Zip · Fusion archive manager')
    parser.add_argument('operation',choices=('open','compress','compress-to','quick-7z','quick-zip','extract','extract-here','extract-folder','test'))
    parser.add_argument('--directory',default='')
    parser.add_argument('paths',nargs='*')
    args=parser.parse_args()
    app=QApplication([sys.argv[0]]); app.setApplicationName('7-Zip · Fusion'); app.setDesktopFileName('xetal-archives')
    runtime.install(app); app.setQuitOnLastWindowClosed(False)
    paths=[os.path.abspath(os.path.expanduser(p)) for p in args.paths]
    directory=args.directory or (str(Path(paths[0]).parent) if paths else str(Path.home()))
    controllers=[]; browsers=[]
    def quit_if_empty():
        if not controllers and not any(browser.isVisible() or browser.pending_drops for browser in browsers): app.quit()
    def launch(request):
        controller=JobController(request,app); controllers.append(controller)
        def release():
            if controller.task.isRunning() or controller not in controllers: return
            controllers.remove(controller)
            if controller.window:controller.window.deleteLater()
            controller.deleteLater();quit_if_empty()
        controller.closed.connect(release)
        if request['operation'] in ('add','delete','rename'):
            controller.completed.connect(lambda result:[browser.reload() for browser in browsers] if result.get('ok') else None)
    def start():
        if args.operation=='open':
            if not paths:
                chosen,_=QFileDialog.getOpenFileNames(None,'Open archives',directory,'Archives and disk images (*)')
                if not chosen:app.quit();return
                paths.extend(chosen)
            for path in paths:
                browser=ArchiveBrowser(path); browser.launch.connect(launch); browsers.append(browser); browser.show()
            watcher=QTimer(app); watcher.setInterval(500); watcher.timeout.connect(quit_if_empty); watcher.start(); app.archive_watcher=watcher
            return
        if not paths:
            QMessageBox.information(None,'7-Zip','Select files in Fusion Files or on the desktop, then choose 7-Zip.');app.quit();return
        if args.operation in ('compress','compress-to'):
            output=None
            if args.operation=='compress-to':
                output,_=QFileDialog.getSaveFileName(None,'Compress to',str(Path(directory)/(Path(paths[0]).name+'.7z')),'Archives (*)',options=QFileDialog.Option.DontConfirmOverwrite)
                if not output:app.quit();return
            dialog=CompressDialog(paths,directory,output)
            if dialog.exec()!=QDialog.DialogCode.Accepted:app.quit();return
            request=dialog.request(); dialog.password.clear();dialog.confirm.clear()
        elif args.operation.startswith('quick-'):
            kind=args.operation.split('-',1)[1]
            request=dict(operation='compress',sources=paths,output=str(Path(directory)/(Path(paths[0]).name+'.'+kind)),options=dict(format=kind))
        elif args.operation=='extract':
            dialog=ExtractDialog(paths,directory)
            if dialog.exec()!=QDialog.DialogCode.Accepted:app.quit();return
            request=dialog.request()
        elif args.operation in ('extract-here','extract-folder'):
            request=dict(operation='extract',sources=paths,destination=directory,separate=args.operation=='extract-folder')
        else:request=dict(operation='test',sources=paths)
        launch(request)
    QTimer.singleShot(0,start)
    return app.exec()


if __name__=='__main__':raise SystemExit(main())

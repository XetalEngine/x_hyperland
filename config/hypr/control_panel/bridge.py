#!/usr/bin/env python3
"""Small desktop adapters for the native Control Panel."""
import json
import os
from pathlib import Path
import shlex
import sys
ROOT=Path(__file__).resolve().parents[1]


def theme():
    sys.path.insert(0,str(ROOT/'theme'))
    import runtime
    from designs import qt_style
    design=runtime.widget_design();p=runtime.colors();style=qt_style(p,design)+runtime.layouts.stylesheet(p,runtime.layout(),runtime.design())
    style+=f'''
      QWidget#hyperControlPanel, QScrollArea, QStackedWidget {{background:{p['Window']};}}
      QWidget#hyperControlPanel {{border:1px solid {p['Midlight']}; border-radius:{4 if design=='binaryknife' else 12 if design=='breakpoint' else 16}px;}}
      QFrame#panelHeader {{background:transparent; border:none;}}
      QLabel#panelTitle {{font-size:21px; font-weight:600; padding:8px 0; color:{p['Text']};}}
      QFrame#ramMetric, QFrame#ramMode {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:8px;}}
      QFrame#ramMode[selected="true"] {{border-color:{p['Accent']};}}
      QWidget#ramCleanerTab QRadioButton::indicator {{width:16px; height:16px; border:1px solid {p['PlaceholderText']}; border-radius:8px; background:{p['Base']};}}
      QWidget#ramCleanerTab QRadioButton::indicator:checked {{background:{p['Highlight']}; border:2px solid {p['Accent']};}}
      QLabel[ramValue="true"] {{font-size:22px; font-weight:600; color:{p['Accent']};}}
      QPushButton#ramCleanButton {{background:{p['Highlight']}; color:{p['HighlightedText']}; font-weight:600; padding:10px 22px;}}
      QPushButton#ramCleanButton:disabled {{background:{p['AlternateBase']}; color:{p['Disabled']};}}
      QGroupBox {{padding:8px; margin-top:16px; border:1px solid {p['Midlight']};}}
      QGroupBox::title {{color:{p['PlaceholderText']}; padding:0 6px;}}
      QTabWidget::pane {{border:none;}}
      QTableWidget, QTreeWidget {{font-size:12px;}}
      QFrame#filterGroupBox {{background:{p['AlternateBase']}; border:1px solid {p['Midlight']}; border-radius:6px;}}
      QSpinBox#minSizeSpinBox {{padding:3px 8px; min-height:22px;}}
      QLabel#driveSummary {{color:{p['PlaceholderText']};}}
      QTreeWidget#drivesTable {{font-size:13px;}}
      QTreeWidget#drivesTable::item {{padding:5px 6px; min-height:22px;}}
      QTableView::item {{padding:4px 6px;}}
      QPushButton[panelCellAction="true"] {{padding:4px 8px; min-height:22px;}}
      QTreeWidget#cleanCategoryTree, QTreeWidget#cleanSizeTree {{font-size:14px;}}
      QTreeWidget#cleanCategoryTree::item, QTreeWidget#cleanSizeTree::item {{padding:3px 6px; min-height:18px;}}
      QTreeWidget#cleanCategoryTree::indicator {{width:18px; height:18px;}}
      QTreeWidget#diskTree, QTreeWidget#diskFolderPicker {{font-size:13px;}}
      QTreeWidget#diskTree::item, QTreeWidget#diskFolderPicker::item {{padding:5px 3px; min-height:20px;}}
      QLabel#diskDetails {{padding:6px 10px; background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:6px;}}
      QAbstractItemView::indicator:unchecked {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:4px; width:16px; height:16px;}}
      QTextEdit#logContentTextEdit {{font-family:"JetBrains Mono", monospace; font-size:12px;}}
      QScrollBar:horizontal {{height:10px; margin:0;}}
      QScrollBar::handle:horizontal {{min-width:28px; min-height:0; background:{p['PlaceholderText']}; border-radius:4px;}}
      QScrollBar::handle:vertical {{min-width:0; min-height:28px;}}
      QScrollBar::handle:horizontal:hover {{background:{p['Accent']};}}
      QPushButton {{padding:6px 10px;}}
    '''
    return {'stylesheet':style,'colors':p,'font':runtime.ui_font(),
            'cardRadius':4 if design=='binaryknife' else 10,
            'iconTheme':'Papirus-Light' if runtime.mode()=='light' else 'Papirus-Dark'}


def shortcut(value):
    # The existing editor supplies working-directory, icon, terminal, hold and floating options.
    sys.path[:0]=[str(ROOT/'launcher'),str(ROOT/'theme')]
    from PyQt6.QtWidgets import QApplication,QDialog,QMessageBox
    from PyQt6.QtCore import QSocketNotifier
    import socket
    import runtime,shortcuts,catalog
    from editor import ShortcutEditor,DIALOG_STYLE
    signature=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE');runtime_dir=os.environ.get('XDG_RUNTIME_DIR')
    if not signature or not runtime_dir:raise ValueError('Open this editor inside Hyprland.')
    connection=socket.socket(socket.AF_UNIX);connection.connect(str(Path(runtime_dir)/'hypr'/signature/'.socket2.sock'));connection.setblocking(False)
    app=QApplication([]);app.setDesktopFileName('xetal-panel-shortcut');runtime.install(app,DIALOG_STYLE)
    import wheel_guard
    wheel_guard.install(app)
    notifier=QSocketNotifier(connection.fileno(),QSocketNotifier.Type.Read)
    def compositor_closed(*_):
        try:
            if connection.recv(65536):return
        except BlockingIOError:return
        except OSError:pass
        app.quit()
    notifier.activated.connect(compositor_closed)
    shell=value.get('shell','bash')
    if shell not in ('bash','zsh','fish','ksh','tcsh','csh'):raise ValueError('Unsupported shortcut shell.')
    fields={'name':value.get('name',''),'command':shlex.join([shell,'-ic',value.get('command','')]).replace('%','%%'),
            'icon':'utilities-terminal','directory':'','description':'Shell shortcut from Control Panel',
            'terminal':True,'keep_open':True,'floating':False}
    entry=shortcuts.Entry('',None,fields,custom=True)
    dialog=ShortcutEditor(entry);dialog.setWindowTitle('Add shortcut to Apps')
    while dialog.exec()==QDialog.DialogCode.Accepted:
        try:
            ident=shortcuts.duplicate(None,dialog.fields);catalog.pin(ident,True)
            break
        except (ValueError,OSError) as error:dialog.error.setText(str(error))
    connection.close();return {'saved':dialog.result()==QDialog.DialogCode.Accepted}


def numlock_startup(data):
    sys.path.insert(0,str(ROOT/'control_center'))
    import desktop_settings as settings
    key = 'input:numlock_by_default'
    if 'enabled' in data:
        if type(data['enabled']) is not bool:
            raise ValueError('Num Lock preference must be true or false.')
        store = settings.Store('input', root=ROOT)
        previous, token = store.load()
        store.save(settings.option_config(previous, {key:data['enabled']}), token)
    value = settings.read_options([key])[key]
    if value not in (0, 1):
        raise ValueError('Could not read the Num Lock startup preference.')
    return {'enabled':bool(value)}


def main():
    action=sys.argv[1] if len(sys.argv)>1 else ''
    try:
        if action=='theme':result=theme()
        else:
            data=json.load(sys.stdin)
            if action in ('aliases','save-aliases'):
                import aliases
                result=aliases.load() if action=='aliases' else aliases.save(data,ROOT/'control_panel/state')
            elif action=='shortcut':result=shortcut(data)
            elif action=='numlock-startup':result=numlock_startup(data)
            elif action=='startup-screen':
                sys.path.insert(0,str(ROOT/'startup'))
                import login_settings
                result={'enabled':login_settings.save(data['enabled']) if 'enabled' in data else login_settings.enabled()}
            else:raise ValueError('Unknown desktop adapter action.')
        print(json.dumps(result,ensure_ascii=False));return 0
    except (OSError,ValueError,KeyError) as error:
        print(json.dumps({'error':str(error)}));return 1
if __name__=='__main__':raise SystemExit(main())

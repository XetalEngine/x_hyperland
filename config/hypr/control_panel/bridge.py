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
      QFrame#debHero {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {p['AlternateBase']},stop:1 {p['Base']}); border:1px solid {p['Midlight']}; border-radius:12px;}}
      QLabel#debEyebrow {{color:{p['Accent']}; font-size:10px; font-weight:600; letter-spacing:2px;}}
      QLabel#debTitle {{color:{p['Text']}; font-size:27px; font-weight:600;}}
      QLabel#debExperimental {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']}; border-radius:6px; padding:5px 12px; font-weight:600;}}
      QLabel#debDescription {{color:{p['Text']};}}
      QLabel#debMuted {{color:{p['PlaceholderText']};}}
      QLabel#debSectionTitle {{font-size:13px; font-weight:600; color:{p['Text']};}}
      QLabel#debCatalogTitle {{font-size:20px; font-weight:600; color:{p['Text']};}}
      QFrame#debHelpers, QFrame#debFeedbackBox {{background:{p['AlternateBase']}; border:1px solid {p['Midlight']}; border-radius:9px;}}
      QPushButton[debPrimary="true"], QPushButton#debFeedbackButton {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']}; font-weight:600; padding:9px 16px;}}
      QPushButton[debPrimary="true"]:hover, QPushButton#debFeedbackButton:hover {{border-color:{p['Text']};}}
      QDialog#debFeedbackDialog {{background:{p['Window']};}}
      QPlainTextEdit#debFeedbackDetails {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:6px; padding:8px;}}
      QLabel#debFeedbackStatus {{color:{p['Accent']};}}
      QFrame#defaultsHero {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {p['AlternateBase']},stop:1 {p['Base']}); border:1px solid {p['Midlight']}; border-radius:{4 if design=='binaryknife' else 14}px;}}
      QLabel#defaultsEyebrow {{font-size:10px; letter-spacing:2px; color:{p['Accent']}; font-weight:600;}}
      QLabel#defaultsTitle {{font-size:28px; font-weight:600; color:{p['Text']};}}
      QLabel#defaultsSubtitle, QLabel#defaultsStatus {{color:{p['PlaceholderText']};}}
      QLabel#defaultsStatus[error="true"] {{color:{p['Text']};}}
      QWidget#defaultAppsTab QToolButton {{padding:9px 16px; border:1px solid {p['Midlight']}; border-radius:6px; color:{p['Text']}; background:{p['Base']};}}
      QWidget#defaultAppsTab QToolButton:checked {{background:{p['Highlight']}; border-color:{p['Accent']}; color:{p['HighlightedText']};}}
      QTreeWidget#defaultsTypes {{font-size:13px; background:{p['Base']}; alternate-background-color:{p['AlternateBase']};}}
      QTreeWidget#defaultsTypes::item {{padding:7px 8px; min-height:24px;}}
      QDialog#defaultAppPicker {{background:{p['Window']};}}
      QLabel#defaultsPickerTitle {{font-size:23px; font-weight:600;}}
      QListWidget#defaultsAppList {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:8px; outline:none;}}
      QListWidget#defaultsAppList::item {{padding:6px 12px; border-radius:5px;}}
      QListWidget#defaultsAppList::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
      QPushButton#defaultsUseApp {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']}; font-weight:600;}}
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
    if design=='tidalglass':
        from tidalglass import gradient
        style+=f'''
          QWidget#hyperControlPanel {{background:{gradient(p)}; border-top-color:{p['Light']}; border-radius:20px;}}
          QScrollArea, QStackedWidget {{background:transparent;}}
          QFrame#defaultsHero, QFrame#ramMetric, QFrame#ramMode, QFrame#filterGroupBox {{background:{gradient(p,'Base','AlternateBase')}; border-top-color:{p['Light']}; border-radius:14px;}}
          QWidget#defaultAppsTab QToolButton {{border-radius:13px;}}
        '''
    if design=='porcelainink':
        from porcelainink import paper
        style+=f'''
          QWidget#hyperControlPanel {{background:{paper(p)}; border-radius:2px;}}
          QScrollArea, QStackedWidget {{background:transparent;}}
          QFrame#defaultsHero, QFrame#ramMetric, QFrame#ramMode, QFrame#filterGroupBox {{background:{p['Base']}; border-radius:2px;}}
          QWidget#defaultAppsTab QToolButton, QListWidget#defaultsAppList, QListWidget#defaultsAppList::item, QLabel#diskDetails {{border-radius:2px;}}
          QLabel#panelTitle, QLabel#defaultsTitle {{font-family:"Noto Serif"; font-weight:500;}}
        '''
    if design=='obsidianforge':
        from obsidianforge import basalt
        style+=f'''
          QWidget#hyperControlPanel {{background:{basalt(p)}; border-radius:3px; border-top-color:{p['Accent']};}}
          QScrollArea, QStackedWidget {{background:transparent;}}
          QFrame#defaultsHero, QFrame#ramMetric, QFrame#ramMode, QFrame#filterGroupBox {{background:{basalt(p,'AlternateBase','Window')}; border-top-color:{p['Light']}; border-radius:3px;}}
          QWidget#defaultAppsTab QToolButton, QListWidget#defaultsAppList, QListWidget#defaultsAppList::item, QLabel#diskDetails {{border-radius:3px;}}
        '''
    if design=='candycloud':
        from candycloud import satin
        style+=f'''
          QWidget#hyperControlPanel {{background:{satin(p)}; border-top-color:{p['Light']}; border-radius:26px;}}
          QScrollArea, QStackedWidget {{background:transparent;}}
          QFrame#defaultsHero, QFrame#ramMetric, QFrame#ramMode, QFrame#filterGroupBox {{background:{satin(p,'Button','Window')}; border-top-color:{p['Light']}; border-radius:20px;}}
          QWidget#defaultAppsTab QToolButton, QListWidget#defaultsAppList, QListWidget#defaultsAppList::item, QLabel#diskDetails {{border-radius:15px;}}
        '''
    if design == 'infernalencore':
        from infernalencore import files_style
        style += files_style(p)
    if design == 'midnightrun':
        from midnightrun import files_style
        style += files_style(p)
    if design == 'platform95':
        from platform95 import files_style
        style += files_style(p)
    if design == 'mycelium':
        from mycelium import files_style
        style += files_style(p)
    if design == 'atomicafterglow':
        from atomicafterglow import files_style
        style += files_style(p)
    if design == 'blackwood':
        from blackwood import files_style
        style += files_style(p)
    if design == 'midnighttransit':
        from midnighttransit import files_style
        style += files_style(p)
    if design == 'hyperfusionblue':
        from hyperfusionblue import steel, blue
        style += f'''QMainWindow,QWidget#filesBody,QWidget#hyperControlPanel,QToolBar,QFrame#addressRow {{background:{steel(p)};}}
        QGroupBox#drivePartitionCard,QFrame#defaultsHero,QFrame#ramMetric,QFrame#ramMode,QFrame#filterGroupBox {{background:{steel(p)};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:8px;}}
        QTreeWidget#places {{background:{p['Window']};border-right:1px solid {p['Midlight']};}}
        QTreeWidget#places::item:selected,QTabBar::tab:selected {{background:{blue(p)};color:{p['HighlightedText']};border:1px solid {p['Accent']};border-radius:5px;}}
        QFrame#pickerActions,QStatusBar {{background:{p['Window']};border-top:1px solid {p['Midlight']};}}'''
    if design=='gildedhollow':
        from gildedhollow import stone
        style+=f'''QWidget#hyperControlPanel {{background:{stone(p)};border:1px solid {p['Light']};border-top-color:{p['Link']};border-radius:17px;}}
          QFrame#defaultsHero,QFrame#ramMetric,QFrame#ramMode,QFrame#filterGroupBox {{background:{stone(p)};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:16px;}}'''
    if design=='hollowgrove':
        from hollowgrove import glass
        style+=f'''QWidget#hyperControlPanel {{background:{glass(p)};border:1px solid {p['Midlight']};border-radius:19px;}}
          QFrame#defaultsHero,QFrame#ramMetric,QFrame#ramMode,QFrame#filterGroupBox {{background:{glass(p)};border-radius:17px;}}'''
    if design=='shadowedge':
        from shadowedge import smoke
        style+=f'''
          QWidget#hyperControlPanel {{background:{smoke(p)}; border-top-color:{p['Link']}; border-radius:3px;}}
          QScrollArea, QStackedWidget {{background:transparent;}}
          QFrame#defaultsHero, QFrame#ramMetric, QFrame#ramMode, QFrame#filterGroupBox {{background:{smoke(p)}; border-top-color:{p['Light']}; border-radius:3px;}}
          QWidget#defaultAppsTab QToolButton, QListWidget#defaultsAppList, QListWidget#defaultsAppList::item, QLabel#diskDetails {{border-radius:2px;}}
        '''
    return {'stylesheet':style,'colors':p,'font':runtime.ui_font(),
            'cardRadius':5 if design=='infernalencore' else 7 if design=='midnightrun' else 1 if design=='platform95' else 12 if design=='mycelium' else 5 if design in ('blackwood','atomicafterglow') else 7 if design=='midnighttransit' else 9 if design=='hyperfusionblue' else 17 if design=='gildedhollow' else 18 if design=='hollowgrove' else 3 if design=='shadowedge' else 24 if design=='candycloud' else 3 if design=='obsidianforge' else 2 if design=='porcelainink' else 16 if design=='tidalglass' else 4 if design=='binaryknife' else 10,
            **runtime.icon_library.info(runtime.ROOT.parent,runtime.design(),runtime.mode())}


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

#!/usr/bin/env python3
"""Read the desktop's existing palette, typography and shape choices."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'theme'))
import runtime
from designs import qt_style

def appearance():
    p = runtime.colors()
    design = runtime.widget_design()
    radius = 3 if design == 'binaryknife' else 8 if design == 'breakpoint' else 10
    style = qt_style(p, design) + runtime.layouts.stylesheet(p, runtime.layout(), runtime.design())
    style += f'''
    QMainWindow, QWidget#filesBody, QTabWidget::pane {{background:{p['Window']}; border:none;}}
    QToolBar {{background:{p['Window']}; border:none; spacing:5px; padding:8px;}}
    QToolButton {{padding:6px; border-radius:{radius}px;}}
    QToolButton:checked {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QTreeWidget#places {{background:{p['Window']}; border:none; padding:8px 4px; outline:none;}}
    QTreeWidget#places::item {{min-height:30px; padding:2px 6px; border-radius:{radius}px;}}
    QTreeWidget#places::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QTreeView#details, QListView#files, QListWidget#driveCards {{background:{p['Base']}; border:none; outline:none;}}
    QTreeView#details::item {{min-height:28px; padding:2px 5px;}}
    QTreeView#details::item:selected, QListView#files::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QHeaderView::section {{background:{p['Window']}; color:{p['Text']}; border:none; border-bottom:1px solid {p['Midlight']}; padding:8px;}}
    QWidget#computerPage {{background:{p['Base']};}}
    QLabel#computerTitle {{font-size:25px; font-weight:600; padding:8px 2px;}}
    QLabel#muted {{color:{p['PlaceholderText']};}}
    QLineEdit#folderFilter {{min-width:120px; max-width:220px; padding:7px 10px;}}
    QFrame#addressRow {{background:{p['Window']}; border-bottom:1px solid {p['Midlight']};}}
    QStatusBar {{background:{p['Window']}; border-top:1px solid {p['Midlight']}; padding:3px;}}
    QSplitter::handle {{background:{p['Midlight']}; width:1px;}}
    QTabBar::tab {{padding:9px 18px; min-width:90px;}}
    QTabBar::tab:selected {{border-bottom:2px solid {p['Accent']};}}
    QScrollArea#filePreview {{background:{p['Base']}; border:none;}}
    '''
    return dict(colors=p, stylesheet=style, font=runtime.ui_font(),
                iconTheme='Papirus-Light' if runtime.mode() == 'light' else 'Papirus-Dark')

if __name__ == '__main__':
    print(json.dumps(appearance()))

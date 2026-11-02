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
    QToolButton#previewToggle, QToolButton#newTabButton {{padding:0; margin:0; border:none; background:transparent;}}
    QToolButton#previewToggle:hover, QToolButton#newTabButton:hover {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QToolButton#previewToggle:focus, QToolButton#newTabButton:focus {{border:1px solid {p['Accent']};}}
    QTreeWidget#places {{background:{p['Window']}; border:none; padding:8px 4px; outline:none;}}
    QTreeWidget#places::item {{min-height:30px; padding:2px 6px; border-radius:{radius}px;}}
    QTreeWidget#places::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QTreeView#details, QListView#files, QListWidget#driveCards {{background:{p['Base']}; border:none; outline:none;}}
    QTreeView#details::item {{min-height:28px; padding:2px 5px;}}
    QTreeView#details::item:selected, QListView#files::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QHeaderView::section {{background:{p['Window']}; color:{p['Text']}; border:none; border-bottom:1px solid {p['Midlight']}; padding:8px;}}
    QWidget#computerPage {{background:{p['Base']};}}
    QScrollArea#mountedDrives, QWidget#mountedDriveRows, QWidget#mountedDiskGroup {{background:{p['Base']}; border:none;}}
    QLabel#computerTitle {{font-size:25px; font-weight:600; padding:8px 2px;}}
    QLabel#driveSectionTitle {{font-size:14px; font-weight:600; padding:4px 2px;}}
    QLabel#driveRowTitle {{font-weight:600; padding:4px 6px 0 6px;}}
    QLabel#driveRowDescription {{color:{p['PlaceholderText']}; padding:0 6px;}}
    QLabel#muted {{color:{p['PlaceholderText']};}}
    QLineEdit#folderFilter {{min-width:120px; max-width:220px; padding:7px 10px;}}
    QFrame#addressRow {{background:{p['Window']}; border-bottom:1px solid {p['Midlight']};}}
    QStatusBar {{background:{p['Window']}; border-top:1px solid {p['Midlight']}; padding:3px;}}
    QSplitter::handle {{background:{p['Midlight']}; width:1px;}}
    QSplitter#driveSections::handle {{background:{p['Window']}; border-top:1px solid {p['Midlight']}; border-bottom:1px solid {p['Midlight']};}}
    QSplitter#driveSections::handle:hover {{background:{p['Highlight']};}}
    QDialog#driveProperties {{background:{p['Window']};}}
    QLabel#volumeArtwork {{background:{p['AlternateBase']}; border:1px solid {p['Midlight']}; border-radius:{radius+4}px;}}
    QLabel#volumeHeading {{font-size:22px; font-weight:600;}}
    QLabel#volumeStatus, QLabel#usageHint, QLabel[muted="true"] {{color:{p['PlaceholderText']};}}
    QLabel#usageHint {{font-size:11px; padding:0 3px;}}
    QLabel[exactBytes="true"] {{font-size:11px;}}
    QFrame#storageSummary {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {p['AlternateBase']},stop:1 {p['Base']}); border:1px solid {p['Midlight']}; border-radius:{radius+4}px;}}
    QFrame#capacityRow {{background:transparent; border:none; border-top:1px solid {p['Midlight']};}}
    QLabel[storageValue="true"] {{font-size:17px; font-weight:600;}}
    QFrame#volumeDetails {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:{radius}px;}}
    QPushButton#systemCleaner {{text-align:left; padding:0; background:{p['Highlight']}; border:1px solid {p['Midlight']}; border-radius:{radius}px;}}
    QPushButton#systemCleaner:hover, QPushButton#systemCleaner:focus {{border-color:{p['Accent']};}}
    QPushButton#systemCleaner:pressed {{background:{p['AlternateBase']};}}
    QPushButton#systemCleaner QLabel {{background:transparent; color:{p['HighlightedText']};}}
    QLabel#cleanerTitle {{font-size:14px; font-weight:600;}}
    QLabel#cleanerDescription {{font-size:11px;}}
    QLabel#cleanerArrow {{font-size:22px;}}
    QTabBar::tab {{padding:9px 18px; min-width:90px;}}
    QTabBar::tab:selected {{border-bottom:2px solid {p['Accent']};}}
    QScrollArea#filePreview {{background:{p['Base']}; border:none;}}
    QLabel#settingsHeading {{font-size:22px; font-weight:600;}}
    QDialog#applicationChooser QLineEdit, QDialog#filesConfiguration QLineEdit {{background:{p['Base']}; color:{p['Text']}; selection-background-color:{p['Highlight']}; selection-color:{p['HighlightedText']}; padding:9px;}}
    QListWidget#applicationList {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:{radius}px; padding:5px;}}
    QListWidget#applicationList::item {{padding:4px 10px; border-radius:{radius}px;}}
    QListWidget#applicationList::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QDialog#filesConfiguration QGroupBox {{padding:18px 14px 10px; margin-top:15px; border:1px solid {p['Midlight']}; border-radius:{radius}px;}}
    QDialog#filesConfiguration QGroupBox::title {{subcontrol-origin:margin; left:14px; padding:0 5px; color:{p['Accent']};}}
    '''
    return dict(colors=p, stylesheet=style, font=runtime.ui_font(),
                iconTheme='Papirus-Light' if runtime.mode() == 'light' else 'Papirus-Dark')

if __name__ == '__main__':
    print(json.dumps(appearance()))

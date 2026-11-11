#!/usr/bin/env python3
"""Read the desktop's existing palette, typography and shape choices."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'theme'))
import runtime
from designs import qt_style
import selection_marker

def appearance():
    p = runtime.colors()
    design = runtime.widget_design()
    radius = 10 if design=='ghostbusters' else 6 if design=='leviathan' else 12 if design == 'polaris' else 5 if design in ('infernalencore','prisonbreak') else 7 if design == 'midnightrun' else 1 if design in ('platform95','mystery98') else 2 if design == 'shadowedge' else 16 if design == 'candycloud' else 3 if design == 'obsidianforge' else 2 if design == 'porcelainink' else 14 if design == 'tidalglass' else 3 if design == 'binaryknife' else 8 if design == 'breakpoint' else 10
    accent_rgb = ','.join(str(int(p['Accent'][i:i+2], 16)) for i in (1, 3, 5))
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
    QTextEdit#inlineRename {{background:{p['Base']}; color:{p['Text']}; selection-background-color:{p['Highlight']}; selection-color:{p['HighlightedText']}; border:1px solid {p['Accent']}; border-radius:{min(radius, 3)}px; padding:0; margin:0; min-height:0;}}
    QHeaderView::section {{background:{p['Window']}; color:{p['Text']}; border:none; border-bottom:1px solid {p['Midlight']}; padding:8px;}}
    QWidget#computerPage {{background:{p['Base']};}}
    QScrollArea[driveSection="true"], QWidget#driveRows {{background:{p['Base']}; border:none;}}
    /* Let the shared QGroupBox style supply the corners for every theme. */
    QGroupBox[physicalDrive="true"] {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba({accent_rgb},36),stop:1 rgba({accent_rgb},12)); border:1px solid rgba({accent_rgb},135); margin:0; padding:0;}}
    QGroupBox[physicalDrive="true"] QListWidget#driveCards {{background:transparent;}}
    QGroupBox#drivePartitionCard {{background:{p['AlternateBase']}; border:1px solid {p['Midlight']}; margin:0; padding:0;}}
    QGroupBox#drivePartitionCard:hover {{border-color:{p['Accent']};}}
    QGroupBox#drivePartitionCard:selected {{background:{p['Highlight']}; border-color:{p['Accent']};}}
    QLabel#driveSectionTitle {{font-size:14px; font-weight:600; padding:4px 2px;}}
    QLabel#driveRowTitle {{font-weight:600; padding:0;}}
    QLabel#driveRowDescription {{color:{p['PlaceholderText']}; padding:0;}}
    QLabel#muted {{color:{p['PlaceholderText']};}}
    QLineEdit#folderFilter {{min-width:120px; max-width:220px; padding:7px 10px;}}
    QFrame#addressRow {{background:{p['Window']}; border-bottom:1px solid {p['Midlight']};}}
    QWidget#folderMessage {{background:{p['Base']};}}
    QFrame#folderMessageCard {{background:{p['AlternateBase']}; border:1px solid {p['Midlight']}; border-radius:{radius}px;}}
    QLabel#folderMessageHeading {{font-size:20px; font-weight:600;}}
    QLabel#folderMessageExplanation {{color:{p['PlaceholderText']};}}
    QPushButton#folderMessageAction {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']}; padding:9px 18px;}}
    QFrame#administratorAccess {{background:{p['AlternateBase']}; border-bottom:1px solid {p['Accent']};}}
    QWidget#searchPane {{background:{p['Window']};}}
    QFrame#searchBar, QFrame#searchPresetBar {{background:{p['AlternateBase']}; border:1px solid {p['Midlight']}; border-radius:{radius}px;}}
    QLineEdit#fileSearchQuery {{background:{p['Base']}; color:{p['Text']}; padding:9px 12px; font-size:14px; border:1px solid {p['Midlight']}; border-radius:{radius}px;}}
    QLineEdit#fileSearchQuery:focus {{border-color:{p['Accent']};}}
    QPushButton#searchStart {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']}; padding:9px 20px;}}
    QTreeView#searchResults {{background:{p['Base']}; alternate-background-color:{p['AlternateBase']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:{radius}px; outline:none;}}
    QTreeView#searchResults::item {{min-height:29px; padding:2px 7px;}}
    QTreeView#searchResults::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QLabel#searchEmpty {{background:{p['Base']}; color:{p['PlaceholderText']}; border:1px solid {p['Midlight']}; border-radius:{radius}px; padding:24px; font-size:16px;}}
    QLabel#searchScope {{font-weight:600; padding:3px 0;}}
    QLabel#searchStatus {{color:{p['PlaceholderText']};}}
    QDialog#advancedSearchDialog QGroupBox {{padding:20px 12px 12px; margin-top:14px; border:1px solid {p['Midlight']}; border-radius:{radius}px;}}
    QDialog#advancedSearchDialog QGroupBox::title {{subcontrol-origin:margin; left:12px; padding:0 4px; color:{p['Accent']};}}
    QLabel#searchValidation {{color:{p['Accent']};}}
    QLabel#searchPresetStatus {{color:{p['PlaceholderText']};}}
    QPlainTextEdit#searchExtensions {{background:{p['Base']}; color:{p['Text']}; selection-background-color:{p['Highlight']}; selection-color:{p['HighlightedText']}; border:1px solid {p['Midlight']}; border-radius:{radius}px; padding:8px;}}
    QPlainTextEdit#searchExtensions:focus {{border-color:{p['Accent']};}}
    QStatusBar {{background:{p['Window']}; border-top:1px solid {p['Midlight']}; padding:3px;}}
    QFrame#pickerActions {{background:{p['Window']}; border-top:1px solid {p['Midlight']};}}
    QPushButton#pickerAccept {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:1px solid {p['Accent']}; padding:8px 22px; border-radius:{radius}px;}}
    QPushButton#pickerAccept:hover {{background:{p['AlternateBase']};}}
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
    if design == 'tidalglass':
        from tidalglass import gradient
        style += f'''
        QMainWindow, QWidget#filesBody, QToolBar, QFrame#addressRow {{background:{gradient(p)};}}
        QTreeWidget#places {{background:{gradient(p,'Button','Window')}; padding:12px 7px;}}
        QTreeWidget#places::item {{min-height:34px; border:1px solid transparent;}}
        QGroupBox#drivePartitionCard {{background:{gradient(p,'Base','AlternateBase')}; border-top-color:{p['Light']};}}
        QFrame#pickerActions, QStatusBar {{background:{p['AlternateBase']};}}
        QTabBar::tab:selected {{border:1px solid {p['Midlight']}; border-bottom:2px solid {p['Accent']};}}
        '''
    if design == 'porcelainink':
        from porcelainink import paper
        style += f'''
        QMainWindow, QWidget#filesBody, QToolBar, QFrame#addressRow {{background:{paper(p)};}}
        QTreeWidget#places {{background:{p['AlternateBase']}; border-right:1px solid {p['Midlight']};}}
        QGroupBox#drivePartitionCard {{background:{p['Base']};}}
        QLabel#volumeArtwork, QFrame#storageSummary {{border-radius:2px;}}
        QFrame#pickerActions, QStatusBar {{background:{p['AlternateBase']};}}
        '''
    if design == 'obsidianforge':
        from obsidianforge import basalt
        style += f'''
        QMainWindow, QWidget#filesBody, QToolBar, QFrame#addressRow {{background:{basalt(p)};}}
        QTreeWidget#places {{background:{basalt(p,'AlternateBase','Base')}; border-right:1px solid {p['Midlight']};}}
        QGroupBox#drivePartitionCard {{background:{basalt(p)}; border-top-color:{p['Light']};}}
        QFrame#pickerActions, QStatusBar {{background:{p['Base']}; border-top:1px solid {p['Midlight']};}}
        QLabel#volumeArtwork, QFrame#storageSummary {{border-radius:3px;}}
        '''
    if design == 'candycloud':
        from candycloud import satin
        style += f'''
        QMainWindow, QWidget#filesBody, QToolBar, QFrame#addressRow {{background:{satin(p)};}}
        QTreeWidget#places {{background:{satin(p,'Button','Window')}; padding:12px 7px;}}
        QTreeWidget#places::item {{min-height:34px; border:1px solid transparent;}}
        QGroupBox#drivePartitionCard {{background:{satin(p,'Button','AlternateBase')}; border-top-color:{p['Light']};}}
        QFrame#pickerActions, QStatusBar {{background:{p['AlternateBase']};}}
        QTabBar::tab:selected {{border:1px solid {p['Midlight']}; border-top-color:{p['Accent']}; border-radius:15px;}}
        '''
    if design == 'prisonbreak':
        from prisonbreak import files_style
        style += files_style(p)
    elif design == 'infernalencore':
        from infernalencore import files_style
        style += files_style(p)
    if design == 'midnightrun':
        from midnightrun import files_style
        style += files_style(p)
    if design == 'ghostbusters':
        from ghostbusters import files_style
        style += files_style(p)
    elif design == 'leviathan':
        from leviathan import files_style
        style += files_style(p)
    if design == 'polaris':
        from polaris import files_style
        style += files_style(p)
    if design == 'mystery98':
        from mystery98 import files_style
        style += files_style(p)
    elif design == 'platform95':
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
    if design == 'gildedhollow':
        from gildedhollow import stone
        style += f'''QMainWindow,QWidget#filesBody,QToolBar,QFrame#addressRow {{background:{stone(p)};}}
        QGroupBox#drivePartitionCard {{background:{stone(p)};border:1px solid {p['Midlight']};border-top-color:{p['Light']};border-radius:16px;}}
        QTreeWidget#places {{background:{p['Window']};border-right:1px solid {p['Midlight']};}}
        QFrame#pickerActions,QStatusBar {{background:{p['Window']};border-top:1px solid {p['Midlight']};}}
        QTabBar::tab:selected {{background:{p['Highlight']};border:1px solid {p['Accent']};border-top-color:{p['Link']};border-radius:9px;}}'''
    if design == 'hollowgrove':
        from hollowgrove import glass
        style += f'''QMainWindow,QWidget#filesBody,QToolBar,QFrame#addressRow {{background:{glass(p)};}}
        QGroupBox#drivePartitionCard {{background:{glass(p)};border:1px solid {p['Midlight']};border-radius:18px;}}
        QTreeWidget#places {{background:{p['Window']};border-right:1px solid {p['Midlight']};}}
        QTabBar::tab:selected {{background:{p['Highlight']};border:1px solid {p['Accent']};border-radius:12px;}}'''
    if design == 'shadowedge':
        from shadowedge import smoke
        style += f'''
        QMainWindow, QWidget#filesBody, QToolBar, QFrame#addressRow {{background:{smoke(p)};}}
        QTreeWidget#places {{background:{smoke(p,'AlternateBase','Window')}; padding:10px 7px; border-right:1px solid {p['Midlight']};}}
        QTreeWidget#places::item {{min-height:32px; border:1px solid transparent;}}
        QTreeWidget#places::item:selected {{background:{p['Highlight']}; border-top-color:{p['Light']};}}
        QGroupBox#drivePartitionCard {{background:{smoke(p)}; border-top-color:{p['Light']};}}
        QFrame#pickerActions, QStatusBar {{background:{p['Base']}; border-top:1px solid {p['Midlight']};}}
        QLabel#volumeArtwork, QFrame#storageSummary {{border-radius:2px;}}
        QTabBar::tab:selected {{background:{p['Highlight']}; border-top-color:{p['Link']}; border-bottom:2px solid {p['Accent']}; border-radius:1px;}}
        '''
    style += selection_marker.stylesheet(p, runtime.selection_marker())
    return dict(colors=p, stylesheet=style, font=runtime.ui_font(),
                **runtime.icon_library.info(runtime.ROOT.parent,runtime.design(),runtime.mode()))

if __name__ == '__main__':
    print(json.dumps(appearance()))

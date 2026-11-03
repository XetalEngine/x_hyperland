"""Presentation tokens shared by the Xetal designs."""
import colorsys
from pathlib import Path

DESIGNS = {'raw': 'Xetal Raw', 'modern': 'Xetal Modern', 'breakpoint': 'BreakPoint', 'binaryknife': 'Binary Knife',
           'tidalglass': 'Tidal Glass', 'porcelainink': 'Porcelain Ink', 'obsidianforge': 'Obsidian Forge'}
DESCRIPTIONS = {'raw': 'Original layout · cyan accents', 'modern': 'Soft cards · blue accents',
                'breakpoint': 'Charcoal glass · crimson focus', 'binaryknife': 'Sharp graphite · electric blue',
                'tidalglass': 'Pearl glass · luminous ocean depths',
                'porcelainink': 'Warm porcelain · charcoal & vermilion',
                'obsidianforge': 'Machined basalt · molten copper & embers'}
COLLECTIONS = {'xetal-world': ('Xetal World', ('raw', 'modern', 'breakpoint', 'binaryknife')),
               'atmospheres': ('Atmospheres', ('tidalglass', 'porcelainink', 'obsidianforge'))}
# Every built-in skin starts dark, including future additions to the catalog.
DEFAULT_MODES = {design: 'dark' for design in DESIGNS}


def recolor(color, palette, mode):
    rgb = tuple(int(color[i:i+2], 16) / 255 for i in (1, 3, 5))
    hue, light, saturation = colorsys.rgb_to_hls(*rgb)
    # Keep destructive/error colors recognizable, including in light mode.
    if saturation > .25 and (hue < .11 or hue > .88) and light > .3:
        return '#b53351' if mode == 'light' else '#efabb9'
    if .32 < hue < .69 and saturation > .25 and light > .45:
        return palette['Accent']
    if light > .82:
        return palette['Text']
    if light > .48:
        return palette['PlaceholderText']
    if light > .27:
        return palette['Midlight']
    if light > .17:
        return palette['Button']
    if light > .085:
        return palette['Window']
    return palette['Base']


def qt_style(p,style='modern'):
    if style=='obsidianforge':
        from obsidianforge import qt_style as themed
        return themed(p)
    if style=='porcelainink':
        from porcelainink import qt_style as themed
        return themed(p)
    if style=='tidalglass':
        from tidalglass import qt_style as themed
        return themed(p)
    if style=='binaryknife':
        from binaryknife import qt_style as themed
        return themed(p)
    if style=='breakpoint':
        from breakpoint import qt_style as themed
        return themed(p)
    ink=p['HighlightedText']
    bright=sum(int(ink[i:i+2],16) for i in (1,3,5))>420
    check=Path(__file__).resolve().parent/'assets'/('check-light.svg' if bright else 'check-dark.svg')
    return f'''
    QWidget {{color:{p['Text']}; font-family:"Noto Sans";}}
    QMainWindow, QDialog, QMessageBox, QWidget#controlRoot {{background:{p['Window']};}}
    QLabel {{background:transparent;}}
    QLabel#brand, QLabel#title {{color:{p['WindowText']}; font-weight:700; letter-spacing:0px;}}
    QLabel#eyebrow {{color:{p['Accent']}; letter-spacing:1px;}}
    QLabel#muted, QLabel#message {{color:{p['PlaceholderText']};}}
    QLabel#section {{font-size:19px; font-weight:600;}}
    QLabel#status {{background:{p['AlternateBase']}; color:{p['Link']}; border:none; border-radius:10px; padding:10px 12px;}}
    QPushButton {{background:{p['Button']}; color:{p['ButtonText']}; border:1px solid transparent; border-radius:10px; padding:8px 13px;}}
    QPushButton:hover {{background:{p['Mid']}; border-color:{p['Midlight']};}}
    QPushButton:focus {{border:1px solid {p['Accent']}; padding:8px 13px;}}
    QPushButton:checked, QPushButton#primary {{background:{p['Highlight']}; color:{p['HighlightedText']}; border-color:{p['Highlight']}; font-weight:600;}}
    QPushButton#primary:hover {{background:{p['Link']}; border-color:{p['Link']};}}
    QPushButton#share, QPushButton#format:checked {{background:{p['Highlight']}; color:{p['HighlightedText']}; border-color:{p['Highlight']};}}
    QPushButton#share:disabled {{background:{p['AlternateBase']}; color:{p['Disabled']}; border-color:{p['Midlight']};}}
    QPushButton:disabled {{color:{p['Disabled']}; background:{p['AlternateBase']}; border-color:transparent;}}
    QPushButton#danger, QPushButton#logout {{background:#4b2935; color:#ffe0e6; border-color:#8d4f61;}}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{background:{p['Base']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:9px; padding:8px 10px; selection-background-color:{p['Highlight']}; selection-color:{p['HighlightedText']};}}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{border-color:{p['Accent']};}}
    QComboBox::drop-down {{border:none; width:24px;}}
    QComboBox QAbstractItemView {{background:{p['Button']}; color:{p['Text']}; selection-background-color:{p['Highlight']}; selection-color:{p['HighlightedText']}; border:1px solid {p['Midlight']}; padding:5px;}}
    QGroupBox {{background:{p['AlternateBase']}; border:1px solid transparent; border-radius:15px; margin-top:18px; padding:15px 12px 12px;}}
    QGroupBox::title {{subcontrol-origin:margin; left:13px; padding:0 5px; color:{p['PlaceholderText']}; font-weight:600;}}
    QSlider, QRadioButton {{background:transparent;}}
    QGroupBox QLineEdit, QGroupBox QComboBox, QGroupBox QSpinBox, QGroupBox QDoubleSpinBox {{background:{p['Base']};}}
    QGroupBox#bindingInspector {{padding-top:8px; padding-bottom:8px;}}
    QGroupBox#bindingInspector QLineEdit, QGroupBox#bindingInspector QComboBox {{padding:6px 10px;}}
    QTabWidget::pane {{border:none; background:transparent;}}
    QTabBar::tab {{background:{p['AlternateBase']}; color:{p['PlaceholderText']}; border:none; border-radius:9px; padding:9px 14px; margin:2px 3px 8px 0;}}
    QTabBar::tab:selected {{background:{p['Highlight']}; color:{p['HighlightedText']}; border:none;}}
    QTabBar::tab:hover {{background:{p['Mid']}; color:{p['Text']};}}
    QTableWidget {{background:{p['Base']}; alternate-background-color:{p['AlternateBase']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:12px; gridline-color:transparent; selection-background-color:{p['Highlight']}; selection-color:{p['HighlightedText']};}}
    QTableWidget::item {{border:none; padding:7px;}}
    QTableWidget::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QHeaderView::section, QTableCornerButton::section {{background:{p['Button']}; color:{p['PlaceholderText']}; border:none; padding:10px 8px;}}
    QScrollArea {{border:none; background:transparent;}}
    QScrollBar:vertical {{background:transparent; width:7px; margin:4px 0;}}
    QScrollBar:horizontal {{background:transparent; height:7px; margin:0 4px;}}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{background:{p['Midlight']}; border-radius:3px; min-height:28px; min-width:28px;}}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{height:0;}}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{width:0;}}
    QScrollBar::add-page, QScrollBar::sub-page {{background:transparent;}}
    QSplitter::handle {{background:transparent;}}
    QCheckBox {{spacing:9px; background:transparent;}}
    QCheckBox::indicator {{width:16px; height:16px; border:1px solid {p['Midlight']}; border-radius:5px; background:{p['Base']};}}
    QCheckBox::indicator:checked, QTableView::indicator:checked {{image:url("{check}"); background:{p['Highlight']}; border:1px solid {p['Link']}; border-radius:4px; width:16px; height:16px;}}
    QSlider::groove:horizontal {{height:6px; border-radius:3px; background:{p['Midlight']};}}
    QSlider::sub-page:horizontal {{background:{p['Accent']}; border-radius:3px;}}
    QSlider::handle:horizontal {{background:{p['Accent']}; width:14px; margin:-5px 0; border-radius:7px;}}
    QProgressBar {{background:{p['Base']}; color:{p['Text']}; border:none; border-radius:7px; min-height:18px;}}
    QProgressBar::chunk {{background:{p['Highlight']}; border-radius:7px;}}
    QMenu {{background:{p['Window']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:13px; padding:7px;}}
    QMenu::item {{padding:9px 32px; border-radius:8px;}}
    QMenu::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QMenu::separator {{height:1px; background:{p['Midlight']}; margin:6px 10px;}}
    QToolTip {{background:{p['Button']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:7px; padding:7px;}}
    QFrame#audioColumn {{background:{p['AlternateBase']}; border:1px solid {p['Midlight']}; border-radius:16px;}}
    QLabel#audioLevel {{color:{p['Accent']};}}
    QScrollArea#audioScroll, QWidget#audioColumns {{background:transparent;}}
    QSlider::groove:vertical, QSlider::sub-page:vertical {{background:{p['Midlight']}; border-radius:4px;}}
    QSlider::add-page:vertical {{background:{p['Accent']}; border-radius:4px;}}
    QSlider::handle:vertical {{background:{p['Accent']}; border-color:{p['Link']}; border-radius:5px;}}
    QFrame#changes, QFrame#modernCard {{background:{p['AlternateBase']}; border:none; border-radius:16px;}}
    QFrame#modernCard QLabel, QFrame#changes QLabel {{background:transparent;}}
    QWidget#modernRail {{background:{p['AlternateBase']}; border-radius:16px;}}
    QPushButton#railButton {{background:transparent; padding:8px; border-radius:11px; text-align:center;}}
    QPushButton#railButton:hover {{background:{p['Mid']};}}
    QPushButton#railButton:checked {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QPushButton#launcherNav {{background:transparent; text-align:left;}}
    QPushButton#launcherNav:checked {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QPushButton#launcherNav:hover {{background:{p['Mid']};}}
    QLineEdit#appSearch {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-radius:15px; padding:9px 15px; font-size:14px;}}
    '''.rstrip()+'\n'


def waybar_style(p,style='modern'):
    if style=='obsidianforge':
        from obsidianforge import waybar_style as themed
        return themed(p)
    if style=='porcelainink':
        from porcelainink import waybar_style as themed
        return themed(p)
    if style=='tidalglass':
        from tidalglass import waybar_style as themed
        return themed(p)
    if style=='binaryknife':
        from binaryknife import waybar_style as themed
        return themed(p)
    if style=='breakpoint':
        from breakpoint import waybar_style as themed
        return themed(p)
    return f'''
    /* Xetal Modern: the existing workspace, pin and device modules. */
    * {{font-family:"Noto Sans", "FiraCode Nerd Font", sans-serif;}}
    window#waybar {{background:{p['Window']}; color:{p['Text']}; border-bottom:1px solid {p['Midlight']};}}
    #custom-launcher, #custom-keys, #clock, #audio, #new-workspace,
    #workspaces button, #xetal-pins .pin {{border-radius:10px;}}
    #custom-launcher {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    #custom-keys, #clock, #audio, #new-workspace, #xetal-pins .pin {{background:{p['AlternateBase']}; color:{p['Accent']};}}
    #workspaces button {{background:{p['AlternateBase']}; color:{p['PlaceholderText']}; border-bottom-color:transparent;}}
    #workspaces button.active {{background:{p['Highlight']}; color:{p['HighlightedText']}; border-bottom-color:transparent;}}
    #workspaces .taskbar-window.active {{background:alpha({p['Base']},0.2);}}
    #new-workspace:hover, #custom-keys:hover, #xetal-pins .pin:hover {{background:{p['Mid']}; color:{p['Text']};}}
    #workspaces button.workspace-remove {{background:transparent; color:#ec8e9e;}}
    #workspaces button.workspace-remove:hover {{background:#823c50; color:#ffffff;}}
    #pulseaudio-slider highlight {{background:{p['Accent']};}}
    #pulseaudio-slider slider {{background:{p['Accent']};}}
    tooltip, menu {{background:{p['Window']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:12px;}}
    menuitem {{border-radius:8px;}}
    menuitem:hover {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    '''.rstrip()+'\n'


def notification_style(p,style='modern'):
    if style=='obsidianforge':
        from obsidianforge import notification_style as themed
        return themed(p)
    if style=='porcelainink':
        from porcelainink import notification_style as themed
        return themed(p)
    if style=='tidalglass':
        from tidalglass import notification_style as themed
        return themed(p)
    if style=='binaryknife':
        from binaryknife import notification_style as themed
        return themed(p)
    if style=='breakpoint':
        from breakpoint import notification_style as themed
        return themed(p)
    return f'''
    .control-center {{background:{p['Window']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:18px; padding:12px;}}
    .notification {{background:{p['AlternateBase']}; color:{p['Text']}; border:1px solid {p['Midlight']}; border-radius:16px; margin:6px;}}
    .notification-content {{padding:12px;}}
    .notification-default-action {{border-radius:16px;}}
    .notification-action {{background:{p['Button']}; color:{p['Text']}; border-radius:9px; margin:4px;}}
    .notification-action:hover, .notification-default-action:hover {{background:{p['Mid']};}}
    .summary {{color:{p['Text']}; font-weight:700;}}
    .body, .time {{color:{p['PlaceholderText']};}}
    .widget-title, .widget-dnd {{background:{p['AlternateBase']}; border-radius:12px; margin:6px; padding:10px;}}
    .widget-title > button {{background:{p['Highlight']}; color:{p['HighlightedText']}; border-radius:9px;}}
    .close-button {{background:{p['Button']}; color:{p['Text']}; border-radius:12px;}}
    '''.rstrip()+'\n'

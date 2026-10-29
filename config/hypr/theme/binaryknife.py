"""Binary Knife: graphite tooling, precise blue edges and silver labels."""
import re
from pathlib import Path
import breakpoint


def qt_style(p):
    base = breakpoint.qt_style(p)
    base = base.replace(str(Path(__file__).with_name('assets')/'check-breakpoint.svg'),
                        str(Path(__file__).with_name('assets')/'check-binaryknife.svg'))
    base = re.sub(r'border-radius:\d+px', 'border-radius:4px', base)
    return base + f'''
    /* Compact, sharply framed tools inspired by the Binary Knife workstation. */
    QMainWindow, QDialog, QMessageBox, QWidget#controlRoot {{background:{p['Window']};}}
    QLabel#eyebrow {{color:{p['Accent']}; font-family:"JetBrains Mono";}}
    QGroupBox {{background:{p['Window']}; border-color:{p['Midlight']}; border-radius:4px;}}
    QTabBar::tab {{background:{p['Base']}; border:1px solid {p['Midlight']}; border-bottom:2px solid transparent; padding:7px 12px;}}
    QTabBar::tab:selected {{background:{p['Highlight']}; color:{p['Text']}; border-color:{p['Midlight']}; border-bottom-color:{p['Accent']};}}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{border-radius:3px;}}
    QMenu {{background:{p['Window']}; border:1px solid {p['Midlight']}; padding:5px;}}
    QMenu::item {{padding:8px 30px; border:1px solid transparent; border-radius:3px;}}
    QMenu::item:selected {{background:{p['Highlight']}; border:1px solid {p['Accent']};}}
    QToolTip {{background:{p['ToolTipBase']}; border:1px solid {p['Accent']}; border-radius:3px;}}
    QTreeView, QListView {{background:{p['Base']}; alternate-background-color:{p['AlternateBase']}; border:1px solid {p['Midlight']};}}
    QTreeView::item:selected, QListView::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QRadioButton::indicator {{width:14px; height:14px; border:1px solid {p['Midlight']}; border-radius:7px; background:{p['Base']};}}
    QRadioButton::indicator:checked {{background:{p['Accent']}; border:3px solid {p['Highlight']};}}
    QProgressBar {{border:1px solid {p['Midlight']}; border-radius:3px;}}
    QProgressBar::chunk {{background:{p['Accent']}; border-radius:2px;}}
    QSlider::groove:horizontal {{height:4px; border-radius:1px;}}
    QSlider::handle:horizontal {{width:10px; margin:-5px 0; border-radius:2px; background:{p['Accent']};}}
    QPushButton#launcherNav:checked {{border-left:3px solid {p['Accent']};}}
    QPushButton#danger, QPushButton#logout {{background:#35212a; border-color:#8d4f61; color:#ffe0e6;}}
    '''


def waybar_style(p):
    base = re.sub(r'border-radius:\d+px', 'border-radius:3px', breakpoint.waybar_style(p))
    return base + f'''
    /* Binary Knife: sharp blue focus and compact instrumentation. */
    window#waybar {{background:alpha({p['Window']},0.97); border-color:{p['Midlight']};}}
    #custom-launcher, #custom-keys, #new-workspace, #xetal-pins .pin {{border:1px solid {p['Midlight']};}}
    #custom-launcher:hover, #custom-keys:hover, #new-workspace:hover, #xetal-pins .pin:hover {{border-color:{p['Accent']};}}
    #workspaces button.active {{background:{p['Highlight']}; border-bottom:2px solid {p['Accent']};}}
    #pulseaudio-slider highlight {{background:{p['Accent']};}}
    menu {{border-color:{p['Accent']};}}
    '''


def notification_style(p):
    base = re.sub(r'border-radius:\d+px', 'border-radius:4px', breakpoint.notification_style(p))
    return base + f'''
    .notification {{border-left:2px solid {p['Accent']};}}
    .widget-title > button, .notification-action {{border-radius:3px;}}
    '''


def compositor(p):
    return (breakpoint.compositor(p).replace('BreakPoint', 'Binary Knife')
            .replace('breakpointEase', 'binaryKnifeEase').replace('rounding = 12', 'rounding = 4')
            .replace('rounding 12', 'rounding 4').replace('1.8, binaryKnifeEase', '1.6, binaryKnifeEase')
            .replace('general:gaps_in = 8', 'general:gaps_in = 6'))

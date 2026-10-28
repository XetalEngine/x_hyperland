"""Hyprland-only theme environment and live styling for our Qt tools."""
import colorsys
import json
import os
from pathlib import Path
import re
import designs

ROOT = Path(__file__).resolve().parent
STATE = ROOT/'state.json'
MODES = {'dark':'Dark', 'light':'Light', 'contrast':'High contrast'}
DESIGNS = designs.DESIGNS


def state():
    try:
        value=json.loads(STATE.read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def design():
    value=state().get('design','raw')
    return value if value in DESIGNS else 'raw'


def mode():
    try:
        value = json.loads(STATE.read_text())['mode']
        return value if value in MODES else 'dark'
    except (OSError, ValueError, KeyError): return 'dark'


def colors(value=None,style=None):
    palettes=json.loads((ROOT/'palettes.json').read_text())
    if (style or design())=='modern':palettes=palettes['modern']
    return palettes[value or mode()]


def environment(base=None, value=None):
    env = dict(os.environ if base is None else base)
    if not env.get('HYPRLAND_INSTANCE_SIGNATURE'): return env
    for key,subdir,fallback in (('XDG_CONFIG_DIRS','config','/etc/xdg'),
                               ('XDG_DATA_DIRS','data','/usr/local/share:/usr/share')):
        directory=str(ROOT.parent/'desktop'/subdir)
        paths=[directory,*filter(None,env.get(key,fallback).split(':'))]
        env[key]=':'.join(dict.fromkeys(paths))
    value = value or mode()
    paths = [str(ROOT/'qt6'), str(ROOT/'qt5')]
    paths += [p for p in env.get('QT_PLUGIN_PATH','').split(':') if p and p not in paths]
    env.update(QT_QPA_PLATFORMTHEME='xetal', QT_STYLE_OVERRIDE='Fusion', QT_PLUGIN_PATH=':'.join(paths),
               XETAL_THEME_CONFIG=str(STATE), GTK_THEME={'dark':'Adwaita:dark','light':'Adwaita','contrast':'HighContrastInverse'}[value],
               KDE_COLOR_SCHEME_PATH=str(ROOT/'current.colors'))
    return env


def recolor(color, value, style=None):
    if (style or design())=='modern':return designs.recolor(color,colors(value,'modern'),value)
    if value == 'dark': return color
    rgb = tuple(int(color[i:i+2],16)/255 for i in (1,3,5))
    hue, light, sat = colorsys.rgb_to_hls(*rgb)
    lum = .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]
    if value == 'light':
        if lum < .53: light, sat = .985-lum*.30, min(sat,.28)
        else: light, sat = .14+(1-lum)*.4, min(sat,.65)
    else:
        light = .025 if lum < .22 else .12 if lum < .48 else .88
        sat = min(sat,.7)
    return '#'+''.join(f'{round(c*255):02x}' for c in colorsys.hls_to_rgb(hue,light,sat))


def stylesheet(source, value=None, style=None, qt=True):
    value = value or mode()
    style = style or design()
    if value == 'dark' and style=='raw': return source
    source = re.sub(r'#[0-9a-fA-F]{6}\b', lambda m: recolor(m[0],value,style), source)
    def rgba(match):
        r,g,b,alpha = match.groups(); transformed = recolor(f'#{int(r):02x}{int(g):02x}{int(b):02x}',value,style)
        return f'rgba({int(transformed[1:3],16)},{int(transformed[3:5],16)},{int(transformed[5:7],16)},{alpha})'
    source=re.sub(r'rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)',rgba,source)
    return source+(designs.qt_style(colors(value,style)) if style=='modern' and qt else '')


def qcolor(*args):
    from PyQt6.QtGui import QColor
    color=QColor(*args)
    if design()=='modern':
        alpha=color.alpha();color=QColor(recolor(color.name(),mode()));color.setAlpha(alpha)
    return color


def palette(value=None):
    from PyQt6.QtGui import QPalette,QColor
    data = colors(value); result = QPalette(QColor(data['Window']))
    for name,color in data.items():
        role = getattr(QPalette.ColorRole,name,None)
        if role is not None: result.setColor(QPalette.ColorGroup.All,role,QColor(color))
    for name in ['Text','WindowText','ButtonText','PlaceholderText']:
        result.setColor(QPalette.ColorGroup.Disabled,getattr(QPalette.ColorRole,name),QColor(data['Disabled']))
    return result


def style_calendar(widget):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor,QTextCharFormat
    data=colors(); widget.setPalette(palette())
    header=QTextCharFormat(); header.setBackground(QColor(data['Button'])); header.setForeground(QColor(data['WindowText']))
    widget.setHeaderTextFormat(header)
    for day in Qt.DayOfWeek:
        style=QTextCharFormat(); style.setForeground(QColor(data['Link'] if day in (Qt.DayOfWeek.Saturday,Qt.DayOfWeek.Sunday) else data['Text']))
        widget.setWeekdayTextFormat(day,style)


def install(app, source=''):
    from PyQt6.QtCore import QFileSystemWatcher,QObject,pyqtSignal,QTimer,QSettings
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QCalendarWidget
    import window_chrome
    window_chrome.install(app)
    class LiveTheme(QObject):
        changed=pyqtSignal()
        def __init__(self):
            super().__init__(app); self.watcher=QFileSystemWatcher([str(ROOT)],self)
            self.watcher.directoryChanged.connect(self.apply); self.apply()
        def apply(self,*_):
            app.setPalette(palette()); app.setStyleSheet(stylesheet(source))
            QIcon.setThemeSearchPaths([str(Path.home()/'.local/share/icons'),'/usr/share/icons'])
            QIcon.setFallbackThemeName('hicolor'); QIcon.setThemeName('Papirus-Light' if mode()=='light' else 'Papirus-Dark')
            for widget in app.allWidgets():
                if isinstance(widget,QCalendarWidget): style_calendar(widget)
                widget.update()
            self.changed.emit()
    # QFileDialog normally remembers its folder in shared QtProject settings.
    # Keep that UI state inside this profile for our tools as well.
    local=ROOT/'qt-settings'; local.mkdir(exist_ok=True)
    for format in (QSettings.Format.NativeFormat,QSettings.Format.IniFormat):
        QSettings.setPath(format,QSettings.Scope.UserScope,str(local))
    app.setStyle('Fusion'); instance=LiveTheme(); app.hypr_theme=instance
    return instance

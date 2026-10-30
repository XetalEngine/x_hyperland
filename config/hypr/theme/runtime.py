"""Hyprland-only theme environment and live styling for our Qt tools."""
import colorsys
import json
import os
from pathlib import Path
import re
import designs
import layouts

ROOT = Path(__file__).resolve().parent
STATE = ROOT/'state.json'
MODES = {'dark':'Dark', 'light':'Light', 'contrast':'High contrast'}
DESIGNS = designs.DESIGNS
LAUNCHER_STYLES = {'follow':'Follow desktop theme', **DESIGNS}


def state():
    try:
        value=json.loads(STATE.read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def design():
    value=state().get('design','raw')
    return value if value in DESIGNS else 'raw'


def layout():
    value=state().get('layout','follow')
    return value if isinstance(value,str) and value in layouts.LAYOUTS else layouts.default(design())


def widget_design(): return layouts.widget_style(layout(),design())


def launcher_style():
    value=state().get('launcher_style','follow')
    return value if isinstance(value,str) and value in LAUNCHER_STYLES else 'follow'


def launcher_design():
    value=launcher_style()
    return design() if value=='follow' else value


def launcher_wallpaper():
    return state().get('launcher_wallpaper') is True


def launcher_background():
    value=state().get('launcher_background','')
    return value if isinstance(value,str) else ''


def launcher_background_visibility():
    value=state().get('launcher_background_visibility',18)
    return max(0,min(100,value)) if type(value) is int else 18


def launcher_surfaces():
    from launcher_surfaces import normalize
    return normalize(state().get('launcher_surfaces',{}))


def launcher_labels():
    from launcher_labels import normalize
    return normalize(state().get('launcher_labels',{}))


def mode():
    try:
        value = json.loads(STATE.read_text())['mode']
        return value if value in MODES else 'dark'
    except (OSError, ValueError, KeyError): return 'dark'


def colors(value=None,style=None):
    palettes=json.loads((ROOT/'palettes.json').read_text())
    selected=style or design()
    if selected in DESIGNS and selected!='raw':palettes=palettes[selected]
    return palettes[value or mode()]


def ui_font(style=None):
    return 'Inter' if (style or design()) in ('breakpoint','binaryknife') else 'Noto Sans'


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
               FONTCONFIG_FILE=str(ROOT.parent/'assets/fonts.conf'),
               KDE_COLOR_SCHEME_PATH=str(ROOT/'current.colors'))
    modules = [str(ROOT/'gtk3/libxetal-file-preview.so'), *filter(None, env.get('GTK3_MODULES', '').split(':'))]
    env['GTK3_MODULES'] = ':'.join(dict.fromkeys(modules))
    return env


def recolor(color, value, style=None):
    selected=style or design()
    if selected!='raw':return designs.recolor(color,colors(value,selected),value)
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
    explicit=style is not None
    value = value or mode()
    style = style or design()
    if value != 'dark' or style!='raw':
        source = re.sub(r'#[0-9a-fA-F]{6}\b', lambda m: recolor(m[0],value,style), source)
    def rgba(match):
        r,g,b,alpha = match.groups(); transformed = recolor(f'#{int(r):02x}{int(g):02x}{int(b):02x}',value,style)
        return f'rgba({int(transformed[1:3],16)},{int(transformed[3:5],16)},{int(transformed[5:7],16)},{alpha})'
    if value != 'dark' or style!='raw':source=re.sub(r'rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)',rgba,source)
    shape=style if explicit else widget_design()
    # A raw layout still needs a complete stylesheet when its colors come from another palette.
    if shape=='raw' and style!='raw':shape='breakpoint'
    return source+(designs.qt_style(colors(value,style),shape) if shape!='raw' and qt else '')+(layouts.stylesheet(colors(value,style),layout(),style) if qt and not explicit else '')


def qcolor(*args):
    from PyQt6.QtGui import QColor
    color=QColor(*args)
    if design()!='raw':
        alpha=color.alpha();color=QColor(recolor(color.name(),mode()));color.setAlpha(alpha)
    return color


def palette(value=None,style=None):
    from PyQt6.QtGui import QPalette,QColor
    data = colors(value,style); result = QPalette(QColor(data['Window']))
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


def install(app, source='', *, style=None):
    from PyQt6.QtCore import QFileSystemWatcher,QObject,pyqtSignal,QTimer,QSettings
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QCalendarWidget
    import window_chrome
    window_chrome.install(app)
    import file_preview
    file_preview.install(app)
    class LiveTheme(QObject):
        changed=pyqtSignal()
        def __init__(self):
            super().__init__(app); self.watcher=QFileSystemWatcher([str(ROOT)],self)
            self.watcher.directoryChanged.connect(self.apply); self.apply()
        def apply(self,*_):
            selected=style() if callable(style) else style
            # The native palette watcher must respect this process's menu style.
            # An application property is not inherited by programs we launch.
            app.setProperty('xetalThemeDesign',selected)
            app.setPalette(palette(style=selected)); app.setStyleSheet(stylesheet(source,style=selected))
            QIcon.setThemeSearchPaths([str(Path.home()/'.local/share/icons'),'/usr/share/icons'])
            QIcon.setFallbackThemeName('hicolor'); QIcon.setThemeName('Papirus-Light' if mode()=='light' else 'Papirus-Dark')
            for widget in app.allWidgets():
                if isinstance(widget,QCalendarWidget): style_calendar(widget)
                if widget.objectName()=='windowClose':window_chrome.style_close(widget,selected or design())
                widget.update()
            self.changed.emit()
    # QFileDialog normally remembers its folder in shared QtProject settings.
    # Keep that UI state inside this profile for our tools as well.
    local=ROOT/'qt-settings'; local.mkdir(exist_ok=True)
    for format in (QSettings.Format.NativeFormat,QSettings.Format.IniFormat):
        QSettings.setPath(format,QSettings.Scope.UserScope,str(local))
    app.setStyle('Fusion'); instance=LiveTheme(); app.hypr_theme=instance
    return instance

"""Transactional theme/wallpaper settings. Never write shared desktop settings."""
from __future__ import annotations
import configparser
from contextlib import ExitStack
import copy
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'control_center'))
import desktop_settings as settings
import keys
import runtime
import designs
import wallpaper_sets
import effect_colors

ROOT=runtime.ROOT.parent
WALLPAPER=ROOT/'wallpaper'


def read_wallpapers(root=None):
    root=root or WALLPAPER
    state=json.loads((root/'selection.json').read_text())
    if not isinstance(state,dict): raise ValueError('The wallpaper settings need repair; nothing was overwritten.')
    # Include changes made outside the picker instead of showing stale previews.
    try:
        for line in settings.ctl('hyprpaper','listactive').splitlines():
            connector, separator, path = line.partition(': ')
            if separator and Path(path).is_file():
                previous=state.get(connector,{})
                state[connector]={**previous,'path':path,'fit':previous.get('fit','cover'),
                                  'original':previous.get('original',path) if previous.get('path')==path else path}
    except (ValueError,OSError,subprocess.TimeoutExpired): pass
    return state


def wallpaper_config(state):
    lines=['# Managed by Hyprland Theme. KDE is not involved.','ipc = true','splash = false','']
    for connector,item in state.items():
        if not re.fullmatch(r'[\w.:-]+',connector): raise ValueError('Unsupported display connector.')
        if item.get('fit') not in ('cover','contain','fill','tile'): raise ValueError('Unsupported wallpaper fit.')
        if any(c in item['path'] for c in '\n\r#{}'): raise ValueError('Unsafe wallpaper path in saved configuration.')
        lines+=['wallpaper {',f'    monitor = {connector}',f'    path = {item["path"]}',f'    fit_mode = {item["fit"]}','}','']
    return '\n'.join(lines)


def set_wallpaper(connector,item):
    result=settings.ctl('hyprpaper','wallpaper',f'{connector},{item["path"]},{item["fit"]}')
    if 'error' in result.lower() or 'failed' in result.lower(): raise ValueError(result)


def apply_wallpapers(draft, expected):
    from PIL import Image
    settings.STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (settings.STATE/'wallpaper-save.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous=read_wallpapers()
        if previous!=expected: raise ValueError('Wallpapers changed outside this page. Reload before applying.')
        connected={m['name'] for m in settings.monitors() if not m.get('disabled')}
        state=copy.deepcopy(previous); changed=[]
        for connector,choice in draft.items():
            if connector not in connected: raise ValueError(connector+' disconnected. Reload displays before applying.')
            if choice['fit'] not in ('cover','contain','fill','tile'): raise ValueError('Choose a valid wallpaper fit.')
            path=Path(choice['path']).resolve(strict=True)
            with Image.open(path) as picture: picture.verify()
            cache=WALLPAPER/'images'; cache.mkdir(exist_ok=True)
            saved=cache/(hashlib.sha256(path.read_bytes()).hexdigest()[:24]+path.suffix.lower())
            if not saved.exists(): shutil.copyfile(path,saved); saved.chmod(0o600)
            state[connector]={'path':str(saved),'original':choice.get('original',str(path)),'fit':choice['fit']}
        config=wallpaper_config(state)
        files={WALLPAPER/'hyprpaper.conf':config.encode(),WALLPAPER/'selection.json':(json.dumps(state,indent=2)+'\n').encode()}
        files[WALLPAPER/'profiles.json']=wallpaper_sets.encode(wallpaper_sets.remember(WALLPAPER,runtime.state().get('wallpaper_theme',runtime.design()),state))
        oldfiles={path:path.read_bytes() if path.exists() else None for path in files}
        try:
            for connector in draft:
                # Remember the attempted output even when its renderer reports an error.
                changed.append(connector); set_wallpaper(connector,state[connector])
            for path,content in files.items(): keys.atomic_write(path,content)
        except Exception:
            for connector in reversed(changed):
                if connector in previous:
                    try: set_wallpaper(connector,previous[connector])
                    except Exception: pass
            for path,content in oldfiles.items():
                if path.exists() and path.read_bytes()==files[path]:
                    if content is None:path.unlink()
                    else:keys.atomic_write(path,content)
            raise
        return read_wallpapers()


def kde_colors(value,design=None):
    design=design or runtime.design()
    colors=runtime.colors(value,design); cfg=configparser.ConfigParser(interpolation=None); cfg.optionxform=str
    cfg['General']={'Name':runtime.DESIGNS[design]+' '+runtime.MODES[value], 'ColorScheme':'Xetal'+design.title()+value.title()}
    for group in ['Window','View','Button','Selection','Tooltip','Complementary','Header']:
        selected=group=='Selection'; base=colors['Highlight'] if selected else colors['Base'] if group=='View' else colors['Button'] if group in ('Button','Header') else colors['Window']
        foreground=colors['HighlightedText'] if selected else colors['Text']
        values={'BackgroundNormal':base,'BackgroundAlternate':colors['AlternateBase'], 'ForegroundNormal':foreground,
                'ForegroundInactive':colors['Disabled'],'ForegroundActive':colors['Link'],'ForegroundLink':colors['Link'],
                'ForegroundVisited':colors['LinkVisited'],'ForegroundNegative':'#e16e83' if value!='light' else '#b32546',
                'ForegroundNeutral':'#ebc36d' if value!='light' else '#816000','ForegroundPositive':'#7bd9a4' if value!='light' else '#167545',
                'DecorationFocus':colors['Accent'],'DecorationHover':colors['Accent']}
        cfg['Colors:'+group]={key:','.join(str(int(color[i:i+2],16)) for i in (1,3,5)) for key,color in values.items()}
    cfg['ColorEffects:Disabled']={'Enable':'false'}; cfg['ColorEffects:Inactive']={'Enable':'false'}
    output=io.StringIO(); cfg.write(output,space_around_delimiters=False); return output.getvalue().rstrip()+'\n'


def theme_token():
    extra=hashlib.sha256()
    for name in ('hyprlock.conf','startup/kitty.conf','file_jobs/preferences.json','switcher/preferences.json','terminal_fetch/settings.json','effects/burn/settings.conf','effects/cube/settings.json','effects/minimize/settings.conf','effects/wobbly/settings.json','cursors/settings.json','theme/icons.json','sounds/settings.json','control_center/appearance.conf','wallpaper/selection.json','waybar/config.json'):
        path=ROOT/name
        extra.update(path.read_bytes() if path.is_file() else b'missing')
    return settings.Store('theme').load()[1], hashlib.sha256(runtime.STATE.read_bytes()).hexdigest(),extra.hexdigest()


def kitty_colors(value,design=None):
    design=design or runtime.design()
    # Desktop light mode must never turn working terminals white. Use the
    # design's dark palette for both text and ANSI colors so TUIs stay readable.
    if value=='light':value='dark'
    colors=runtime.colors(value,design)
    ansi={
        'dark':['#192130','#ee8196','#78d7b6','#d8ce99','#82aef0','#b7a2e4','#73d4d1','#d1dbec',
                '#70829a','#ff96ad','#9de6c5','#eadeaf','#a5c5fb','#d2baf6','#a5efeb','#eff6ff'],
        'contrast':['#52677a','#ff8ea4','#8aefbd','#ffe199','#a5c5ff','#dbb5ff','#8cfff0','#ffffff',
                    '#bbcbd8','#ffb4c6','#bcffd9','#fff2bb','#d0e0ff','#ecd5ff','#c6fff7','#ffffff']
    }[value]
    options={'background':colors['Base'],'foreground':colors['Text'],
             'cursor':colors['Accent'],'cursor_text_color':colors['Base'],
             'selection_background':colors['Highlight'],'selection_foreground':colors['HighlightedText'],
             'scrollbar_handle_color':colors['Accent'],'url_color':colors['Link'],
             'active_tab_background':colors['Highlight'],'active_tab_foreground':colors['HighlightedText'],
             'inactive_tab_background':colors['Window'],'inactive_tab_foreground':colors['Text'],
             'tab_bar_background':colors['Base'],**{f'color{i}':color for i,color in enumerate(ansi)}}
    font='font_family JetBrains Mono\n' if design in ('breakpoint','binaryknife') else ''
    return '# Managed by Hyprland Theme.\n'+font+''.join(f'{key} {color}\n' for key,color in options.items())


def reload_kitty(proc_root=Path('/proc'),include_startup=False):
    """Reload only terminals using this profile in the current compositor session."""
    session=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    if not session: return []
    profiles={str(ROOT/'kitty.conf').encode()}; marker=b'HYPRLAND_INSTANCE_SIGNATURE='+session.encode()
    if include_startup:profiles.add(str(ROOT/'startup/kitty.conf').encode())
    reloaded=[]
    for item in proc_root.iterdir():
        if not item.name.isdigit(): continue
        try:
            if item.stat().st_uid!=os.getuid() or (item/'comm').read_text().strip()!='kitty': continue
            command=(item/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
            if not command or Path(os.fsdecode(command[0])).name!='kitty': continue
            configs=[command[i+1] for i,arg in enumerate(command[:-1]) if arg in (b'--config',b'-c')]
            configs += [arg.split(b'=',1)[1] for arg in command[1:] if arg.startswith(b'--config=')]
            if not profiles.intersection(configs) or marker not in (item/'environ').read_bytes().split(b'\0'): continue
            os.kill(int(item.name),signal.SIGUSR1); reloaded.append(int(item.name))
        except (OSError,ValueError): continue
    return reloaded


def modern_lock(colors,design='modern'):
    def rgb(name):return 'rgb('+colors[name][1:]+')'
    return f'''# {runtime.DESIGNS[design]}. Authentication and lock shortcuts are unchanged.
$font = {runtime.ui_font(design)}
general {{
    hide_cursor = false
}}
animations {{
    enabled = true
    bezier = linear, 1, 1, 0, 0
    animation = fadeIn, 1, 5, linear
    animation = fadeOut, 1, 5, linear
    animation = inputFieldDots, 1, 2, linear
}}
background {{
    monitor =
    path = screenshot
    blur_passes = 3
}}
input-field {{
    monitor =
    size = 360, 58
    outline_thickness = 2
    inner_color = {rgb('Window')}
    outer_color = {rgb('Accent')}
    check_color = {rgb('Link')}
    fail_color = rgb(ea9bab)
    font_color = {rgb('Text')}
    fade_on_empty = false
    rounding = {3 if design=='shadowedge' else 26 if design=='candycloud' else 3 if design=='obsidianforge' else 2 if design=='porcelainink' else 4 if design=='binaryknife' else 12 if design=='breakpoint' else 18}
    font_family = $font
    placeholder_text = Password
    fail_text = $PAMFAIL$FPRINTFAIL
    dots_spacing = 0.3
    position = 0, -60
    halign = center
    valign = center
}}
label {{
    monitor =
    text = $TIME
    color = {rgb('Text')}
    font_size = 80
    font_family = $font
    position = 0, 130
    halign = center
    valign = center
}}
label {{
    monitor =
    text = cmd[update:60000] date +"%A, %d %B"
    color = {rgb('Link')}
    font_size = 20
    font_family = $font
    position = 0, 55
    halign = center
    valign = center
}}
label {{
    monitor =
    text = $USER
    color = {rgb('Text')}
    font_size = 16
    font_family = $font
    position = 0, -130
    halign = center
    valign = center
}}
label {{
    monitor =
    text = $LAYOUT[en,ru]
    color = {rgb('Link')}
    font_size = 14
    onclick = hyprctl switchxkblayout all next
    position = 0, -175
    halign = center
    valign = center
}}
'''


def prepare_launcher_background(choice):
    """Keep a portable, oriented PNG so moving the original never breaks Apps."""
    from PIL import Image,ImageOps
    source=Path(choice).expanduser()
    if not source.is_absolute():source=runtime.ROOT/source
    try:
        with Image.open(source) as picture:
            output=io.BytesIO()
            ImageOps.exif_transpose(picture).convert('RGBA').save(output,format='PNG')
    except (OSError,ValueError,Image.DecompressionBombError) as error:
        raise ValueError('The Apps background could not be read. Choose another image.') from error
    data=output.getvalue()
    relative='backgrounds/'+hashlib.sha256(data).hexdigest()[:24]+'.png'
    return relative,data


def prepare_group_image(choice):
    """Keep animation frames, timing and transparency when importing strip art."""
    from PIL import Image,ImageOps
    from launcher_surfaces import image_path
    try:
        data=image_path(choice).read_bytes()
        with Image.open(io.BytesIO(data)) as picture:
            if picture.format in ('GIF','WEBP') and getattr(picture,'is_animated',False):
                extension=picture.format.lower()
                for frame in range(picture.n_frames):
                    picture.seek(frame);picture.load()
            else:
                output=io.BytesIO()
                ImageOps.exif_transpose(picture).convert('RGBA').save(output,format='PNG')
                data=output.getvalue();extension='png'
    except (OSError,ValueError,Image.DecompressionBombError) as error:
        raise ValueError('The group-strip image could not be read. Choose another image or GIF.') from error
    return 'backgrounds/group-'+hashlib.sha256(data).hexdigest()[:24]+'.'+extension,data


def apply_mode(value,expected,design=None,avatar=None,launcher_wallpaper=None,launcher_background=None,launcher_surfaces=None,launcher_style=None,launcher_labels=None,launcher_background_visibility=None,*,layout=None,components=None,bundle=None,selection_marker=None,bar_style=None,bar_variant=None):
    if value not in runtime.MODES: raise ValueError('Choose an available theme.')
    design=design or runtime.design()
    if design not in runtime.DESIGNS:raise ValueError('Choose an available desktop design.')
    previous=runtime.state()
    import bar_styles
    bar_style=previous.get('bar_style','follow') if bar_style is None else bar_style
    if not isinstance(bar_style,str) or bar_style not in bar_styles.STYLES:raise ValueError('Choose an available Waybar style.')
    bar_variant=bar_styles.variant(previous.get('bar_variant') if bar_variant is None else bar_variant,bar_styles.resolve(bar_style,design))
    from selection_marker import validate as validate_marker
    selection_marker=validate_marker(runtime.selection_marker() if selection_marker is None else selection_marker)
    if layout is not None and layout not in runtime.layouts.LAYOUTS:raise ValueError('Choose a supported navigation layout.')
    partial=components is not None
    from launcher_labels import normalize as normalize_labels
    labels=normalize_labels(previous.get('launcher_labels',{}) if launcher_labels is None else launcher_labels,strict=True)
    visibility=runtime.launcher_background_visibility() if launcher_background_visibility is None else launcher_background_visibility
    if type(visibility) is not int or not 0<=visibility<=100:raise ValueError('Background visibility must be between 0 and 100%.')
    launcher_style=runtime.launcher_style() if launcher_style is None else launcher_style
    if not isinstance(launcher_style,str) or launcher_style not in runtime.LAUNCHER_STYLES:
        raise ValueError('Choose an available Start menu style or Follow desktop theme.')
    menu_design=design if launcher_style=='follow' else launcher_style
    launcher_wallpaper=previous.get('launcher_wallpaper',False) if launcher_wallpaper is None else launcher_wallpaper
    if not isinstance(launcher_wallpaper,bool):raise ValueError('Choose whether to use a wallpaper behind Apps.')
    launcher_background=previous.get('launcher_background','') if launcher_background is None else launcher_background
    if not isinstance(launcher_background,str) or any(c in launcher_background for c in '\r\n\0'):
        raise ValueError('Choose a valid Apps background image.')
    background_data=None
    if launcher_background and (launcher_wallpaper or launcher_background!=previous.get('launcher_background','')):
        launcher_background,background_data=prepare_launcher_background(launcher_background)
    from launcher_surfaces import normalize
    old_surfaces=normalize(previous.get('launcher_surfaces',{}))
    surfaces=normalize(old_surfaces if launcher_surfaces is None else launcher_surfaces,strict=True)
    group_files={}
    for style,options in surfaces.items():
        choice=options['group_image']
        if choice and (choice!=old_surfaces[style]['group_image'] or (style==menu_design and options['group_opacity']>0)):
            options['group_image'],data=prepare_group_image(choice)
            group_files[runtime.ROOT/options['group_image']]=data
    avatar=previous.get('avatar','auto') if avatar is None else avatar
    if not isinstance(avatar,str) or any(c in avatar for c in '\r\n\0'):
        raise ValueError('Choose a valid account image.')
    if avatar!='auto':
        from PIL import Image
        image=Path(avatar).expanduser()
        if not image.is_absolute():image=runtime.ROOT/image
        with Image.open(image) as picture:picture.verify()
    from build import build
    build()
    store=settings.Store('theme')
    if theme_token()!=expected: raise ValueError('The theme changed elsewhere. Reload before applying.')
    env=runtime.environment({'HYPRLAND_INSTANCE_SIGNATURE':'preview'},value)
    content='# Managed by Hyprland Theme; only this compositor inherits these values.\n'
    content+='\n'.join('env = '+key+','+val for key,val in env.items() if key!='HYPRLAND_INSTANCE_SIGNATURE')+'\n'
    colors=runtime.colors(value,design)
    if design=='modern':
        content+='\n# Xetal Modern defaults; Window effects can override these below.\n'
        content+=f"general:col.active_border = rgb({colors['Accent'][1:]})\ngeneral:col.inactive_border = rgb({colors['Midlight'][1:]})\n"
        content+='general:border_size = 1\ndecoration:rounding = 18\n'
    elif design=='breakpoint':
        from breakpoint import compositor
        content+=compositor(colors)
    elif design=='binaryknife':
        from binaryknife import compositor
        content+=compositor(colors)
    elif design=='tidalglass':
        from tidalglass import compositor
        content+=compositor(colors)
    elif design=='shadowedge':
        from shadowedge import compositor
        content+=compositor(colors)
    elif design=='blackwood':
        from blackwood import compositor
        content+=compositor(colors)
    elif design=='midnighttransit':
        from midnighttransit import compositor
        content+=compositor(colors)
    elif design=='hyperfusionblue':
        from hyperfusionblue import compositor
        content+=compositor(colors)
    elif design=='gildedhollow':
        from gildedhollow import compositor
        content+=compositor(colors)
    elif design=='hollowgrove':
        from hollowgrove import compositor
        content+=compositor(colors)
    elif design=='candycloud':
        from candycloud import compositor
        content+=compositor(colors)
    elif design=='obsidianforge':
        from obsidianforge import compositor
        content+=compositor(colors)
    elif design=='porcelainink':
        from porcelainink import compositor
        content+=compositor(colors)
    if partial:
        old_content=store.load()[0]
        if 'colors' not in components:content=old_content
        elif 'effects' not in components:
            # A palette-only change must not also replace animations, gaps, rounding or blur.
            retained='\n'.join(line for line in old_content.splitlines() if not line.lstrip().startswith(('env =','general:col.active_border','general:col.inactive_border')))
            content='\n'.join(line for line in content.splitlines() if line.lstrip().startswith('env ='))+'\n'+retained+'\n'
            content+=f"general:col.active_border = rgb({colors['Accent'][1:]})\ngeneral:col.inactive_border = rgb({colors['Midlight'][1:]})\n"
    store.check(content,expected[0])
    scheme=kde_colors(value,design)
    isolated=ROOT/'dolphin/config/kdeglobals'
    cfg=configparser.ConfigParser(interpolation=None,strict=False); cfg.optionxform=str; cfg.read(isolated)
    new=configparser.ConfigParser(interpolation=None); new.optionxform=str; new.read_string(scheme)
    for section in new.sections():
        if section.startswith(('Colors:','ColorEffects:')): cfg[section]=dict(new[section])
    if 'General' not in cfg: cfg['General']={}
    cfg['General']['ColorScheme']='Xetal'+design.title()+value.title()
    stream=io.StringIO(); cfg.write(stream,space_around_delimiters=False)
    css='/* Hyprland-only notification colors. Retain the packaged layout and animations. */\n'
    css+='@define-color cc-bg '+colors['Window']+';\n@define-color noti-bg '+colors['Window']+';\n'
    css+='@define-color noti-bg-hover '+colors['Button']+';\n@define-color text-color '+colors['Text']+';\n'
    css+='@define-color text-color-disabled '+colors['Disabled']+';\n@define-color noti-border-color '+colors['Midlight']+';\n'
    if design!='raw':css+=designs.notification_style(colors,design)
    bar=runtime.stylesheet((runtime.ROOT/'waybar-dark.css').read_text(),value,design,qt=False)
    bar_design=bar_styles.resolve(bar_style,design)
    if bar_design!='raw':bar+=designs.waybar_style(colors,bar_design)
    bar+=bar_styles.stylesheet(colors,bar_design,variation=bar_variant)
    import update_widget
    bar=update_widget.attach(bar)
    files={runtime.ROOT/launcher_background:background_data} if background_data is not None else {}
    files.update(group_files)
    files.update({runtime.STATE:(json.dumps({**previous,'version':2,'mode':value,'design':design,**({'layout':layout} if layout is not None else {}),**({'wallpaper_theme':bundle.get('wallpaper_theme',design)} if partial and 'wallpaper' in components else {}),'bar_style':bar_style,'bar_variant':bar_variant,'selection_marker':selection_marker,'launcher_style':launcher_style,'avatar':avatar,'launcher_wallpaper':launcher_wallpaper,'launcher_background':launcher_background,'launcher_surfaces':surfaces,'launcher_labels':labels,'launcher_background_visibility':visibility},indent=2)+'\n').encode(),
           runtime.ROOT/'current.colors':scheme.encode(),runtime.ROOT/'kitty-colors.conf':kitty_colors(value,design).encode(),
           isolated:(stream.getvalue().rstrip()+'\n').encode(),
           ROOT/'waybar/style.css':bar.encode(),
           ROOT/'waybar/updates.css':update_widget.style(colors).encode(),
           ROOT/'swaync/style.css':css.encode()})
    for target,template in [('hyprlock.conf','hyprlock-raw.conf'),('startup/kitty.conf','startup-raw.conf')]:
        path=ROOT/target;saved=runtime.ROOT/template
        if not path.exists() or not saved.exists():continue
        raw=saved.read_bytes()
        if runtime.design()=='raw':
            raw=path.read_bytes()
            if design!='raw':files[saved]=raw
        files[path]=(modern_lock(colors,design).encode() if target=='hyprlock.conf' else raw+b'\n'+kitty_colors(value,design).encode()) if design!='raw' else raw
    if not partial or 'colors' in components or 'waybar' in components:
        bar_config=ROOT/'waybar/config.json'
        if bar_config.exists():files[bar_config]=(json.dumps(bar_styles.configure(json.loads(bar_config.read_text()),bar_design,bar_variant),indent=2)+'\n').encode()
    if partial and 'colors' not in components:
        for path in (runtime.ROOT/'current.colors',runtime.ROOT/'kitty-colors.conf',isolated,ROOT/'waybar/style.css',ROOT/'waybar/updates.css',ROOT/'swaync/style.css',ROOT/'hyprlock.conf',ROOT/'startup/kitty.conf',runtime.ROOT/'hyprlock-raw.conf',runtime.ROOT/'startup-raw.conf'):
            if 'waybar' in components and path==ROOT/'waybar/style.css':continue
            files.pop(path,None)
    settings.STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with ExitStack() as locks:
        lock_paths=[settings.STATE/'theme-files.lock',settings.STATE/'wallpaper-save.lock']
        lock_paths.append(settings.STATE/'appearance-save.lock')
        for path in (ROOT/'effects/burn/settings.conf',ROOT/'effects/cube/settings.json',ROOT/'effects/minimize/settings.conf',ROOT/'effects/wobbly/settings.json',ROOT/'cursors/settings.json',ROOT/'file_jobs/preferences.json',ROOT/'switcher/preferences.json',ROOT/'terminal_fetch/settings.json',ROOT/'theme/icons.json',ROOT/'sounds/settings.json'):
            if path.exists():lock_paths.append(path.with_suffix('.lock'))
        for path in lock_paths:
            lock=locks.enter_context(path.open('a'))
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        if theme_token()!=expected: raise ValueError('The theme changed elsewhere. Reload before applying.')
        wallpaper_root=ROOT/'wallpaper'
        old_wallpapers={};new_wallpapers={};connected=set();changed_outputs=[]
        if ((not partial and design!=runtime.design()) or (partial and 'wallpaper' in components)) and (wallpaper_root/'sets.json').exists():
            monitors=settings.monitors()
            connected={monitor['name'] for monitor in wallpaper_sets.screens(monitors)}
            old_wallpapers=read_wallpapers(wallpaper_root)
            previous_wallpaper=previous.get('wallpaper_theme',runtime.design())
            wallpaper_design=bundle.get('wallpaper_theme',bundle['theme']['design']) if partial else design
            new_wallpapers,profiles=wallpaper_sets.switching(wallpaper_root,previous_wallpaper,wallpaper_design,old_wallpapers,monitors)
            if partial and bundle.get('wallpapers'):
                from PIL import Image
                choices=bundle['wallpapers'];fallback=list(choices.values())
                for index,monitor in enumerate(wallpaper_sets.screens(monitors)):
                    item=copy.deepcopy(choices.get(monitor['name'],fallback[index%len(fallback)]))
                    path=Path(item['path']).expanduser().resolve(strict=True)
                    with Image.open(path) as picture:picture.verify()
                    item['path']=str(path);new_wallpapers[monitor['name']]=item
                profiles['themes'][wallpaper_design]=copy.deepcopy(new_wallpapers)
            files.update({wallpaper_root/'selection.json':wallpaper_sets.encode(new_wallpapers),
                          wallpaper_root/'hyprpaper.conf':wallpaper_config(new_wallpapers).encode(),
                          wallpaper_root/'profiles.json':wallpaper_sets.encode(profiles)})
        effect_files,effect_reloads=({},[])
        if not partial or 'effects' in components:
            target_design=bundle['theme']['design'] if partial else design
            effect_files,effect_reloads=effect_colors.plan(ROOT,runtime.design(),target_design,runtime.colors(value,target_design))
        files.update(effect_files)
        if partial:
            import presets
            if 'cursors' in components and 'cursors' in bundle:
                from cursors import controller as cursor_controller
                cursor_controller.prepare()
            extra,reloads=presets.resources(ROOT,bundle,components,runtime.design())
            files.update(extra);effect_reloads=list(dict.fromkeys([*effect_reloads,*reloads]))
        # Minimize follows the profile palette even for a colors-only preset.
        # Its custom color, effect and motion settings are left intact. Reload
        # again after rollback so the renderer sees the restored palette too.
        if runtime.ROOT/'current.colors' in files and (ROOT/'effects/minimize/settings.conf').exists():
            effect_reloads=list(dict.fromkeys([*effect_reloads,('Xetal Minimize','xetalminimize:reload')]))
        if runtime.ROOT/'current.colors' in files and (ROOT/'effects/window_close/settings.conf').exists():
            effect_reloads=list(dict.fromkeys([*effect_reloads,('Xetal Window Close','xetalwindowclose:reload')]))
        if runtime.STATE in files and (ROOT/'cursors/settings.json').exists() and (not partial or 'colors' in components):
            effect_reloads=list(dict.fromkeys([*effect_reloads,('Xetal Desktop Cube','xetalcube:cursor')]))
        old={path:path.read_bytes() if path.exists() else None for path in files}
        effects_attempted=False
        try:
            if background_data is not None or group_files:(runtime.ROOT/'backgrounds').mkdir(exist_ok=True,mode=0o700)
            for path,data in files.items():
                path.parent.mkdir(parents=True,exist_ok=True);keys.atomic_write(path,data)
            for connector,item in new_wallpapers.items():
                if connector in connected and item!=old_wallpapers.get(connector):
                    changed_outputs.append(connector);set_wallpaper(connector,item)
            effects_attempted=True
            if partial and 'effects' in components:presets.activate_effects(bundle,settings.ctl)
            effect_colors.reload_active(settings.ctl,effect_reloads)
            if not partial or 'colors' in components or 'effects' in components:store.save(content,expected[0])
        except Exception:
            for path,data in old.items():
                if path.exists() and path.read_bytes()==files[path]:
                    if data is None: path.unlink()
                    else: keys.atomic_write(path,data)
            for connector in reversed(changed_outputs):
                if connector in old_wallpapers:
                    try:set_wallpaper(connector,old_wallpapers[connector])
                    except Exception:pass
            if effects_attempted:
                try:effect_colors.reload_active(settings.ctl,effect_reloads)
                except Exception:pass
            raise
    if not partial or 'colors' in components or 'waybar' in components:bar_styles.reload_session(ROOT)
    if not partial or 'colors' in components:reload_kitty(include_startup=True)
    # Reload only our notification daemon, never a notification server from KDE.
    for item in Path('/proc').iterdir():
        if not item.name.isdigit(): continue
        try: command=(item/'cmdline').read_bytes().split(b'\0')
        except OSError: continue
        if command and Path(command[0].decode(errors='ignore')).name=='swaync' and str(ROOT/'swaync/config.json').encode() in command:
            subprocess.run(['swaync-client','--reload-css'],capture_output=True,timeout=5); break
    # Only opted-in installs have a public artwork directory. Never publish passwords.
    try:
        if ROOT.resolve() == (Path.home()/'.config/hypr').resolve():
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from login.profile import publish
            publish(ROOT)
    except (ImportError, OSError) as error:
        print('Fusion sign-in artwork could not be refreshed: '+str(error), file=sys.stderr)
    return theme_token()


def apply_components(target,selected,expected):
    import presets
    target=presets.validate(target);selected=set(selected)
    if not selected:raise ValueError('Select at least one component.')
    state=presets.merged_theme(runtime.state(),target,selected)
    return apply_mode(state['mode'],expected,state['design'],state.get('avatar','auto'),
        state.get('launcher_wallpaper',False),state.get('launcher_background',''),state.get('launcher_surfaces'),
        state.get('launcher_style','follow'),launcher_labels=state.get('launcher_labels'),
        launcher_background_visibility=state.get('launcher_background_visibility',18),
        layout=state['layout'],components=selected,bundle=target,selection_marker=state.get('selection_marker','none'),bar_style=state.get('bar_style','follow'),bar_variant=state.get('bar_variant'))

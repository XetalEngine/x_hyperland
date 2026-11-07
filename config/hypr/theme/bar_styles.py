"""Independent Waybar architecture, composed with the chosen desktop palette."""
import copy
from pathlib import Path
import os
import signal
import designs

STYLES={'follow':'Follow desktop theme', **designs.DESIGNS}
VARIANTS={'full':'Full · continuous bar', 'partial':'Partial · floating sections',
          'centered':'Centered · workspaces in the middle'}
DESCRIPTIONS={
 'blackwood':'Walnut panels · brass fittings, sage selections and an engraved HF monogram',
 'midnighttransit':'Station enamel · cream pinstripes, amber signals and a winged HF badge',
 'hyperfusionblue':'Alpine console · silver bevels, sapphire buttons and a polished graphite rail',
 'raw':'Terminal rail · a continuous compact strip with underlined workspaces',
 'modern':'Floating islands · rounded app, clock and status capsules',
 'breakpoint':'Command deck · segmented blocks and a strong lower seam',
 'binaryknife':'Circuit rail · offset corners, side ticks and a centered workspace bank',
 'tidalglass':'Tide pools · translucent curved islands with a luminous rim',
 'porcelainink':'Ink ledger · a restrained paper strip with a stamped Apps seal',
 'obsidianforge':'Forge console · heavy machined edges and inset status blocks',
 'candycloud':'Cloud beads · soft floating bubbles and pill-shaped workspaces',
 'shadowedge':'Blade rail · fine silver edges, angular tabs and a quiet central clock',
 'hollowgrove':'Grove bough · botanical glass, pale leaves and a framed workspace trail',
 'gildedhollow':'Lantern rail · engraved brass, moss-dark stone and glowing workspace jewels',
}


def resolve(choice,design):return design if choice=='follow' else choice


def default_variant(style):
    # Retain the appearance of presets saved before variants were selectable.
    return 'centered' if style in ('binaryknife','candycloud','gildedhollow') else 'partial' if style in ('modern','tidalglass') else 'full'


def variant(value,style):
    value=default_variant(style) if value is None else value
    if not isinstance(value,str) or value not in VARIANTS:raise ValueError('Unknown taskbar variation.')
    return value


def configure(config,style,variation=None):
    """Rearrange only owned modules; retain commands, user modules and settings."""
    if style not in designs.DESIGNS:raise ValueError('Unknown Waybar design.')
    variation=variant(variation,style)
    result=copy.deepcopy(config)
    if isinstance(result,list):return [configure(bar,style,variation) for bar in result]
    all_modules=[]
    for zone in ('left','center','right'):
        for module in result.get('modules-'+zone,[]):
            if module not in all_modules:all_modules.append(module)
    available=set(all_modules)
    apps=['cffi/bar-options','custom/launcher','hyprland/workspaces','cffi/new-workspace','custom/keys','custom/updates','cffi/app-pins']
    status=['custom/recording','cpu','memory','custom/temperature','temperature','disk','custom/internet','custom/lan','network#lan','custom/wifi',
            'custom/vpn','bluetooth','group/audio','pulseaudio#microphone','idle_inhibitor','custom/notifications','tray','clock','custom/power']
    layouts={
        'blackwood':(['cffi/bar-options','custom/launcher','custom/keys','custom/updates','cffi/app-pins','mpris'],['hyprland/workspaces','cffi/new-workspace'],status),
        'midnighttransit':(['cffi/bar-options','custom/launcher','custom/keys','custom/updates','cffi/app-pins','mpris'],['hyprland/workspaces','cffi/new-workspace'],status),
        'hyperfusionblue':(apps,['mpris'],status),
        'raw':(apps,['mpris'],status),
        'modern':(apps+['mpris'],['clock'],[x for x in status if x!='clock']),
        'breakpoint':(apps,['custom/recording','mpris'],[x for x in status if x!='custom/recording']),
        'binaryknife':(['cffi/bar-options','custom/launcher','custom/keys','custom/updates','cffi/app-pins','mpris'],
                       ['hyprland/workspaces','cffi/new-workspace'],status),
        'tidalglass':(apps+['mpris'],['clock'],[x for x in status if x!='clock']),
        'porcelainink':(apps,['clock'],['mpris']+[x for x in status if x!='clock']),
        'obsidianforge':(apps,['cpu','memory','custom/temperature','temperature'],['mpris']+[x for x in status if x not in ('cpu','memory','custom/temperature','temperature')]),
        'candycloud':(['cffi/bar-options','custom/launcher','custom/keys','custom/updates','cffi/app-pins','mpris'],
                      ['hyprland/workspaces','cffi/new-workspace'],status),
        'shadowedge':(apps+['mpris'],['clock'],[x for x in status if x!='clock']),
        'hollowgrove':(apps,['mpris'],status),
        'gildedhollow':(['cffi/bar-options','custom/launcher','custom/keys','custom/updates','cffi/app-pins','mpris'],
                        ['hyprland/workspaces','cffi/new-workspace'],status),
    }
    left,center,right=map(list,layouts[style])
    workspaces=['hyprland/workspaces','cffi/new-workspace']
    if variation=='centered':
        left=[m for m in left if m not in workspaces]
        right=[m for m in right if m not in workspaces]
        right=[m for m in center if m not in workspaces]+right
        center=workspaces
    else:
        left=[m for m in left if m not in workspaces]
        insertion=left.index('custom/launcher')+1 if 'custom/launcher' in left else 0
        left[insertion:insertion]=workspaces
        center=[m for m in center if m not in workspaces]
        right=[m for m in right if m not in workspaces]
        if not center and 'clock' in right:center=['clock'];right.remove('clock')
    zones=[[module for module in zone if module in available] for zone in (left,center,right)]
    used=set(sum(zones,[]));zones[2]+=[m for m in all_modules if m not in used]
    for zone,modules in zip(('left','center','right'),zones):result['modules-'+zone]=modules
    floating=variation!='full' or style in ('modern','tidalglass','candycloud','hollowgrove','gildedhollow')
    result.update(height=42 if style in ('candycloud','tidalglass') else 40 if floating else 38,spacing=2)
    result['margin-top']=6 if floating else 0;result['margin-bottom']=0
    result['margin-left']=10 if floating else 0;result['margin-right']=10 if floating else 0
    return result


def stylesheet(p,style,root=None,variation=None):
    if style not in designs.DESIGNS:raise ValueError('Unknown Waybar design.')
    variation=variant(variation,style)
    root=root or Path(__file__).resolve().parent
    a,b,w,t,m,h=p['Accent'],p['Base'],p['Window'],p['Text'],p['Midlight'],p['Highlight']
    common=f'''
/* Independent Waybar design: {style}. All click targets and visibility choices are retained. */
window#waybar {{color:{t};}}
#custom-launcher, #custom-keys, #new-workspace, #clock, #audio, #xetal-pins .pin, #workspaces button {{color:{t};}}
#workspaces button.active {{background:{h}; color:{p['HighlightedText']};}}
#workspaces button:hover, #custom-launcher:hover, #custom-keys:hover, #xetal-pins .pin:hover {{background:{p['Mid']};}}
#custom-recording.recording {{color:#ff8292;}}
/* The proportional text face otherwise falls back to wide Nerd glyphs whose
   ink overhangs their advance into the next digit. Keep metrics in one face,
   including after GTK reloads a theme. The Mono variant has cell-sized icons. */
#cpu, #memory, #temperature, #custom-temperature, #disk {{
    font-family:"FiraCode Nerd Font Mono","FiraCode Nerd Font","DejaVu Sans Mono",monospace;
}}
'''
    faces={
'blackwood':__import__('blackwood').bar_controls(p,root),
'midnighttransit':__import__('midnighttransit').bar_controls(p,root),
'hyperfusionblue':f'''
window#waybar {{background:linear-gradient(180deg,{p['Button']},{w} 35%,{b} 54%,{w});border:1px solid {m};border-top-color:{p['Light']};border-bottom:2px solid {p['Dark']};border-radius:0;}}
.modules-left,.modules-center,.modules-right {{padding:0 5px;}}
#custom-launcher {{background:linear-gradient(180deg,{p['Button']},{w});border:1px solid {p['Light']};border-radius:6px;font-weight:700;padding:0 14px 0 35px;}}
#workspaces button {{background:linear-gradient(180deg,{p['Button']},{b} 55%,{w});border:1px solid {m};border-top-color:{p['Light']};border-radius:5px;margin:3px 2px;padding:0 7px;}}
#workspaces button.active {{background:linear-gradient(180deg,{a},{h} 48%,{h});color:{p['HighlightedText']};border:1px solid {p['Link']};box-shadow:inset 0 1px alpha({p['Light']},0.6),0 0 5px alpha({a},0.4);}}
#custom-keys,#new-workspace,#xetal-pins .pin {{background:linear-gradient(180deg,{p['Button']},{w});border:1px solid {m};border-radius:5px;}}
#clock {{background:transparent;border-left:1px solid {m};border-radius:0;padding:0 12px;font-weight:600;}}
''',
'raw':f'''
window#waybar {{background:{w};border:0;border-bottom:1px solid {a};border-radius:0;}}
.modules-left,.modules-center,.modules-right {{padding:2px 4px;background:transparent;}}
#custom-launcher,#custom-keys,#clock,#audio,#xetal-pins .pin,#workspaces button {{border-radius:0;background:transparent;}}
#custom-launcher {{border-right:1px solid {m};color:{a};font-family:monospace;}}
#workspaces button {{border-bottom:2px solid transparent;padding:0 6px;}}
#workspaces button.active {{border-bottom-color:{a};background:alpha({a},0.1);}}
#clock {{font-family:monospace;border-left:1px solid {m};}}
''',
'modern':f'''
window#waybar {{background:transparent;border:0;}}
.modules-left,.modules-center,.modules-right {{background:alpha({w},0.96);border:1px solid alpha({m},0.75);border-radius:22px;padding:3px 8px;}}
.modules-center {{margin:0 12px;}}
#custom-launcher {{background:{h};border-radius:18px;padding:0 15px;}}
#workspaces button {{background:transparent;border:0;border-radius:16px;}}
#workspaces button.active {{box-shadow:inset 0 -2px {a};}}
#clock {{background:transparent;font-weight:bold;}}
#audio,#custom-keys,#xetal-pins .pin {{border-radius:14px;}}
''',
'breakpoint':f'''
window#waybar {{background:linear-gradient(180deg,{w},{b});border:0;border-bottom:3px solid {a};}}
.modules-left,.modules-center,.modules-right {{padding:2px 4px;border-right:1px solid {m};}}
#custom-launcher {{background:{h};border-radius:2px 12px 2px 2px;border-left:3px solid {a};font-weight:900;padding:0 15px;}}
#workspaces button {{border-radius:1px;border:1px solid {m};background:alpha({b},0.5);}}
#workspaces button.active {{border-color:{a};box-shadow:inset 0 -3px {a};}}
#clock {{border-radius:1px;background:{h};border-left:3px solid {a};font-family:monospace;}}
#cpu,#memory,#custom-temperature,#temperature,#disk {{padding:0 5px;border-bottom:1px solid {m};}}
''',
'binaryknife':f'''
window#waybar {{background:{b};border:1px solid {m};border-bottom:2px solid {a};}}
.modules-left,.modules-right {{padding:3px 5px;}}
.modules-center {{padding:2px 8px;border-left:2px solid {a};border-right:2px solid {a};background:alpha({a},0.07);}}
#custom-launcher,#clock {{background:linear-gradient(110deg,{h},{w});border:1px solid {a};border-radius:0 10px 0 10px;}}
#workspaces button {{background:transparent;border-radius:0 8px 0 8px;border:1px solid {m};}}
#workspaces button.active {{border-color:{a};box-shadow:inset 3px 0 {a};}}
#custom-keys,#audio,#xetal-pins .pin {{border-radius:0;background:transparent;}}
''',
 'tidalglass':f'''
window#waybar {{background:transparent;border:0;}}
.modules-left,.modules-center,.modules-right {{background:linear-gradient(170deg,alpha({p['Button']},0.96),alpha({w},0.86));border:1px solid alpha({p['Light']},0.75);border-radius:10px 28px 10px 28px;padding:4px 10px;box-shadow:inset 0 1px alpha({a},0.3);}}
.modules-center {{margin:0 14px;border-radius:24px;}}
#custom-launcher {{background:alpha({a},0.18);border-radius:20px 5px 20px 5px;border-bottom:1px solid {a};}}
#workspaces button {{background:transparent;border:0;border-radius:12px;}}
#workspaces button.active {{border-bottom:2px solid {p['Light']};}}
#clock,#audio,#custom-keys,#xetal-pins .pin {{background:alpha({b},0.25);border-radius:16px;}}
''',
'porcelainink':f'''
window#waybar {{background:{w};border:1px solid {m};border-bottom:2px solid {p['Link']};border-radius:1px;}}
.modules-left,.modules-center,.modules-right {{padding:4px 8px;}}
#custom-launcher {{background:{h};border:1px solid {a};border-radius:1px;box-shadow:inset 0 0 0 2px {w};padding:0 16px;}}
#workspaces button {{background:transparent;border:0;border-radius:0;font-family:serif;}}
#workspaces button.active {{background:transparent;color:{a};border-bottom:2px solid {a};}}
#clock {{background:transparent;font-family:serif;letter-spacing:2px;border-left:1px solid {m};border-right:1px solid {m};border-radius:0;}}
#audio,#custom-keys,#xetal-pins .pin {{background:transparent;border-radius:0;}}
''',
'obsidianforge':f'''
window#waybar {{background:linear-gradient(180deg,{p['Button']},{b});border:1px solid {m};border-top:2px solid {p['Light']};border-bottom:4px solid {a};border-radius:3px;}}
.modules-left,.modules-center,.modules-right {{padding:2px 5px;}}
.modules-center {{background:{b};border:1px solid {m};border-radius:3px;margin:3px 10px;padding:0 10px;}}
#custom-launcher,#clock {{background:{b};border:1px solid {p['Light']};border-bottom:2px solid {a};border-radius:2px;font-weight:900;}}
#workspaces button {{border:1px solid {m};background:{b};border-radius:2px;}}
#workspaces button.active {{box-shadow:inset 0 2px {a};border-color:{a};}}
#audio,#custom-keys,#xetal-pins .pin {{border:1px solid {m};border-radius:2px;}}
''',
'candycloud':f'''
window#waybar {{background:transparent;border:0;}}
.modules-left,.modules-center,.modules-right {{background:linear-gradient(160deg,alpha({p['Button']},0.98),alpha({w},0.95));border:1px solid {p['Light']};border-radius:26px;padding:4px 10px;box-shadow:inset 0 2px alpha({p['Text']},0.08);}}
.modules-center {{margin:0 10px;}}
#custom-launcher,#clock {{background:linear-gradient(180deg,{h},{p['Button']});border:1px solid {p['Link']};border-radius:19px;}}
#workspaces button {{background:alpha({b},0.3);border:0;border-radius:22px;min-width:14px;}}
#workspaces button.active {{border:1px solid {p['Light']};box-shadow:inset 0 2px alpha({p['Text']},0.2);}}
#custom-keys,#audio,#xetal-pins .pin {{background:alpha({a},0.1);border-radius:19px;}}
''',
'shadowedge':f'''
window#waybar {{background:linear-gradient(180deg,{p['Button']},{b});border:1px solid {m};border-top:1px solid {p['Light']};border-bottom:1px solid {p['Link']};border-radius:0;}}
.modules-left,.modules-right {{padding:3px 7px;}}
.modules-center {{background:transparent;border-left:1px solid {m};border-right:1px solid {m};padding:1px 18px;margin:4px 12px;}}
#custom-launcher {{background:{b};border:1px solid {p['Link']};border-bottom-color:{a};border-radius:10px 0 10px 0;}}
#workspaces button {{background:transparent;border:0;border-radius:0;}}
#workspaces button.active {{border-top:1px solid {p['Link']};border-bottom:2px solid {a};background:alpha({h},0.5);}}
#clock {{background:transparent;font-weight:500;letter-spacing:2px;border-radius:0;}}
#audio,#custom-keys,#xetal-pins .pin {{background:transparent;border-radius:1px;}}
''',
'gildedhollow':f'''
window#waybar {{background:linear-gradient(165deg,{p['Button']},{w} 24%,{b} 65%,{w});border:1px solid {p['Light']};border-top-color:{p['Link']};border-bottom-color:{a};border-radius:22px;box-shadow:inset 0 0 0 2px alpha({a},0.10);}}
.modules-left {{background-image:url("{root/'assets/gilded-picks.svg'}");background-repeat:no-repeat;background-position:12px center;padding:3px 10px 3px 42px;}}
.modules-center {{padding:3px 8px;margin:0 12px;}}
.modules-right {{padding:3px 12px;}}
#custom-launcher {{background:transparent;font-family:serif;letter-spacing:1px;color:{p['Link']};border-radius:0;border-right:1px solid {m};padding:0 13px;}}
#workspaces button {{background:linear-gradient(150deg,{p['Button']},{b});border:1px solid {m};border-top-color:{p['Light']};border-radius:8px;min-width:17px;padding:0 6px;margin:0 2px;color:{p['Text']};}}
#workspaces button.active {{background:linear-gradient(145deg,{a},{h} 70%);border-color:{p['Link']};color:{p['HighlightedText']};box-shadow:0 0 5px alpha({a},0.50),inset 0 1px alpha({p['Link']},0.75);}}
#workspaces button:hover {{border-color:{a};box-shadow:inset 0 0 5px alpha({a},0.30);}}
#clock {{font-family:serif;letter-spacing:1px;background:transparent;border-left:1px solid {m};border-radius:0;color:{p['Link']};}}
#audio,#custom-keys,#xetal-pins .pin {{background:transparent;border-radius:8px;}}
#custom-power:hover {{color:{p['Link']};text-shadow:0 0 5px {a};}}
''',
'hollowgrove':f'''
window#waybar {{background:linear-gradient(180deg,alpha({p['Button']},0.97),alpha({b},0.95));border:1px solid {p['Link']};border-radius:25px;box-shadow:inset 0 1px alpha({p['Light']},0.25);}}
.modules-left {{background-image:url("{root/'assets/grove-bough.svg'}");background-repeat:no-repeat;background-position:left center;padding:4px 9px 4px 34px;}}
.modules-right {{padding:4px 12px;}}
.modules-center {{padding:4px 12px;}}
#custom-launcher {{font-family:serif;letter-spacing:1px;background:transparent;border-radius:16px;border-right:1px solid {m};}}
#workspaces {{border-left:1px solid alpha({a},0.3);border-right:1px solid alpha({a},0.3);padding:0 5px;}}
#workspaces button {{background:transparent;border:0;border-radius:14px 5px 14px 5px;}}
#workspaces button.active {{background:linear-gradient(160deg,{p['Link']},{h});color:{p['HighlightedText']};border:1px solid {a};}}
#clock {{background:transparent;font-family:serif;letter-spacing:1px;border-left:1px solid {m};border-radius:0;}}
#audio,#custom-keys,#xetal-pins .pin {{background:transparent;border-radius:14px;}}
'''}
    return common+faces[style]+architecture(p,style,variation,root)


def architecture(p,style,variation,root):
    """One material vocabulary, available as a rail, islands or centered bank."""
    a,b,w,t,m,h=p['Accent'],p['Base'],p['Window'],p['Text'],p['Midlight'],p['Highlight']
    radius={'blackwood':'5px','midnighttransit':'7px','hyperfusionblue':'7px','raw':'1px','modern':'23px','breakpoint':'12px 2px 12px 2px','binaryknife':'2px 16px 2px 16px',
            'tidalglass':'28px 28px 14px 14px','porcelainink':'4px','obsidianforge':'5px',
            'candycloud':'28px','shadowedge':'12px 0 12px 0','hollowgrove':'28px 12px 28px 12px','gildedhollow':'24px'}[style]
    surface={
        'blackwood':f'url("{root/"assets/blackwood-grain.svg"}"),linear-gradient(180deg,{p["Button"]},{w} 30%,{b})',
        'midnighttransit':f'linear-gradient(160deg,{p["Button"]},{w} 22%,{b} 78%,{w})',
        'raw':f'linear-gradient(180deg,{w},{b})',
        'modern':f'linear-gradient(160deg,alpha({p["Button"]},0.95),alpha({w},0.93) 50%,alpha({b},0.95))',
        'breakpoint':f'linear-gradient(180deg,{p["Button"]},{b} 55%,alpha({a},0.13))',
        'binaryknife':f'linear-gradient(120deg,{b},alpha({a},0.18) 22%,{w} 23%,{b} 80%,alpha({a},0.12))',
        'tidalglass':f'linear-gradient(165deg,alpha({p["Light"]},0.3),alpha({w},0.94) 24%,alpha({b},0.93) 72%,alpha({a},0.2))',
        'porcelainink':f'linear-gradient(180deg,{w},{p["Button"]} 85%,{w})',
        'obsidianforge':f'linear-gradient(180deg,{p["Light"]},{p["Button"]} 8%,{b} 42%,{w} 90%,alpha({a},0.28))',
        'candycloud':f'linear-gradient(160deg,alpha({p["Link"]},0.20),{w} 30%,{p["Button"]} 70%,alpha({a},0.26))',
        'shadowedge':f'linear-gradient(155deg,{p["Button"]},{b} 40%,{w} 80%,{b})',
        'hollowgrove':f'linear-gradient(150deg,{p["Button"]},alpha({w},0.98) 30%,alpha({b},0.97) 80%,alpha({a},0.14))',
        'hyperfusionblue':f'linear-gradient(180deg,{p["Button"]},{w} 32%,{b} 55%,{w})',
        'gildedhollow':f'linear-gradient(165deg,{p["Button"]},{w} 24%,{b} 65%,{w})',
    }[style]
    frame=f'background:{surface};border:1px solid alpha({a},0.58);border-top-color:alpha({p["Link"]},0.72);border-radius:{radius};box-shadow:inset 0 1px alpha({t},0.12),inset 0 -2px alpha({a},0.1);'
    if variation=='partial':
        structure=f'''
window#waybar {{background:transparent;border:0;box-shadow:none;}}
.modules-left,.modules-center,.modules-right {{{frame}padding:3px 10px;}}
.modules-center {{margin:0 12px;}}
'''
    else:
        structure=f'''
window#waybar {{{frame}}}
.modules-left,.modules-center,.modules-right {{background:transparent;border:0;box-shadow:none;border-radius:0;padding:3px 10px;margin:0;}}
'''
    if variation=='centered':
        structure+=f'.modules-center {{background:alpha({b},0.45);border:1px solid alpha({a},0.3);border-radius:{radius};margin:3px 14px;padding:0 9px;}}\n'
    ornament={
        'blackwood':__import__('blackwood').bar_controls(p,root),
        'midnighttransit':__import__('midnighttransit').bar_controls(p,root),
        'raw':f'''#custom-launcher {{border-left:3px solid {a};border-right:1px dashed {m};letter-spacing:2px;}}
#workspaces button.active {{background:alpha({a},0.14);border-top:1px solid {a};border-bottom:2px solid {a};}}
#clock {{border-left:1px dashed {a};padding-left:13px;}}''',
        'modern':f'''#custom-launcher {{background:linear-gradient(135deg,{h},alpha({a},0.3));border:1px solid alpha({p['Link']},0.4);}}
#workspaces button.active {{border:1px solid alpha({a},0.65);box-shadow:0 0 4px alpha({a},0.25),inset 0 -2px {a};}}
#clock {{letter-spacing:1px;}}''',
        'breakpoint':f'''#custom-launcher {{border-left:4px solid {a};border-bottom:2px solid {p['Link']};border-radius:7px 1px 7px 1px;letter-spacing:1px;}}
#workspaces button {{border:1px solid {m};border-radius:2px;background:{b};}}
#workspaces button.active {{background:linear-gradient(180deg,{h},{b});border-color:{a};box-shadow:inset 0 -3px {a};}}
#clock {{border-left:3px solid {a};border-radius:0;padding-left:12px;}}''',
        'binaryknife':f'''#custom-launcher {{background:linear-gradient(125deg,alpha({a},0.18),{b});border:1px solid {a};border-radius:1px 12px 1px 12px;}}
#workspaces button {{border-radius:1px 9px 1px 9px;border:1px solid {m};}}
#workspaces button.active {{border-color:{p['Link']};box-shadow:inset 2px 0 {a},inset -2px 0 {a};}}
#clock {{border-bottom:1px solid {a};letter-spacing:2px;}}''',
        'tidalglass':f'''#custom-launcher {{border-radius:20px 20px 9px 9px;border:1px solid alpha({p['Link']},0.7);background:linear-gradient(180deg,alpha({a},0.25),alpha({b},0.3));}}
#workspaces button {{border-radius:15px 15px 7px 7px;}}
#workspaces button.active {{background:linear-gradient(180deg,{h},alpha({a},0.3));border-bottom:2px solid {p['Link']};box-shadow:0 0 5px alpha({a},0.25);}}
#clock {{border-bottom:1px solid alpha({a},0.5);border-radius:18px;}}''',
        'porcelainink':f'''#custom-launcher {{border:1px solid {a};border-left:4px solid {a};border-radius:1px;background:alpha({a},0.08);font-family:serif;}}
#workspaces button {{font-family:serif;border:0;border-bottom:1px solid transparent;}}
#workspaces button.active {{background:alpha({a},0.07);color:{a};border-bottom:3px double {a};}}
#clock {{font-family:serif;border-left:1px solid {m};letter-spacing:2px;}}''',
        'obsidianforge':f'''#custom-launcher {{border:2px solid {m};border-top-color:{p['Light']};border-bottom:3px solid {a};border-radius:3px;}}
#workspaces button {{background:linear-gradient(180deg,{p['Button']},{b});border:1px solid {m};border-radius:3px;}}
#workspaces button.active {{border-color:{a};box-shadow:inset 0 2px alpha({p['Link']},0.7),inset 0 -3px {a};}}
#clock {{border:1px solid {m};border-left:4px solid {a};background:{b};padding:0 10px;}}''',
        'candycloud':f'''#custom-launcher {{border-radius:24px;background:linear-gradient(165deg,{p['Link']},{h});border:1px solid alpha({t},0.35);}}
#workspaces button {{border-radius:30px;background:alpha({a},0.07);margin:0 3px;}}
#workspaces button.active {{border:1px solid {p['Link']};box-shadow:inset 0 2px alpha({t},0.35),0 0 5px alpha({a},0.2);}}
#clock {{border-radius:22px;background:alpha({a},0.1);padding:0 13px;}}''',
        'shadowedge':f'''#custom-launcher {{background:{b};border:1px solid {p['Light']};border-bottom:2px solid {a};border-radius:10px 0 10px 0;}}
#workspaces button {{border-radius:9px 0 9px 0;margin:0 2px;}}
#workspaces button.active {{background:linear-gradient(130deg,{h},{b});border-top:1px solid {p['Link']};border-bottom:2px solid {a};}}
#clock {{border:0;border-bottom:1px solid {p['Light']};letter-spacing:3px;}}''',
        'hollowgrove':f'''.modules-left {{background-image:url("{root/'assets/grove-bough.svg'}");background-repeat:no-repeat;background-position:8px center;padding-left:35px;}}
#custom-launcher {{font-family:serif;letter-spacing:1px;background:transparent;border:0;border-right:1px solid alpha({a},0.3);}}
#workspaces button {{border-radius:14px 3px 14px 3px;border:1px solid transparent;margin:0 2px;}}
#workspaces button.active {{background:linear-gradient(155deg,{p['Link']},{h});border-color:{a};box-shadow:inset 0 1px alpha({t},0.3);}}
#clock {{font-family:serif;border-left:1px solid alpha({a},0.3);letter-spacing:1px;}}''',
        'hyperfusionblue':f'''#custom-launcher {{background-image:url("{root/'assets/hyperfusion-blue-mark.svg'}"),linear-gradient(180deg,{p['Button']},{w});background-repeat:no-repeat;background-position:9px center;border:1px solid {p['Light']};border-radius:6px;padding-left:35px;}}
#workspaces button {{border-radius:5px;border:1px solid {m};border-top-color:{p['Light']};background:linear-gradient(180deg,{p['Button']},{b} 55%,{w});}}
#workspaces button.active {{background:linear-gradient(180deg,{a},{h} 48%,{h});color:{p['HighlightedText']};border-color:{p['Link']};box-shadow:inset 0 1px alpha({p['Light']},0.7),0 0 5px alpha({a},0.35);}}
#clock {{border-left:1px solid {m};font-weight:600;}}''',
        'gildedhollow':f'''.modules-left {{background-image:url("{root/'assets/gilded-picks.svg'}");background-repeat:no-repeat;background-position:10px center;padding-left:40px;}}
#custom-launcher {{font-family:serif;letter-spacing:1px;color:{p['Link']};background:transparent;border:0;border-right:1px solid {m};}}
#workspaces button {{background:linear-gradient(145deg,{p['Button']},{b});border:1px solid {m};border-top-color:{p['Light']};border-radius:8px;}}
#workspaces button.active {{background:linear-gradient(145deg,{a},{h});border-color:{p['Link']};box-shadow:0 0 5px alpha({a},0.5),inset 0 1px alpha({p['Link']},0.8);}}
#clock {{font-family:serif;color:{p['Link']};border-left:1px solid {m};letter-spacing:1px;}}''',
    }[style]
    return f'\n/* Taskbar variation: {variation} */\n'+structure+ornament+'\n'


def reload_session(root):
    """Signal only this user's bar using this profile and compositor instance."""
    config=str(root/'waybar/config.json').encode();instance=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE','').encode()
    if not instance:return
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            if proc.stat().st_uid!=os.getuid():continue
            command=(proc/'cmdline').read_bytes().split(b'\0')
            if not command or Path(os.fsdecode(command[0])).name!='waybar' or config not in command:continue
            if b'HYPRLAND_INSTANCE_SIGNATURE='+instance not in (proc/'environ').read_bytes().split(b'\0'):continue
            os.kill(int(proc.name),signal.SIGUSR2)
        except (OSError,ValueError):continue

"""Pure settings, rendering and quality policy. Never rewrite effect preferences."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = dict(kawase='Classic blur', acrylic='Acrylic', aurora='Aurora', drops='Rain drops',
               fluid_jar='Fluid jar', frost='Frost', haze='Haze', heat_shimmer='Heat shimmer',
               prism='Prism', ripple='Click ripples', water='Water')
QUALITY = {'current':'Keep current tuning', 'lightweight':'Lightweight', 'balanced':'Balanced', 'full':'Full effects'}
# (initial value, minimum, maximum). Names/ranges match Hyprland 0.57's schema.
PARAMETERS = {
 'acrylic': {'aberration':(.025,0,.25), 'bulb':(48,4,256), 'clarity':(.82,0,1), 'refraction':(24,0,48)},
 'aurora': {'intensity':(.35,0,1), 'speed':(1,0,10)},
 'drops': {'speed':(3,0,10)},
 'fluid_jar': {'distortion':(8,0,10), 'fill_amount':(.5,0,1), 'mass':(1.4,.1,10),
               'precision':(2,.5,8), 'speed':(3.7,0,10), 'turbulence':(1.2,0,5)},
 'glass': {'refraction':(20,0,20), 'roughness':(1,0,1), 'size':(40,4,512)},
 'haze': {'intensity':(.35,0,1), 'iridescence':(.7,0,1)},
 'heat_shimmer': {'speed':(1,0,10)},
 'ripple': {'duration':(.45,.05,5), 'radius':(400,1,1000), 'strength':(30,0,32), 'width':(32,1,200)},
 'water': {'damping':(.95,0,1), 'duration':(12,.5,60), 'radius':(20,1,1000), 'speed':(.76,0,10), 'strength':(32,0,32)},
}
SUGGESTIONS = {'tidalglass':'acrylic', 'midnighttransit':'drops', 'polaris':'aurora',
               'obsidianforge':'heat_shimmer', 'candycloud':'haze'}
MATERIAL = dict(enabled=False, variant='kawase', size=4, passes=2, proportional=False,
                parameters={group:{name:spec[0] for name,spec in items.items()} for group,items in PARAMETERS.items()})
FOCUS = dict(enabled=True, border=2, shadow=8, glow=True, glow_size=3, exceptions=[])
THEME = dict(material=MATERIAL, focus=FOCUS)
DEFAULTS = dict(version=2, quality='current', reduced_motion=False, preview_size=360, preview_fps=30,
                hover_previews=False, quiet_sharing=False, themes={}, focus=FOCUS, appearance={})
# Glass, quality presets, hover previews and workspace tools are parked for now.
# Keep their saved data/code for later; hidden controls must not override effects.
EXPERIMENTAL_VISUALS = False
APPEARANCE_RANGES = {'decoration:rounding':(0,40,True), 'general:border_size':(0,10,True),
    'decoration:shadow:range':(0,40,True), 'decoration:active_opacity':(.3,1,False),
    'decoration:inactive_opacity':(.3,1,False)}
APPEARANCE_BOOLS = {'general:resize_on_border','animations:enabled','decoration:blur:enabled','decoration:shadow:enabled'}
APPEARANCE_GAPS = {'general:gaps_in','general:gaps_out'}


def number(value, low, high, integer=False):
    if type(value) not in (int,float) or not math.isfinite(value) or not low <= value <= high or (integer and int(value)!=value):
        raise ValueError(f'Choose a number between {low} and {high}.')
    return value


def validate(value):
    if not isinstance(value,dict) or set(value)!=set(DEFAULTS) or type(value['version']) is not int or value['version']!=2:
        raise ValueError('Unsupported visual settings.')
    validate_focus(value['focus'])
    if not isinstance(value['appearance'],dict):raise ValueError('Invalid window appearance settings.')
    for key,item in value['appearance'].items():
        if key in APPEARANCE_RANGES:number(item,*APPEARANCE_RANGES[key])
        elif key in APPEARANCE_BOOLS:
            if type(item) is not bool:raise ValueError(key+' must be on or off.')
        elif key in APPEARANCE_GAPS:
            if not isinstance(item,str) or not re.fullmatch(r'\d{1,3}(?:\s+\d{1,3}){0,3}',item):raise ValueError('Gaps need one to four numbers from 0 to 999.')
        else:raise ValueError('Unknown window appearance option: '+key)
    if not isinstance(value['quality'],str) or value['quality'] not in QUALITY: raise ValueError('Unknown visual quality profile.')
    for key in ('reduced_motion','hover_previews','quiet_sharing'):
        if type(value[key]) is not bool: raise ValueError(key+' must be on or off.')
    number(value['preview_size'],240,520,True); number(value['preview_fps'],1,60,True)
    if not isinstance(value['themes'],dict) or len(value['themes'])>128: raise ValueError('Invalid theme visual settings.')
    for theme,settings in value['themes'].items():
        if not isinstance(theme,str) or not re.fullmatch(r'[a-z0-9_]{1,64}',theme) or not isinstance(settings,dict) or set(settings)!=set(THEME):
            raise ValueError('Invalid theme visual settings.')
        material,focus=settings['material'],settings['focus']
        if not isinstance(material,dict) or set(material)!=set(MATERIAL) or not isinstance(material['variant'],str) or material['variant'] not in VARIANTS:
            raise ValueError('Unknown material.')
        if not isinstance(focus,dict) or set(focus)!=set(FOCUS): raise ValueError('Invalid focus settings.')
        for obj,key in ((material,'enabled'),(material,'proportional'),(focus,'enabled'),(focus,'glow')):
            if type(obj[key]) is not bool: raise ValueError(key+' must be on or off.')
        number(material['size'],1,15,True);number(material['passes'],1,4,True)
        params=material['parameters']
        if not isinstance(params,dict) or set(params)!=set(PARAMETERS): raise ValueError('Invalid material parameters.')
        for group,items in PARAMETERS.items():
            if not isinstance(params[group],dict) or set(params[group])!=set(items): raise ValueError('Invalid material parameters.')
            for name,(_,low,high) in items.items(): number(params[group][name],low,high)
        validate_focus(focus)
    return deepcopy(value)


def validate_focus(focus):
    if not isinstance(focus,dict) or set(focus)!=set(FOCUS):raise ValueError('Invalid focus settings.')
    if any(type(focus[key]) is not bool for key in ('enabled','glow')):raise ValueError('Focus options must be on or off.')
    number(focus['border'],0,10,True);number(focus['shadow'],0,40,True);number(focus['glow_size'],1,30,True)
    if not isinstance(focus['exceptions'],list) or len(focus['exceptions'])>64:raise ValueError('Too many application exceptions.')
    if any(not isinstance(c,str) or not c or len(c)>200 or any(ord(ch)<32 for ch in c) for c in focus['exceptions']):
        raise ValueError('Use one exact application class per line.')


def upgrade(value, theme='raw'):
    """Promote an existing theme's focus choices to one persistent global choice."""
    result=deepcopy(value)
    if isinstance(result,dict) and result.get('version')==1:
        themes=result.get('themes',{})
        selected=themes.get(theme) if isinstance(themes,dict) else None
        if selected is None and isinstance(themes,dict):
            selected=next((v for v in reversed(list(themes.values())) if isinstance(v,dict) and isinstance(v.get('focus'),dict) and v['focus'].get('enabled')),None)
        result.update(version=2,focus=deepcopy(selected.get('focus',FOCUS) if isinstance(selected,dict) else FOCUS),appearance={})
    return validate(result)


def active_settings(settings):
    result=deepcopy(settings)
    if not EXPERIMENTAL_VISUALS:
        result.update(quality='current',reduced_motion=False,hover_previews=False,quiet_sharing=False)
        for theme in result['themes'].values():theme['material']['enabled']=False
    return result


def load(root=ROOT):
    path=Path(root)/'visuals/settings.json'; raw=path.read_bytes() if path.exists() else b''
    if len(raw)>256*1024: raise ValueError('Visual settings file is too large.')
    return upgrade(json.loads(raw) if raw else DEFAULTS,theme_name(root)),hashlib.sha256(raw).hexdigest()


def theme_name(root=ROOT):
    try:
        name=json.loads((Path(root)/'theme/state.json').read_text()).get('design','raw')
        return name if isinstance(name,str) and re.fullmatch(r'[a-z0-9_]{1,64}',name) else 'raw'
    except (OSError,ValueError,AttributeError): return 'raw'


def theme_settings(settings, name):
    result=deepcopy(settings['themes'].get(name,THEME))
    result['focus']=deepcopy(settings['focus'])
    return result


def palette(root=ROOT):
    try:
        state=json.loads((Path(root)/'theme/state.json').read_text())
        palettes=json.loads((Path(root)/'theme/palettes.json').read_text())
        design=state.get('design','raw'); mode=state.get('mode','dark')
        return (palettes if design=='raw' else palettes[design])[mode]
    except (OSError,ValueError,KeyError): return {'Accent':'#76ddd0','Midlight':'#405269','Window':'#171c24'}


def preview_limits(settings):
    cap={'lightweight':5,'balanced':20,'full':60,'current':60}[settings['quality']]
    return settings['preview_size'], min(settings['preview_fps'],cap)


def native_settings(settings, root=ROOT, quiet=False):
    """Render focus defaults and saved appearance; leave other effects alone."""
    validate(settings);settings=active_settings(settings)
    theme=theme_settings(settings,theme_name(root)); material=theme['material']; focus=settings['focus']
    result={key.replace(':','.'):value for key,value in settings['appearance'].items()}
    from compat.hypr_compat import gaps
    for key in APPEARANCE_GAPS:
        if key in settings['appearance']:result[key.replace(':','.')]=gaps(settings['appearance'][key])
    quality=settings['quality']; reduced=settings['reduced_motion'] or (quiet and EXPERIMENTAL_VISUALS)
    if material['enabled']:
        variant=material['variant']
        # Motion-sensitive modes use a static blur, retaining the selected effect in the file.
        if reduced and variant in ('aurora','drops','fluid_jar','heat_shimmer','ripple','water'): variant='kawase'
        result.update({'decoration.blur.enabled':True,'decoration.blur.variant':variant,
                       'decoration.blur.size':material['size'],'decoration.blur.passes':material['passes'],
                       'decoration.blur.proportional':material['proportional']})
        if material['proportional']: result['render.use_shader_blur_blend']=True
        for group,items in material['parameters'].items():
            for name,value in items.items(): result[f'decoration.blur.{group}.{name}']=value
    if focus['enabled']:
        colors=palette(root); active=colors['Accent'].lstrip('#'); inactive=colors['Midlight'].lstrip('#')
        result.update({'general.border_size':focus['border'], 'general.col.active_border':f'rgb({active})',
                       'general.col.inactive_border':f'rgb({inactive})',
                       'decoration.shadow.enabled':settings['appearance'].get('decoration:shadow:enabled',focus['shadow']>0),
                       'decoration.shadow.range':focus['shadow'],
                       'decoration.shadow.color':f'rgba({active}44)', 'decoration.shadow.color_inactive':'rgba(00000044)',
                       'decoration.glow.enabled':focus['glow'],'decoration.glow.range':focus['glow_size'],
                       'decoration.glow.color':f'rgba({active}40)','decoration.glow.color_inactive':'rgba(00000000)'})
    if quality=='lightweight': result.update({'decoration.blur.enabled':False,'decoration.glow.enabled':False})
    elif quality=='balanced':
        result['decoration.blur.size']=min(result.get('decoration.blur.size',4),4)
        result['decoration.blur.passes']=min(result.get('decoration.blur.passes',2),2)
        if material['enabled']: result['decoration.blur.fluid_jar.precision']=min(material['parameters']['fluid_jar']['precision'],1)
    elif quality=='full': result.update({'decoration.blur.size':material['size'] if material['enabled'] else 6,
                                       'decoration.blur.passes':material['passes'] if material['enabled'] else 3})
    if reduced:
        result.update({'animations.enabled':False,'decoration.blur.variant':'kawase'})
    return result


def overlay_rule(name,title,move):
    return {'name':name,'match':{'class':'^fusion-visual-service$','title':'^'+title+'$'},
            'float':True,'pin':True,'no_initial_focus':True,'no_focus':True,'allows_input':False,
            'decorate':False,'no_anim':True,'no_blur':True,'no_shadow':True,'no_glow':True,
            'border_size':0,'move':move,'tag':'+fusion-placement-owned'}


def lua_config(settings,root=ROOT,quiet=False):
    from compat.hypr_compat import call
    values=native_settings(settings,root,quiet)
    lines=[call('config',values)] if values else []
    # App-owned rules also reach older, personally merged main configs.
    if EXPERIMENTAL_VISUALS:
        lines.append(call('window_rule',{'name':'fusion-visual-tools','match':{'class':'^fusion-(overview|settings|sample)$'},
                                        'float':True,'center':True}))
        for name,title,move in (('fusion-window-preview','Fusion window preview','16 50'),
                                ('fusion-capture-indicator','Fusion capture indicator','100%-w-16 50')):
            lines.append(call('window_rule',overlay_rule(name,title,move)))
    focus=theme_settings(settings,theme_name(root))['focus']
    if focus['enabled']:
        for i,app in enumerate(dict.fromkeys(focus['exceptions'])):
            lines.append(call('window_rule',{'name':f'fusion-focus-exception-{i}', 'match':{'class':'^'+re.escape(app)+'$'},
                                             'no_glow':True,'no_shadow':True}))
    return '\n'.join(lines)

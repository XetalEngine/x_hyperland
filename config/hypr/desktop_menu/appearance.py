"""Shared menu layout and colors for the native menu and its editor preview."""
import sys
import menu_config
sys.path.insert(0, str(menu_config.ROOT/'theme'))
import runtime as theme_runtime


def colors(style):
    if style['palette']=='system' and theme_runtime.design()!='raw':
        p=theme_runtime.colors()
        return {'background':p['Window'],'background_end':p['Window'],'text':p['Text'],'border':p['Midlight'],
                'accent':p['Accent'],'hover':p['Highlight'],'hover_text':p['HighlightedText'],'divider':p['Midlight']}
    return {key: (theme_runtime.recolor(value, theme_runtime.mode())
                  if style['palette'] == 'system' else style[key])
            for key, value in menu_config.CUSTOM_COLORS.items()}


def columns(items):
    result = [[]]
    for item in items:
        if not item['enabled']:
            continue
        if item['kind'] == 'column':
            if result[-1]: result.append([])
        else:
            result[-1].append(item)
    return [column for column in result if column]


def height(item, style):
    if item['kind'] == 'spacer': return item['height']
    if item['kind'] == 'separator': return 13
    if item['kind'] == 'heading': return max(28, style['font_size']+14)
    return max(style['row_height'], style['icon_size']+14 if style['show_icons'] else 0,
               style['font_size']+18)


def row_heights(groups, style):
    return [max(height(column[row], style) for column in groups if row < len(column))
            for row in range(max(map(len, groups), default=0))]


def rgba(value, opacity):
    return 'rgba('+','.join(str(int(value[i:i+2], 16)) for i in (1, 3, 5))+f',{opacity/100:.2f})'


def css(style):
    c = colors(style)
    rounding=max(16,style['rounding']) if style['palette']=='system' and theme_runtime.design()=='modern' else style['rounding']
    breakpoint=style['palette']=='system' and theme_runtime.design()=='breakpoint'
    if breakpoint:rounding=12
    font='Inter' if breakpoint and style['font_family']=='Noto Sans' else style['font_family']
    return f'''
    window#xetal-desktop-background {{background:transparent; border:none; box-shadow:none;}}
    menu.desktop-context-menu {{
        background:linear-gradient(to bottom right, {rgba(c['background'], style['opacity'])}, {rgba(c['background_end'], style['opacity'])});
        color:{c['text']}; border:1px solid {c['border']};
        border-left:{style['accent_width']}px solid {c['accent']};
        border-radius:{rounding}px; padding:{style['padding']}px;
        box-shadow:{'0 6px 20px rgba(0,0,0,0.24)' if style['shadow'] else 'none'};
    }}
    menu.desktop-context-menu menuitem {{
        min-width:0; min-height:0; padding:0; border:1px solid transparent;
        border-radius:{min(rounding, 9)}px;
        background:transparent; color:{c['text']};
        font:{style['font_size']}px "{font}"; text-shadow:none;
    }}
    menu.desktop-context-menu menuitem:hover {{background:{c['hover']}; border-color:{c['border']}; color:{c['hover_text']};}}
    menu.desktop-context-menu label, menu.desktop-context-menu image {{color:inherit; background:transparent;}}
    menu.desktop-context-menu menuitem:disabled {{opacity:1; color:{c['accent']};}}
    menu.desktop-context-menu .section-title {{font-weight:bold;}}
    menu.desktop-context-menu .hotkey {{font-size:{max(9, style['font_size']-2)}px; opacity:0.65;}}
    menu.desktop-context-menu separator {{background:{c['divider']}; min-height:1px; min-width:1px;}}
    menu.desktop-context-menu .divider {{margin:0; padding:0; border:none; border-radius:0; background:transparent;}}
    menu.desktop-context-menu .spacer {{border:none; border-radius:0;}}
    menu.desktop-context-menu .after-split {{border-left:1px solid {c['divider']}; border-radius:0;}}
    '''

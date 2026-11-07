"""Original vector cursor families, shared by the picker and generated themes."""
STYLES = {
    'enamel': ('Transit Enamel', '#f9edca', '#10383c', '#f7ad37'),
    'pearl': ('Pearl', '#f4f7ff', '#172335', '#69baff'),
    'carbon': ('Carbon', '#18232e', '#e2eaff', '#94a6bf'),
    'cyan': ('Neon Cyan', '#173848', '#5ce8ff', '#13c8ff'),
    'orchid': ('Orchid', '#372547', '#e2acff', '#ad65ff'),
    'ember': ('Ember', '#48291f', '#ffd491', '#ff7952'),
    'sumi': ('Sumi Ink', '#242321', '#f6efe3', '#ab3429'),
}
# Canonical cursor names with toolkit aliases. Every functional shape is drawn.
ALIASES = {
 'left_ptr': ['default','arrow','top_left_arrow','left-arrow'],
 'hand2': ['pointer','hand','pointing_hand','9d800788f1b08800ae810202380a0822'],
 'xterm': ['text','ibeam'], 'vertical-text': [],
 'crosshair': ['cross','tcross','cell'],
 'fleur': ['move','all-scroll','size_all'],
 'sb_h_double_arrow': ['ew-resize','col-resize','h_double_arrow','size_hor','e-resize','w-resize','right_side','left_side'],
 'sb_v_double_arrow': ['ns-resize','row-resize','v_double_arrow','size_ver','n-resize','s-resize','top_side','bottom_side'],
 'bd_double_arrow': ['nwse-resize','nw-resize','se-resize','size_fdiag','top_left_corner','bottom_right_corner'],
 'fd_double_arrow': ['nesw-resize','ne-resize','sw-resize','size_bdiag','top_right_corner','bottom_left_corner'],
 'watch': ['wait'], 'left_ptr_watch': ['progress','half-busy'],
 'question_arrow': ['help','whats_this'], 'crossed_circle': ['not-allowed','no-drop','forbidden'],
 'openhand': ['grab','open_hand'], 'closedhand': ['grabbing','closed_hand'],
 'dnd-copy': ['copy'], 'dnd-link': ['alias','link'],
 'zoom-in': [], 'zoom-out': [],
}

def svg(style, shape='left_ptr', frame=0):
    _, fill, edge, accent = STYLES[style]
    arrow = 'M5 3 L5 26 L11 21 L16 32 L21 29 L16 19 L26 18 Z'
    arrow = {'enamel':'M5 3L5 27L12 20L17 32L22 29L17 19L28 18L17 11Z', 'carbon':'M5 3L5 28L12 21L17 32L22 29L17 19L29 18Z', 'cyan':'M5 3L8 28L14 20L25 18Z', 'orchid':'M5 3Q7 2 9 5L28 20L17 20L21 30Q18 34 16 30L12 22L5 28Z', 'ember':'M5 3L5 27L12 20L18 32L23 29L17 18L28 18Z'}.get(style,arrow)
    body = f'<path d="{arrow}"/>'
    hot = (5, 3)
    if shape in ('hand2','openhand','closedhand'):
        body = '<path d="M10 18V5Q10 2 13 3Q15 3 15 6V15V11Q19 8 21 13Q25 10 27 15Q31 13 32 18L30 28Q28 33 23 34H17Q13 34 10 30L4 23Q2 19 6 18L10 21Z"/>'
        if shape == 'closedhand': body = '<path d="M7 15Q8 11 12 13Q15 9 19 12Q23 9 26 13Q31 12 32 17L30 28Q28 33 24 33H15Q10 31 8 27Z"/>'
        hot = (13, 4) if shape == 'hand2' else (19, 19)
    elif shape in ('xterm','vertical-text'):
        path='M12 5H24M18 5V31M12 31H24'
        body = f'<path fill="none" stroke-width="5" d="{path}"/><path fill="none" stroke="{fill}" stroke-width="2" d="{path}"/>'
        if shape == 'vertical-text': body = '<g transform="rotate(90 18 18)">'+body+'</g>'
        hot = (18,18)
    elif shape == 'crosshair':
        path='M18 3V14M18 22V33M3 18H14M22 18H33'
        body = f'<path fill="none" stroke-width="4" d="{path}"/><path fill="none" stroke="{fill}" stroke-width="1.5" d="{path}"/><circle cx="18" cy="18" r="3"/>';hot=(18,18)
    elif shape in ('sb_h_double_arrow','sb_v_double_arrow','bd_double_arrow','fd_double_arrow','fleur'):
        body = '<path d="M3 18L11 10V15H25V10L33 18L25 26V21H11V26Z"/>'
        angle = {'sb_v_double_arrow':90,'bd_double_arrow':45,'fd_double_arrow':-45}.get(shape,0)
        if angle: body = f'<g transform="rotate({angle} 18 18)">{body}</g>'
        if shape == 'fleur': body += '<path d="M18 3L11 10H15V25H11L18 33L25 25H21V10H25Z"/>'
        hot=(18,18)
    elif shape in ('watch','left_ptr_watch'):
        ring=f'<g transform="rotate({frame*30} 18 18)"><circle cx="18" cy="18" r="11" fill="none" stroke="{edge}" stroke-opacity=".25" stroke-width="4"/><path d="M18 7A11 11 0 0 1 29 18" fill="none" stroke="{accent}" stroke-width="4"/></g>'
        body=ring if shape=='watch' else body+'<g transform="translate(15 15) scale(.58)">'+ring+'</g>';hot=(18,18) if shape=='watch' else hot
    elif shape=='crossed_circle':
        body=f'<circle cx="18" cy="18" r="12"/><path stroke="{accent}" stroke-width="3" d="M10 10L26 26"/>';hot=(18,18)
    elif shape.startswith('zoom-'):
        body='<circle cx="15" cy="14" r="9"/><path stroke-width="5" d="M22 22L31 31"/><path fill="none" d="M10 14H20'+('M15 9V19' if shape=='zoom-in' else '')+'"/>';hot=(15,14)
    elif shape in ('question_arrow','dnd-copy','dnd-link'):
        sign={'question_arrow':'?','dnd-copy':'+','dnd-link':'↗'}[shape]
        body+=f'<circle cx="27" cy="27" r="8" fill="{accent}"/><text x="27" y="31" text-anchor="middle" stroke="none" fill="#101820" font-family="DejaVu Sans" font-weight="bold" font-size="12">{sign}</text>'
    # Clear outline and a restrained accent cut make small cursors legible on both palettes.
    result=f'<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36"><g fill="{fill}" stroke="{edge}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">{body}</g></svg>'
    return result, hot

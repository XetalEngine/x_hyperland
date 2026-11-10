"""Original vector cursor families, shared by the picker and generated themes."""
STYLES = {
    'leviathan': ('Leviathan Gilded', '#f0d8b6', '#211c29', '#c69ae5'),
    'polaris': ('Polaris Starlight', '#e8fcff', '#18344b', '#22daed'),
    'infernalencore': ('Infernal Blade', '#f4dfbd', '#36150f', '#ff472c'),
    'midnightrun': ('Midnight Run Neon', '#17212e', '#72f3ff', '#ff4fc3'),
    'platform95': ('Platform 95 Classic', '#fff6df', '#382719', '#c49a42'),
    'mycelium': ('Mycelium Spore', '#f2e5d4', '#352536', '#c9a0e1'),
    'isotope': ('Atomic Phosphor', '#d5e5a4', '#182218', '#b5ed29'),
    'brass': ('Blackwood Brass', '#e9d2a0', '#24271f', '#8db694'),
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
    arrow = {'isotope':'M5 3L6 28L12 21L18 32L23 29L17 19L28 17L16 10Z', 'brass':'M5 3L7 29L13 22L19 32L23 29L17 20L29 17L16 12Z', 'enamel':'M5 3L5 27L12 20L17 32L22 29L17 19L28 18L17 11Z', 'carbon':'M5 3L5 28L12 21L17 32L22 29L17 19L29 18Z', 'cyan':'M5 3L8 28L14 20L25 18Z', 'orchid':'M5 3Q7 2 9 5L28 20L17 20L21 30Q18 34 16 30L12 22L5 28Z', 'ember':'M5 3L5 27L12 20L18 32L23 29L17 18L28 18Z'}.get(style,arrow)
    if style == 'mycelium':
        arrow = 'M5 3Q9 4 13 8L29 18Q30 20 27 20L18 21L22 30Q21 33 18 32L13 23L7 28Q5 29 5 26Z'
    if style == 'platform95':
        arrow = 'M5 3L5 27L11 21L16 32L21 30L16 20L27 20Z'
    if style == 'midnightrun':
        arrow = 'M5 3L7 28L13 21L19 32L24 29L18 18L29 17Z'
    if style == 'infernalencore':
        arrow = 'M5 3L28 16L18 19L24 30L20 33L13 22L7 28Z'
    if style == 'leviathan':
        arrow = 'M5 3L29 17L18 20L23 31L18 34L12 23L6 28Z'
    if style == 'polaris':
        arrow = 'M5 3Q6 2 8 5L28 20L18 21L22 30L18 33L13 23L6 28Z'
    body = f'<path d="{arrow}"/>'
    if style == 'leviathan':
        body += f'<path d="M8 8L10 22L14 18L23 17M10 12L17 16L13 19Z" fill="none" stroke="{edge}" stroke-width=".8"/><path d="M10 12L17 16L13 19Z" fill="{accent}" stroke-width=".5"/>'
    if style == 'polaris':
        body += f'<path d="M8 8L10 22L14 18L22 18" fill="none" stroke="{accent}" stroke-width="1.6"/>'
    if style == 'infernalencore':
        body += f'<path d="M8 8L12 18L22 16M12 18L19 29" fill="none" stroke="{accent}" stroke-width="1.3"/>'
    if style == 'midnightrun':
        body += f'<path d="M9 11L10 21L14 17L22 16" fill="none" stroke="{accent}" stroke-width="1.8"/>'
    if style == 'platform95':
        body += f'<path d="M8 11V20L12 16L20 18" fill="none" stroke="{accent}" stroke-width="1"/>'
    if style == 'mycelium':
        body += f'<path d="M8 8Q12 13 14 20M11 13L16 13L23 17M13 18L9 23M17 14L17 10" fill="none" stroke="{accent}" stroke-width="1"/>'
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
        if style == 'leviathan':
            ring = (f'<circle cx="18" cy="18" r="14" fill="{edge}" stroke="{fill}" stroke-width=".8"/>'
                    f'<g transform="rotate({frame*30} 18 18)"><path d="M18 5L29 18L18 31L7 18ZM18 5V31M7 18H29M18 9L25 18L18 27L11 18Z" fill="none" stroke="{fill}" stroke-width="1.1"/>'
                    f'<circle cx="18" cy="5" r="1.6" fill="{accent}" stroke="none"/></g>'
                    f'<path d="M18 14L22 18L18 22L14 18Z" fill="{accent}" stroke="none"/>')
        if style == 'polaris':
            ring = (f'<circle cx="18" cy="18" r="14" fill="{edge}" stroke="{fill}" stroke-width=".7"/>'
                    f'<path d="M18 10L20 16L26 18L20 20L18 26L16 20L10 18L16 16Z" fill="{fill}" stroke="none"/>'
                    f'<g transform="rotate({frame*30} 18 18)"><ellipse cx="18" cy="18" rx="13" ry="6" fill="none" stroke="{accent}" stroke-width="1.4"/>'
                    f'<circle cx="31" cy="18" r="2.4" fill="{accent}" stroke="{fill}" stroke-width=".7"/></g>')
        if style == 'infernalencore':
            ring = (f'<circle cx="18" cy="18" r="14" fill="{edge}" stroke="{fill}" stroke-width="1.2"/>'
                    f'<circle cx="18" cy="18" r="11.5" fill="none" stroke="{accent}" stroke-width=".7"/>'
                    f'<g transform="rotate({frame*30} 18 18)"><path d="M18 6L25 27.7L6.6 14.3H29.4L11 27.7Z" fill="none" stroke="{accent}" stroke-width="1.8"/>'
                    f'<circle cx="18" cy="5" r="1.4" fill="{fill}" stroke="none"/></g>')
        if style == 'midnightrun':
            ring = (f'<circle cx="18" cy="18" r="14" fill="{fill}" stroke="{edge}" stroke-width="1.2"/>'
                    + ''.join(f'<path d="M18 6V8" stroke="{edge}" stroke-width=".8" transform="rotate({angle} 18 18)"/>' for angle in range(0,360,30))
                    + f'<g transform="rotate({frame*30} 18 18)"><path d="M18 7A11 11 0 0 1 29 18" fill="none" stroke="{accent}" stroke-width="2.8"/>'
                    + f'<path d="M18 29A11 11 0 0 1 7 18" fill="none" stroke="{edge}" stroke-width="2.8"/>'
                    + ''.join(f'<path d="M18 18L18 11" stroke="{edge}" stroke-width="1.3" transform="rotate({angle} 18 18)"/>' for angle in range(0,360,72))
                    + f'<circle cx="18" cy="18" r="2.5" fill="{accent}" stroke="none"/></g>')
        if style == 'mycelium':
            ring = (f'<circle cx="18" cy="18" r="14" fill="{edge}" stroke="{fill}" stroke-width=".8"/>'
                    f'<path d="M16 18Q18 24 15 27H22Q19 22 20 18" fill="{fill}" stroke-width=".7"/>'
                    f'<path d="M8 17Q12 7 18 8Q25 8 28 17Q18 23 8 17Z" fill="{accent}" stroke="{fill}" stroke-width="1"/>'
                    f'<path d="M11 18Q18 22 25 18M14 17L17 20M22 17L19 20" stroke="{fill}" stroke-width=".8"/>'
                    f'<g transform="rotate({frame*30} 18 18)"><circle cx="18" cy="4" r="2" fill="{fill}" stroke="{edge}" stroke-width=".8"/>'
                    f'<circle cx="32" cy="18" r="1.2" fill="{accent}" stroke="{edge}" stroke-width=".6"/></g>')
        if style == 'platform95':
            ring = (f'<circle cx="18" cy="18" r="14" fill="{accent}" stroke="{edge}"/>'
                    f'<circle cx="18" cy="18" r="11" fill="{fill}" stroke="{edge}" stroke-width=".9"/>'
                    + ''.join(f'<path d="M18 8V10" stroke="{edge}" transform="rotate({angle} 18 18)"/>' for angle in (0,90,180,270))
                    + f'<path d="M18 18L23 21" stroke="{edge}" stroke-width="2"/>'
                    + f'<path d="M18 18V10" stroke="{edge}" stroke-width="1.6" transform="rotate({frame*30} 18 18)"/>'
                    + f'<circle cx="18" cy="18" r="1.7" fill="{edge}"/>')
        if style == 'isotope':
            ring = (f'<circle cx="18" cy="18" r="14" fill="{edge}"/>'
                    + ''.join(f'<ellipse cx="18" cy="18" rx="12" ry="5" fill="none" stroke="{fill}" stroke-width="1.2" transform="rotate({angle} 18 18)"/>' for angle in (0,60,120))
                    + f'<circle cx="18" cy="18" r="2.5" fill="{accent}" stroke="none"/>'
                    + f'<g transform="rotate({frame*30} 18 18)"><circle cx="30" cy="18" r="2.8" fill="{accent}" stroke="none"/></g>')
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

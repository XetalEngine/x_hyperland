"""Original enamel-and-nickel icons for Midnight Transit; no bitmap inputs."""
from xml.sax.saxutils import escape


def svg(name,catalog,symbol):
    label,group,shape,_=catalog[name]
    folder=shape=='folder' or group=='Places' and name.startswith('folder-')
    document=shape.startswith('file-')
    defs='''<defs>
    <linearGradient id="enamel" x2=".25" y2="1"><stop stop-color="#376169"/><stop offset=".24" stop-color="#163e43"/><stop offset=".76" stop-color="#082629"/><stop offset="1" stop-color="#235054"/></linearGradient>
    <linearGradient id="nickel" x2="0" y2="1"><stop stop-color="#fff6d9"/><stop offset=".45" stop-color="#dbcba6"/><stop offset=".52" stop-color="#998c6d"/><stop offset="1" stop-color="#f6e7bb"/></linearGradient>
    <linearGradient id="amber" x2="0" y2="1"><stop stop-color="#ffdc88"/><stop offset="1" stop-color="#cf8423"/></linearGradient>
    </defs>'''
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>{escape(label)} · Midnight Transit</title>',defs]
    if folder:
        parts+=['<path d="M5 19V14Q5 9 11 9H25L31 15H53Q59 15 59 21V49Q59 55 53 55H11Q5 55 5 49Z" fill="url(#nickel)" stroke="#082629" stroke-width="1.5"/>',
                '<path d="M7 21V17H56V24H7Z" fill="url(#amber)"/>',
                '<rect x="6" y="23" width="52" height="32" rx="5" fill="url(#enamel)" stroke="#f1dfb6" stroke-width="1.7"/>',
                '<path d="M10 28H54M10 51H54" fill="none" stroke="#a89e7f" stroke-width=".65"/>']
        if shape!='folder':parts+=['<g transform="translate(11 15) scale(.65)" fill="none" stroke="#ffebbf" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'+symbol(shape)+'</g>']
    elif document:
        parts+=['<path d="M13 6H39L53 20V55Q53 58 49 58H16Q12 58 12 54V10Q12 6 13 6Z" fill="#f3e5c5" stroke="#8c957e"/>',
                '<path d="M39 6V20H53" fill="#d9caa7" stroke="#788776"/>',
                '<rect x="17" y="27" width="31" height="23" rx="3" fill="url(#enamel)" stroke="#9b906f"/>',
                '<g transform="translate(16 21) scale(.52)" fill="none" stroke="#ffe6ae" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'+symbol(shape)+'</g>']
    elif shape=='home':
        parts+=['<path d="M10 29L32 9L54 29V55H10Z" fill="url(#enamel)" stroke="#e9d8b1" stroke-width="1.8"/>',
                '<path d="M5 30L32 5L59 30" fill="none" stroke="url(#nickel)" stroke-width="4" stroke-linejoin="round"/>',
                '<path d="M27 55V37H38V55" fill="url(#amber)" stroke="#e9d8b1"/><rect x="18" y="28" width="7" height="7" rx="1" fill="#ffe6ad"/>']
    elif shape in ('computer','desktop'):
        parts+=['<rect x="6" y="9" width="52" height="37" rx="4" fill="url(#nickel)" stroke="#42504b"/>',
                '<rect x="10" y="13" width="44" height="28" rx="2" fill="url(#enamel)" stroke="#061e22"/>',
                '<path d="M26 46H38L40 54H47V57H17V54H24Z" fill="url(#nickel)" stroke="#748177"/>',
                '<path d="M13 36L39 16" stroke="#dbe8d3" stroke-opacity=".12" stroke-width="5"/>']
    elif shape in ('trash','trash-full'):
        parts+=['<path d="M13 19H51L47 57H17Z" fill="url(#enamel)" stroke="url(#nickel)" stroke-width="2.5"/>',
                '<path d="M24 25V50M32 25V50M40 25V50" stroke="url(#nickel)" stroke-width="3"/>',
                '<path d="M24 12V8H40V12" fill="none" stroke="#edddb5" stroke-width="3"/>',
                '<ellipse cx="32" cy="16" rx="23" ry="5" fill="url(#nickel)" stroke="#5e736b"/>']
        if shape=='trash-full':parts+=['<path d="M19 13L20 3L32 7L36 2L46 12" fill="#f3e6c8" stroke="#899581"/>']
    else:
        parts+=['<rect x="6" y="7" width="52" height="50" rx="10" fill="url(#enamel)" stroke="url(#nickel)" stroke-width="2"/>',
                '<rect x="9" y="10" width="46" height="44" rx="7" fill="none" stroke="#d4c69f" stroke-width=".6"/>',
                '<g fill="none" stroke="#f5dfad" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'+symbol(shape)+'</g>',
                '<path d="M24 53H40" stroke="#ffb33e" stroke-width="1.2"/>']
    return ''.join(parts)+'</svg>\n'

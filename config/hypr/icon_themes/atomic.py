"""Original graphite instrument cases, phosphor tabs and brass hardware."""
from xml.sax.saxutils import escape


def svg(name,catalog,symbol):
    label,group,shape,_=catalog[name]
    defs='''<defs>
    <linearGradient id="metal" x2=".12" y2="1"><stop stop-color="#f4e7b5"/><stop offset=".45" stop-color="#aaa477"/><stop offset=".55" stop-color="#6f704d"/><stop offset="1" stop-color="#d7c797"/></linearGradient>
    <linearGradient id="steel" x2=".3" y2="1"><stop stop-color="#565b40"/><stop offset=".25" stop-color="#32392b"/><stop offset=".8" stop-color="#171e18"/><stop offset="1" stop-color="#363d29"/></linearGradient>
    <linearGradient id="phosphor" x2=".2" y2="1"><stop stop-color="#d7ff65"/><stop offset=".48" stop-color="#a5d91c"/><stop offset="1" stop-color="#5b8517"/></linearGradient>
    </defs>'''
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>{escape(label)} · Atomic Afterglow</title>',defs]
    if shape=='folder' or group=='Places' and name.startswith('folder-'):
        parts+=['<path d="M5 20V12L9 8H25L31 14H55L59 18V51H5Z" fill="url(#phosphor)" stroke="#d8d4a4"/>',
                '<path d="M7 19H57V26H7Z" fill="#d9d6bb"/>',
                '<path d="M5 24L9 20H55L59 24V52L55 56H9L5 52Z" fill="url(#steel)" stroke="url(#metal)" stroke-width="1.8"/>',
                '<path d="M10 25H54M11 51H53" stroke="#92966a" stroke-opacity=".5"/>']
        if shape!='folder':parts+=['<g transform="translate(11 15) scale(.65)" fill="none" stroke="#e6efac" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(shape)+'</g>']
        else:parts+=['<g transform="translate(32 39)" fill="none" stroke="#d8e78b" stroke-width="1.2"><ellipse rx="12" ry="4.5"/><ellipse rx="12" ry="4.5" transform="rotate(60)"/><ellipse rx="12" ry="4.5" transform="rotate(120)"/></g><circle cx="32" cy="39" r="2" fill="#baff26"/>']
        parts+=['<g fill="#cfc59c"><circle cx="10" cy="25" r="1"/><circle cx="54" cy="51" r="1"/></g>']
    elif shape=='home':
        parts+=['<path d="M11 29L32 9L53 29V55H11Z" fill="url(#steel)" stroke="url(#metal)" stroke-width="1.8"/>',
                '<path d="M4 29L32 4L60 29L56 34L32 13L8 34Z" fill="url(#metal)" stroke="#242e20"/>',
                '<path d="M28 55V36H38V55M17 31H24V40H17Z" fill="url(#phosphor)" stroke="#d7dfac"/><path d="M20.5 31V40M28 44H38" stroke="#3a4c23"/>']
    elif shape in ('computer','desktop','monitor'):
        parts+=['<path d="M8 9H56L60 13V44L56 48H8L4 44V13Z" fill="url(#steel)" stroke="url(#metal)" stroke-width="2"/>',
                '<rect x="10" y="15" width="44" height="26" rx="1" fill="#172719" stroke="#b5b389"/>',
                '<path d="M26 48H38V53H48V57H16V53H26Z" fill="url(#metal)" stroke="#4c563c"/>',
                '<g transform="translate(32 28)" fill="none" stroke="#b8ef30" stroke-width="1.5"><ellipse rx="12" ry="4"/><ellipse rx="12" ry="4" transform="rotate(60)"/><ellipse rx="12" ry="4" transform="rotate(120)"/></g><circle cx="32" cy="28" r="2.5" fill="#d7ff65"/><circle cx="51" cy="44" r="1" fill="#b5ed29"/>']
    elif shape in ('trash','trash-full'):
        parts+=['<path d="M13 17H51L48 55Q32 61 16 55Z" fill="url(#steel)" stroke="url(#metal)" stroke-width="1.7"/>',
                '<path d="M15 28Q32 32 50 28M16 48Q32 52 49 48" fill="none" stroke="#9e9e71"/>',
                '<ellipse cx="32" cy="16" rx="22" ry="5" fill="url(#metal)" stroke="#414b34"/><ellipse cx="32" cy="15" rx="17" ry="2" fill="#2a3326"/>',
                '<circle cx="32" cy="39" r="3" fill="#bcf22e"/><path d="M30 34L25 26Q20 29 20 35L29 37M35 37L44 35Q44 29 39 26L34 34M30 42L25 50Q32 53 39 50L34 42Z" fill="#bcf22e"/>']
        if shape=='trash-full':parts+=['<path d="M19 13L22 4L32 8L39 3L46 12" fill="#e1e2ba" stroke="#8c9264"/>']
    else:
        paper=shape.startswith('file-')
        contour='M14 5H39L53 19V58H14Z' if paper else 'M12 6H52L58 12V52L52 58H12L6 52V12Z'
        parts+=[f'<path d="{contour}" fill="url(#steel)" stroke="url(#metal)" stroke-width="1.7"/>']
        if paper:parts+=['<path d="M39 5V19H53M19 23H47" fill="none" stroke="#c5c99a"/><path d="M17 8H36" stroke="#b5ed29" stroke-width="3"/>']
        else:parts+=['<path d="M13 10H51L54 13V51L51 54H13L10 51V13Z" fill="none" stroke="#747e52" stroke-width=".7"/>']
        # CPU, gear and sliders keep their individual silhouettes.
        parts+=['<g fill="none" stroke="#dbeaa7" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'+symbol(shape)+'</g>',
                '<path d="M23 54H41" stroke="#b5ed29" stroke-width="1.5"/>']
        if not paper:parts+=['<g fill="#c5bd91"><circle cx="12" cy="12" r="1.1"/><circle cx="52" cy="52" r="1.1"/></g>']
    return ''.join(parts)+'</svg>\n'

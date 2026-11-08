"""Original 64px classic office icons: brass folders and ivory equipment."""
from xml.sax.saxutils import escape

DEFS = '''<defs>
<linearGradient id="gold" x2="0" y2="1"><stop stop-color="#fff0b8"/><stop offset=".18" stop-color="#e6c16b"/><stop offset="1" stop-color="#af8133"/></linearGradient>
<linearGradient id="ivory" x2="0" y2="1"><stop stop-color="#fffbed"/><stop offset=".55" stop-color="#e5dac5"/><stop offset="1" stop-color="#b0a18a"/></linearGradient>
<linearGradient id="glass" x2="1" y2="1"><stop stop-color="#9bc5cf"/><stop offset=".4" stop-color="#3e7f99"/><stop offset="1" stop-color="#25485d"/></linearGradient>
</defs>'''


def svg(name, catalog, symbol):
    label, group, shape, _ = catalog[name]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>{escape(label)} · Platform 95</title>', DEFS]
    folder = shape == 'folder' or group == 'Places' and name.startswith('folder-')
    if folder:
        out += ['<path d="M5 19V11H25L31 17H57V51H5Z" fill="url(#gold)" stroke="#392719" stroke-width="1.6"/>',
                '<path d="M8 14H24L29 19H54V29H8Z" fill="#fff7df"/>',
                '<path d="M5 24H59L55 56H5Z" fill="url(#gold)" stroke="#392719" stroke-width="1.8"/>',
                '<path d="M7 53V26H56M8 28H54" fill="none" stroke="#fff5ce" stroke-width="1.4"/>',
                '<path d="M8 54H53L57 27" fill="none" stroke="#9a702e"/>']
        if shape != 'folder':
            out += ['<g transform="translate(11 15) scale(.64)" fill="none" stroke="#382719" stroke-width="2.8" stroke-linecap="square" stroke-linejoin="miter">'+symbol(shape)+'</g>']
    elif shape == 'home':
        out += ['<path d="M10 27L32 7L54 27V57H10Z" fill="url(#ivory)" stroke="#382719" stroke-width="1.8"/>',
                '<path d="M5 27L32 4L59 27L54 32L32 13L10 32Z" fill="url(#gold)" stroke="#382719" stroke-width="1.6"/>',
                '<path d="M26 57V36H40V57M15 34H22V43H15ZM45 34H51V43H45Z" fill="url(#gold)" stroke="#382719" stroke-width="1.5"/>',
                '<path d="M33 36V56" stroke="#fff1c4"/><circle cx="36" cy="47" r="1.3" fill="#382719"/>']
    elif shape in ('computer', 'desktop', 'monitor'):
        out += ['<path d="M10 5H54V41H10Z" fill="url(#ivory)" stroke="#382719" stroke-width="1.8"/>',
                '<path d="M15 10H49V33H15Z" fill="url(#glass)" stroke="#382719" stroke-width="2"/>',
                '<path d="M17 31V12H47" fill="none" stroke="#c1dce4"/>',
                '<path d="M27 41H38V46H27ZM9 46H55L60 57H4Z" fill="url(#ivory)" stroke="#382719" stroke-width="1.6"/>',
                '<path d="M10 49H53M10 52H54M13 55H42" stroke="#7f735f"/><path d="M12 7H52M12 7V39" fill="none" stroke="#fffbed"/>',
                '<rect x="43" y="36" width="5" height="2" fill="#bd9140"/>']
    elif shape in ('trash', 'trash-full'):
        out += ['<path d="M10 17L16 55Q32 61 48 55L54 17" fill="url(#ivory)" stroke="#382719" stroke-width="1.8"/>']
        out += [f'<path d="M{x} 20L{x*.72+9:.1f} 55" stroke="#887b65" fill="none"/>' for x in (15, 23, 32, 41, 49)]
        out += ['<path d="M13 29Q32 35 51 29M15 42Q32 48 49 42" fill="none" stroke="#887b65"/>',
                '<ellipse cx="32" cy="17" rx="23" ry="7" fill="url(#ivory)" stroke="#382719" stroke-width="1.7"/><ellipse cx="32" cy="17" rx="18" ry="3.6" fill="#5a4b38"/>']
        if shape == 'trash-full':
            out += ['<path d="M17 17L14 7L25 10L32 4L39 12L49 8L47 20" fill="#fffbed" stroke="#9d8b70"/>']
    elif shape == 'network':
        out += ['<path d="M17 29V46H48V29M32 46V57" fill="none" stroke="#382719" stroke-width="3"/>']
        for x, y in ((3, 10), (35, 10), (19, 37)):
            out += [f'<g transform="translate({x} {y})"><rect width="25" height="18" fill="url(#ivory)" stroke="#382719" stroke-width="1.4"/><rect x="3" y="3" width="19" height="11" fill="url(#glass)" stroke="#382719"/><path d="M9 19H17L21 22H5Z" fill="url(#ivory)" stroke="#382719"/></g>']
    else:
        paper = shape.startswith('file-')
        contour = 'M14 5H38L51 18V58H14Z' if paper else 'M7 7H57V57H7Z'
        out += [f'<path d="{contour}" transform="translate(1 2)" fill="#382719" opacity=".25"/>',
                f'<path d="{contour}" fill="url(#ivory)" stroke="#382719" stroke-width="1.8"/>']
        if paper:
            out += ['<path d="M38 5V18H51" fill="#c9b99a" stroke="#382719"/><path d="M16 55V7H36" fill="none" stroke="#fffbed"/>']
        else:
            out += ['<path d="M9 55V9H55" fill="none" stroke="#fffbed" stroke-width="2"/><path d="M55 10V55H10" fill="none" stroke="#a49378"/>']
        out += ['<g fill="none" stroke="#382719" stroke-width="2.4" stroke-linecap="square" stroke-linejoin="round">'+symbol(shape)+'</g>']
        if not paper:
            out += ['<path d="M11 52H20" stroke="#bd9140" stroke-width="2"/>']
    return ''.join(out)+'</svg>\n'

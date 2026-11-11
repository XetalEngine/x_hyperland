"""Original brass, parchment and walnut artwork for the Mystery 98 desktop."""
from xml.sax.saxutils import escape

DEFS = '''<defs>
<linearGradient id="brass" x2=".3" y2="1"><stop stop-color="#fff0b8"/><stop offset=".23" stop-color="#dcb66a"/><stop offset=".6" stop-color="#ac772a"/><stop offset=".82" stop-color="#e0ba70"/><stop offset="1" stop-color="#79521e"/></linearGradient>
<linearGradient id="paper" x2="0" y2="1"><stop stop-color="#fff0cd"/><stop offset="1" stop-color="#c9a96f"/></linearGradient>
<linearGradient id="wood" x2="1" y2="1"><stop stop-color="#654024"/><stop offset=".4" stop-color="#352319"/><stop offset=".6" stop-color="#593620"/><stop offset="1" stop-color="#201810"/></linearGradient>
<linearGradient id="glass" x2="1" y2="1"><stop stop-color="#538774"/><stop offset=".4" stop-color="#164c36"/><stop offset="1" stop-color="#081c14"/></linearGradient>
</defs>'''


def svg(name, catalog, symbol):
    label, group, shape, _ = catalog[name]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>{escape(label)} · Windows 98 Mystery</title>', DEFS]
    if shape == 'home':
        # The key bow stays open so the silhouette reads even at 24 px.
        out += ['<g transform="rotate(38 32 32)" stroke="#342316" stroke-width="1.6"><path d="M28 27H36V57H24V51H28V46H23V40H28Z" fill="url(#brass)"/>',
                '<path d="M32 6C19 0 12 14 23 21C17 31 30 37 32 27C34 37 47 31 41 21C52 14 45 0 32 6Z" fill="url(#brass)"/>',
                '<ellipse cx="25" cy="15" rx="5" ry="6" fill="#241d15"/><ellipse cx="39" cy="15" rx="5" ry="6" fill="#241d15"/>',
                '<path d="M31 32V53M23 10Q27 5 31 10" fill="none" stroke="#fff0bf" stroke-width="1.3"/></g>']
    elif name == 'folder-documents':
        for x, y, color in ((7,39,'#5b3026'),(10,24,'#244d39'),(6,9,'#663524')):
            out += [f'<g transform="translate({x} {y})"><path d="M3 0H44L49 5V16H3Q-3 8 3 0Z" fill="{color}" stroke="#261c12" stroke-width="1.6"/>',
                    '<path d="M9 6H46V13H9" fill="url(#paper)" stroke="#aa874e"/>',
                    '<path d="M7 2V15M13 3H38M15 9H44M14 11H44" stroke="#c9a25c" fill="none" stroke-width=".8"/></g>']
    elif shape == 'folder' or group == 'Places' and name.startswith('folder-'):
        out += ['<path d="M5 20V11H25L31 17H57V53H5Z" fill="url(#brass)" stroke="#382719" stroke-width="1.6"/>',
                '<path d="M8 15H24L29 20H53V30H8Z" fill="url(#paper)"/>',
                '<path d="M5 25H59L55 56H5Z" fill="url(#paper)" stroke="#684821" stroke-width="1.8"/>',
                '<path d="M8 53V28H55M9 31H54" fill="none" stroke="#fff2d3" stroke-width="1.3"/>',
                '<path d="M8 54H53L57 28" fill="none" stroke="#9a702e"/>']
        if shape != 'folder':
            out += ['<g transform="translate(11 15) scale(.64)" fill="none" stroke="#49311a" stroke-width="2.8" stroke-linecap="square" stroke-linejoin="round">'+symbol(shape)+'</g>']
    elif shape in ('computer','desktop','monitor'):
        out += ['<path d="M9 6H55V42H9Z" fill="url(#brass)" stroke="#322214" stroke-width="1.8"/>',
                '<path d="M13 10H51V35H13Z" fill="url(#wood)" stroke="#fff0bc"/>',
                '<path d="M16 13H48V32H16Z" fill="url(#glass)" stroke="#140e09" stroke-width="1.5"/>',
                '<path d="M18 29V15H44" fill="none" stroke="#8ea581" stroke-width=".8"/>',
                '<path d="M27 42H37V47H27ZM7 47H57L61 58H3Z" fill="url(#brass)" stroke="#322214" stroke-width="1.5"/>',
                '<path d="M10 50H54M9 53H55M14 56H42" fill="none" stroke="#634b2d"/><circle cx="47" cy="38" r="1.4" fill="#dce1a4"/>']
    elif shape in ('trash','trash-full'):
        out += ['<path d="M10 17L16 54Q32 62 48 54L54 17" fill="url(#brass)" stroke="#382719" stroke-width="1.7"/>']
        for x in (18,27,36,45):
            out += [f'<path d="M{x} 24q-6 7 1 10q7 4 0 10q-5 3 0 9" fill="none" stroke="#5e411e" stroke-width="1.3"/>']
        out += ['<path d="M14 26Q32 31 50 26M16 47Q32 53 48 47" fill="none" stroke="#fff0b8" stroke-width="1.1"/>',
                '<ellipse cx="32" cy="17" rx="23" ry="7" fill="url(#brass)" stroke="#382719" stroke-width="1.6"/><ellipse cx="32" cy="17" rx="18" ry="3.7" fill="#281e14"/>']
        if shape == 'trash-full':
            out += ['<path d="M17 18L15 7L25 9L32 4L39 11L49 8L47 19" fill="url(#paper)" stroke="#9b743c"/>']
    elif shape == 'network':
        out += ['<path d="M29 43H35V54L46 57V60H18V57L29 54Z" fill="url(#brass)" stroke="#382719" stroke-width="1.4"/>',
                '<g transform="rotate(-23 32 27)" fill="none" stroke="url(#brass)" stroke-width="3"><circle cx="32" cy="27" r="20"/><ellipse cx="32" cy="27" rx="10" ry="20"/><ellipse cx="32" cy="27" rx="26" ry="8"/><path d="M32 3V51"/></g>',
                '<circle cx="32" cy="27" r="4.5" fill="url(#brass)" stroke="#5d4021"/>']
    else:
        paper = shape.startswith('file-')
        contour = 'M14 5H38L51 18V58H14Z' if paper else 'M7 7H57V57H7Z'
        out += [f'<path d="{contour}" transform="translate(1 2)" fill="#170f09" opacity=".3"/>',
                f'<path d="{contour}" fill="url(#{"paper" if paper else "wood"})" stroke="#bb9452" stroke-width="1.5"/>']
        if paper:
            out += ['<path d="M38 5V18H51" fill="#ad8a51" stroke="#5d4121"/><path d="M16 55V7H36" fill="none" stroke="#fff1cc"/>']
        else:
            out += ['<path d="M10 54V10H54M14 12H50M12 17V49" fill="none" stroke="#d7b57c" stroke-width=".8"/>',
                    '<path d="M54 12V54H12" fill="none" stroke="#2a1b0e" stroke-width="2"/>']
        ink = '#4b311a' if paper else '#ebcf95'
        out += [f'<g fill="none" stroke="{ink}" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">'+symbol(shape)+'</g>']
    return ''.join(out)+'</svg>\n'

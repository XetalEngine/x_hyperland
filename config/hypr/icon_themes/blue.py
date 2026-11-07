"""Original HyperFusion Blue artwork: beveled silver and sapphire glass."""
from xml.sax.saxutils import escape


def svg(name, catalog, symbol):
    label, group, shape, _ = catalog[name]
    folder = shape == 'folder' or group == 'Places' and name.startswith('folder-')
    document = shape.startswith('file-')
    defs = '''<defs>
<linearGradient id="metal" x2="0.25" y2="1"><stop stop-color="#f3fbff"/><stop offset=".23" stop-color="#b7cbd7"/><stop offset=".47" stop-color="#f3fbff"/><stop offset=".52" stop-color="#7894a6"/><stop offset="1" stop-color="#d4e5ee"/></linearGradient>
<linearGradient id="blue" x2=".15" y2="1"><stop stop-color="#70e2ff"/><stop offset=".12" stop-color="#27c6ff"/><stop offset=".49" stop-color="#0099e7"/><stop offset=".52" stop-color="#007bc7"/><stop offset="1" stop-color="#004b83"/></linearGradient>
<linearGradient id="case" x2="0" y2="1"><stop stop-color="#526977"/><stop offset=".15" stop-color="#263e4e"/><stop offset=".5" stop-color="#162835"/><stop offset=".52" stop-color="#0a1924"/><stop offset="1" stop-color="#263c4b"/></linearGradient>
<linearGradient id="shine" x2="0" y2="1"><stop stop-color="#ffffff" stop-opacity=".55"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient>
</defs>'''
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>{escape(label)} · HyperFusion Blue</title>',defs]
    if folder:
        parts += ['<path d="M5 19V14Q5 9 10 9H25L31 15H54Q59 15 59 21V50Q59 56 53 56H11Q5 56 5 50Z" fill="#052b45" stroke="#4aaed5"/>',
                  '<path d="M7 18V14Q7 11 11 11H24L30 17H54Q57 17 57 21V25H7Z" fill="url(#metal)"/>',
                  '<path d="M6 24Q6 20 11 20H54Q59 20 59 25L56 50Q55 54 51 54H11Q7 54 6 50Z" fill="url(#blue)" stroke="url(#metal)" stroke-width="1.3"/>',
                  '<path d="M9 24H55L53 31H10Z" fill="url(#shine)" opacity=".5"/>',
                  '<path d="M12 51H51" stroke="#6bdcff" stroke-opacity=".5"/>']
        if shape!='folder':parts += ['<g transform="translate(10 12) scale(.68)" fill="none" stroke="url(#metal)" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round">',symbol(shape),'</g>']
    elif shape=='home':
        parts += ['<path d="M13 29V54H28V39H38V54H52V29L32 11Z" fill="url(#metal)" stroke="#284d64" stroke-width="1.5"/>',
                  '<path d="M4 29 31 5Q32 4 34 6L60 29 55 34 32 14 9 34Z" fill="url(#blue)" stroke="#d7f5ff" stroke-width="1.1"/>',
                  '<path d="M28 54V39Q33 36 38 39V54" fill="#0d496d" stroke="#eefaff"/>']
    elif shape in ('computer','desktop','monitor'):
        parts += ['<rect x="5" y="10" width="54" height="37" rx="4" fill="url(#metal)" stroke="#2b465a"/>',
                  '<rect x="8" y="13" width="48" height="29" rx="1.5" fill="url(#blue)"/>',
                  '<path d="M9 14H54L9 39Z" fill="url(#shine)" opacity=".5"/>',
                  '<path d="M28 47H37V53H45V56H19V53H28Z" fill="url(#metal)" stroke="#536e80"/>',
                  '<circle cx="52" cy="44.5" r="1" fill="#00d6ff"/>']
    elif shape in ('trash','trash-full'):
        parts += ['<path d="M16 19H49L45 56H20Z" fill="url(#case)" stroke="url(#metal)" stroke-width="2"/>',
                  '<path d="M14 17H51V22H14ZM25 16V10H40V16" fill="url(#metal)" stroke="#36566b"/>',
                  '<g stroke="url(#metal)" stroke-width="2.5"><path d="M24 27 26 49M32 27V49M41 27 39 49"/></g>',
                  '<path d="M21 53H44" stroke="#00baff" stroke-width="1.5"/>']
        if shape=='trash-full':parts += ['<path d="m20 15 3-8 13 4 7-6 4 10" fill="#d4f0ff" stroke="#48758e"/>']
    else:
        contour='M17 6H39L51 18V57H17ZM39 6V19H51' if document else 'M15 7H49Q57 7 57 15V49Q57 57 49 57H15Q7 57 7 49V15Q7 7 15 7Z'
        parts += [f'<path d="{contour}" transform="translate(0 1.5)" fill="#03111d" opacity=".5"/>',
                  f'<path d="{contour}" fill="url(#case)" stroke="url(#metal)" stroke-width="1.5"/>']
        if not document:
            parts += ['<rect x="11" y="11" width="42" height="42" rx="5" fill="url(#blue)" stroke="#0a324d"/>',
                      '<path d="M13 13H51V26Q31 20 13 30Z" fill="url(#shine)" opacity=".45"/>']
        parts += ['<g fill="none" stroke="url(#metal)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">',symbol(shape),'</g>']
        parts += ['<path d="M23 54H41" stroke="#3bd7ff" stroke-width="1.3"/>']
    return ''.join(parts)+'</svg>\n'

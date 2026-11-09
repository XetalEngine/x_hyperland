"""Sculpted sapphire folders and glass tiles with distinct functional symbols."""
from xml.sax.saxutils import escape


def svg(name, catalog, symbol):
    label, group, kind, _ = catalog[name]
    folder = kind == 'folder' or group == 'Places' and name.startswith('folder-')
    doc = kind.startswith('file-')
    defs = '''<defs>
    <linearGradient id="glass" x1="0" y1="0" x2=".8" y2="1"><stop stop-color="#477793"/><stop offset=".35" stop-color="#203b55"/><stop offset="1" stop-color="#131e36"/></linearGradient>
    <linearGradient id="folder" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#54c3e2"/><stop offset=".45" stop-color="#396499"/><stop offset="1" stop-color="#55467e"/></linearGradient>
    <linearGradient id="rim" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#b3f5ff"/><stop offset=".45" stop-color="#5483ae"/><stop offset="1" stop-color="#8174bd"/></linearGradient>
    <linearGradient id="glyph" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#dcfcff"/><stop offset="1" stop-color="#27d8ec"/></linearGradient>
    </defs>'''
    if folder:
        body = '<path d="M6 22V15Q6 10 12 10H25Q28 10 31 16H51Q57 16 57 23V48H6Z" fill="#5ce7f2" stroke="#b3f5ff" stroke-width="1.1"/>'
        body += '<rect x="6" y="20" width="52" height="36" rx="8" fill="url(#folder)" stroke="url(#rim)" stroke-width="1.3"/><path d="M13 22H49Q55 22 55 27" fill="none" stroke="#b5edff" stroke-width="1" opacity=".7"/>'
        if kind != 'folder':
            body += '<g transform="translate(12 15) scale(.63)" fill="none" stroke="url(#glyph)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    elif doc:
        body = '<path d="M15 6H39L51 18V53Q51 57 47 57H19Q15 57 15 53Z" fill="url(#glass)" stroke="url(#rim)" stroke-width="1.4"/><path d="M39 6V18H51" fill="#94c9f0" stroke="#b3f5ff" stroke-width="1"/>'
        body += '<g transform="translate(10 16) scale(.66)" fill="none" stroke="url(#glyph)" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    else:
        body = '<rect x="5" y="5" width="54" height="54" rx="12" fill="url(#glass)" stroke="url(#rim)" stroke-width="1.3"/><path d="M16 8H45Q53 8 55 17" fill="none" stroke="#b5edff" stroke-width="1" opacity=".6"/>'
        body += '<g transform="translate(6 6) scale(.81)" fill="none" stroke="#061524" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        body += '<g transform="translate(6 6) scale(.81)" fill="none" stroke="url(#glyph)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    return '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>'+escape(label+' · Polaris')+'</title>'+defs+body+'</svg>\n'

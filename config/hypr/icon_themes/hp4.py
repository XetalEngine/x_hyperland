"""Original cobalt folders, carbon bodies and machined silver instruments."""
from xml.sax.saxutils import escape


def svg(name, catalog, symbol):
    label, group, kind, _ = catalog[name]
    defs = '''<defs><linearGradient id="blue" x2=".2" y2="1">
    <stop stop-color="#61b6ff"/><stop offset=".3" stop-color="#147ff0"/>
    <stop offset="1" stop-color="#073c8e"/></linearGradient>
    <linearGradient id="metal" x2=".1" y2="1"><stop stop-color="#e8f2ff"/>
    <stop offset=".5" stop-color="#9aafc9"/><stop offset="1" stop-color="#5d789e"/></linearGradient>
    <pattern id="carbon" width="6" height="6" patternUnits="userSpaceOnUse">
    <rect width="6" height="6" fill="#0b111b"/><path d="M0 6L6 0" stroke="#273448" stroke-width="1"/></pattern></defs>'''
    if kind == 'folder' or group == 'Places' and name.startswith('folder-'):
        body = '<path d="M5 20V13Q5 9 10 9H25L31 16H54Q59 16 59 22V49Q59 55 53 55H11Q5 55 5 49Z" fill="#093d88" stroke="#8abfff"/>'
        body += '<path d="M5 24Q5 19 11 19H53Q59 19 59 25V49Q59 55 53 55H11Q5 55 5 49Z" fill="url(#blue)" stroke="#8abfff" stroke-width="1.2"/>'
        body += '<path d="M10 24H53" stroke="#c4e4ff" stroke-opacity=".65"/><path d="M11 50H52" stroke="#082e66"/>'
        if kind != 'folder':
            body += '<g transform="translate(9 13) scale(.72)" fill="none" stroke="#eaf4ff" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        else:
            body += '<path d="M36 44L42 30H47L41 44ZM44 44L50 30H53L47 44Z" fill="#b4d9ff" opacity=".7"/>'
    elif kind.startswith('file-'):
        body = '<path d="M15 5H39L51 17V57H15Z" fill="url(#carbon)" stroke="url(#metal)" stroke-width="1.5"/><path d="M39 5V18H51" fill="#165ab0" stroke="#a6ceff"/>'
        body += '<g transform="translate(10 12) scale(.7)" fill="none" stroke="#72baff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g><path d="M20 52H45" stroke="#278cff" stroke-width="2"/>'
    else:
        body = '<rect x="5" y="5" width="54" height="54" rx="9" fill="url(#carbon)" stroke="#516784" stroke-width=".8"/>'
        body += '<g fill="none" stroke="url(#metal)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g><path d="M19 55H45" stroke="#278cff" stroke-width="2"/>'
    return '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>'+escape(label+' · HP4')+'</title>'+defs+body+'</svg>\n'

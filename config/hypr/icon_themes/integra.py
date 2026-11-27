"""Pearl-lilac folders and ivory instruments for the Integra desktop."""
from xml.sax.saxutils import escape


def svg(name, catalog, symbol):
    label, group, kind, _ = catalog[name]
    defs = '''<defs><linearGradient id="pearl" x2=".35" y2="1">
    <stop stop-color="#f4e8fa"/><stop offset=".45" stop-color="#cdb3dd"/>
    <stop offset="1" stop-color="#9c7cb8"/></linearGradient>
    <linearGradient id="ivory" x2=".2" y2="1"><stop stop-color="#fffaf4"/>
    <stop offset="1" stop-color="#c9b7d9"/></linearGradient>
    <linearGradient id="night" x2=".2" y2="1"><stop stop-color="#3c354e"/>
    <stop offset="1" stop-color="#191a2d"/></linearGradient></defs>'''
    if kind == 'folder' or group == 'Places' and name.startswith('folder-'):
        body = '<path d="M5 21V13Q5 9 10 9H25L31 16H54Q59 16 59 22V49Q59 55 53 55H11Q5 55 5 49Z" fill="#9578ae" stroke="#e8d8f1"/>'
        body += '<path d="M5 25Q5 20 11 20H53Q59 20 59 25V49Q59 55 53 55H11Q5 55 5 49Z" fill="url(#pearl)" stroke="#e8d8f1" stroke-width="1.1"/>'
        body += '<path d="M10 24H54" stroke="#fff8f7" stroke-opacity=".7"/>'
        if kind != 'folder':
            body += '<g transform="translate(10 14) scale(.7)" fill="none" stroke="#40304f" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    elif kind.startswith('file-'):
        body = '<path d="M15 5H39L51 17V57H15Z" fill="url(#ivory)" stroke="#9c83b1" stroke-width="1.1"/><path d="M39 5V18H51" fill="#b89acb" stroke="#f4e8fa"/>'
        body += '<g transform="translate(10 12) scale(.7)" fill="none" stroke="#714e84" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g><path d="M20 52H45" stroke="#b86f8a" stroke-width="2"/>'
    else:
        body = '<rect x="5" y="5" width="54" height="54" rx="10" fill="url(#night)" stroke="#af97c2" stroke-width="1"/>'
        body += '<g fill="none" stroke="url(#pearl)" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g><path d="M20 55H44" stroke="#e6a4bb" stroke-opacity=".7"/>'
    return '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>'+escape(label+' · Integra')+'</title>'+defs+body+'</svg>\n'

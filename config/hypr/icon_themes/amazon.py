"""Original emerald-enamel silhouettes with gold edges and leaf details."""
from xml.sax.saxutils import escape


def svg(name, catalog, symbol):
    label, group, kind, _ = catalog[name]
    folder = kind == 'folder' or group == 'Places' and name.startswith('folder-')
    document = kind.startswith('file-')
    defs = ('<defs><linearGradient id="gold" x2=".4" y2="1">'
            '<stop stop-color="#fff0b2"/><stop offset=".5" stop-color="#e6bc58"/>'
            '<stop offset="1" stop-color="#ad7931"/></linearGradient>'
            '<linearGradient id="enamel" x2=".2" y2="1">'
            '<stop stop-color="#398556"/><stop offset=".3" stop-color="#165335"/>'
            '<stop offset="1" stop-color="#03291c"/></linearGradient></defs>')
    if folder:
        body = '<path d="M6 20V14Q6 9 11 9H24L31 16H53Q58 16 58 22V49Q58 55 52 55H12Q6 55 6 49Z" fill="url(#gold)" stroke="#f6dc88" stroke-width="1.2"/>'
        body += '<path d="M7 25Q7 20 12 20H53Q57 20 57 25V49Q57 54 52 54H12Q7 54 7 49Z" fill="url(#enamel)" stroke="#edcd76" stroke-width="1.4"/>'
        body += '<path d="M11 27Q11 24 15 24H50" fill="none" stroke="#b7d28a" stroke-width=".8" opacity=".7"/>'
        if kind != 'folder':
            body += '<g transform="translate(8 13) scale(.75)" fill="none" stroke="#ffdf80" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        else:
            body += '<path d="M25 44Q20 29 42 27Q43 44 25 44Z" fill="#4e8e3e" stroke="#edcd76"/><path d="M22 48 39 30M28 41 27 33M32 37 39 38" fill="none" stroke="#f3d884"/>'
    elif document:
        body = '<path d="M16 5H39L51 18V57H16Z" fill="url(#enamel)" stroke="#edcd76" stroke-width="1.5"/><path d="M39 5V18H51" fill="#d6b75e" stroke="#ffdfa0"/>'
        body += '<g transform="translate(10 12) scale(.7)" fill="none" stroke="#fff0b2" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        body += '<path d="M22 51H44" stroke="#e2805e" stroke-width="1.5"/>'
    else:
        # Open gold instruments, not a repeated square app tile. The quiet
        # circular enamel backing keeps fine symbols legible on wallpapers.
        body = '<circle cx="32" cy="32" r="28" fill="url(#enamel)" opacity=".96"/>'
        body += '<g transform="translate(-1 -1) scale(1.03)" fill="none" stroke="url(#gold)" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        body += '<path d="M44 55Q43 48 53 47Q53 54 44 55ZM43 57 50 50" fill="#477c38" stroke="#e8c56b" stroke-width=".75"/>'
    return '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>'+escape(label+' · Amazon')+'</title>'+defs+body+'</svg>\n'

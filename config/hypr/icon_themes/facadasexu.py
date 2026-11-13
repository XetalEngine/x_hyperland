"""Ivory linework, oxblood lacquer folders and restrained copper fittings."""
from xml.sax.saxutils import escape


def svg(name,catalog,symbol):
    label,group,kind,_=catalog[name]
    folder=kind=='folder' or group=='Places' and name.startswith('folder-')
    doc=kind.startswith('file-')
    defs='<defs><linearGradient id="lacquer" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#8d1721"/><stop offset=".3" stop-color="#430e14"/><stop offset="1" stop-color="#120c0b"/></linearGradient><linearGradient id="copper" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#ecc9a4"/><stop offset=".5" stop-color="#a8643c"/><stop offset="1" stop-color="#d8a574"/></linearGradient></defs>'
    if folder:
        body='<path d="M7 21V14Q7 10 11 10H25L31 16H53Q57 16 57 21V50Q57 54 53 54H11Q7 54 7 50Z" fill="url(#lacquer)" stroke="#f2e6cc" stroke-width="1.8"/>'
        body+='<path d="M8 22H56M12 51H52" fill="none" stroke="url(#copper)" stroke-width="1.2"/>'
        if kind!='folder':body+='<g transform="translate(9 14) scale(.70)" fill="none" stroke="#f2e6cc" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    elif doc:
        body='<path d="M15 7H39L51 19V55H15Z" fill="#18100d" stroke="#f2e6cc" stroke-width="1.8"/><path d="M39 7V20H51" fill="none" stroke="url(#copper)" stroke-width="1.5"/>'
        body+='<path d="M16 48H50V54H16Z" fill="#7a101c"/>'
        body+='<g transform="translate(7 11) scale(.75)" fill="none" stroke="#f2e6cc" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    elif kind=='apps':
        body='<g fill="none" stroke="#f2e6cc" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M32 8V55M14 16Q13 34 32 37Q51 34 50 16M9 20L14 12L19 20M27 14L32 5L37 14M45 20L50 12L55 20M24 48H40"/></g><path d="M32 38V54M15 27Q20 40 27 41M49 27Q44 40 37 41" fill="none" stroke="#af2830" stroke-width="2"/>'
    else:
        # Different silhouettes remain recognizable at small launcher sizes.
        body='<g fill="#150d0b" stroke="#150d0b" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        body+='<g fill="none" stroke="#f2e6cc" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        body+='<path d="M24 53H40" stroke="url(#copper)" stroke-width="2" stroke-linecap="round"/>'
        if kind in ('computer','desktop','monitor'):
            body='<rect x="16" y="20" width="32" height="23" rx="2" fill="url(#lacquer)"/>'+body
    return '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>'+escape(label+' · 777 Facadas Exu')+'</title>'+defs+body+'</svg>\n'

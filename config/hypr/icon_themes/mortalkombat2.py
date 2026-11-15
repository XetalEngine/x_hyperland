"""Jade arcade folders and readable gold-edged system silhouettes."""
from xml.sax.saxutils import escape

# Original vector dragon medallion; scalable at taskbar and launcher sizes.
DRAGON = ('<circle cx="32" cy="32" r="27" fill="#0b1510" stroke="#e4c474" stroke-width="2.2"/>'
          '<path d="M22 51Q10 41 18 29Q21 24 29 22L26 16L34 19L38 11L40 19L49 23L46 28L39 26L44 31L36 29Q28 30 28 35Q28 41 39 40Q48 40 47 48L42 45Q35 53 22 51Z" fill="#d9b65d"/>'
          '<path d="M18 31L13 30L18 38L14 39L22 45M32 22L37 24" fill="none" stroke="#e4c474" stroke-width="1.5"/>'
          '<circle cx="39" cy="22" r="1.2" fill="#0b1510"/>')


def svg(name,catalog,symbol):
    label,group,kind,_=catalog[name]
    defs='<defs><linearGradient id="jade" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#4cbd78"/><stop offset=".25" stop-color="#167747"/><stop offset="1" stop-color="#073a25"/></linearGradient><linearGradient id="gold" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#fff0b8"/><stop offset=".5" stop-color="#b18c3b"/><stop offset="1" stop-color="#e4c474"/></linearGradient><linearGradient id="ice" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#a7e4ff"/><stop offset="1" stop-color="#16445b"/></linearGradient></defs>'
    if kind=='apps':
        body=DRAGON
    elif kind=='home':
        body='<path d="M13 28H51V54H13Z" fill="#f5e8c9" stroke="#9b7836" stroke-width="1.7"/><path d="M7 28Q23 23 32 10Q41 23 57 28ZM16 17Q27 14 32 5Q37 14 48 17Z" fill="url(#jade)" stroke="url(#gold)" stroke-width="1.8"/><path d="M27 54V38H37V54M18 34V43H23V34ZM43 34V43H48V34Z" fill="#0b2117"/><path d="M8 55H56" stroke="#e4c474" stroke-width="3"/>'
    elif kind=='folder' or group=='Places' and name.startswith('folder-'):
        body='<path d="M7 21V14H25L31 19H56V53H7Z" fill="url(#jade)" stroke="url(#gold)" stroke-width="1.8"/><path d="M8 23H55M10 51H53M10 25V48" fill="none" stroke="#a5d8a6" stroke-width="1"/>'
        if kind!='folder':body+='<g transform="translate(9 14) scale(.70)" fill="none" stroke="#fff0ca" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    elif kind.startswith('file-'):
        body='<path d="M15 7H39L51 19V55H15Z" fill="#f5e8c9" stroke="#8f753d" stroke-width="1.8"/><path d="M39 7V20H51" fill="#c6b67c" stroke="#8f753d" stroke-width="1"/><path d="M16 49H50V54H16Z" fill="#126c40"/>'
        body+='<g transform="translate(7 11) scale(.75)" fill="none" stroke="#164d32" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    else:
        body='<g fill="#0b1510" stroke="#0b1510" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        body+='<g fill="none" stroke="url(#gold)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        if kind in ('computer','desktop','monitor'):
            body='<rect x="16" y="20" width="32" height="23" rx="1" fill="url(#ice)"/>'+body
        body+='<path d="M25 55H39" stroke="#3dd489" stroke-width="2"/>'
    return '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>'+escape(label+' · Mortal Kombat II')+'</title>'+defs+body+'</svg>\n'

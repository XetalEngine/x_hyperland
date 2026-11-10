"""Original engraved brass silhouettes on obsidian and amethyst plaques."""
from xml.sax.saxutils import escape


def svg(name, catalog, symbol):
    label, group, kind, _ = catalog[name]
    folder = kind == 'folder' or group == 'Places' and name.startswith('folder-')
    document = kind.startswith('file-')
    defs = '<defs><linearGradient id="brass" x2=".7" y2="1"><stop stop-color="#f7e0b8"/><stop offset=".35" stop-color="#c6a06c"/><stop offset=".7" stop-color="#826140"/><stop offset="1" stop-color="#e8c99a"/></linearGradient><linearGradient id="stone" x2=".4" y2="1"><stop stop-color="#38303f"/><stop offset=".65" stop-color="#100e16"/><stop offset="1" stop-color="#292132"/></linearGradient></defs>'
    if folder:
        body='<path d="M6 19V12L10 8H24L31 15H52L58 21V51L54 55H10L6 51Z" fill="url(#brass)" stroke="#f2d6a8" stroke-width="1.5"/>'
        body+='<path d="M8 22H56V50L52 53H12L8 49Z" fill="url(#stone)" stroke="#aa8456"/>'
        body+='<path d="M11 25H53V48L50 50H14L11 47ZM12 28L16 24M48 50L53 45" fill="none" stroke="#d4b585" stroke-width=".6"/>'
        if kind != 'folder':body+='<g transform="translate(9 15) scale(.72)" fill="none" stroke="#e8c99a" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        else:body+='<path d="M32 28L42 38L32 48L22 38ZM32 28V48M22 38H42M27 33L37 43M37 33L27 43" fill="none" stroke="#d4b585" stroke-width="1"/>'
        body+='<circle cx="51" cy="19" r="1.2" fill="#c69ae5"/>'
    elif document:
        body='<path d="M15 5H39L51 17V57H15Z" fill="url(#stone)" stroke="url(#brass)" stroke-width="2"/><path d="M39 5V17H51M19 10H34M19 52H47" fill="none" stroke="#d4b585" stroke-width="1"/>'
        body+='<g transform="translate(10 12) scale(.7)" fill="none" stroke="#e8c99a" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    else:
        body='<path d="M13 5H51L59 13V51L51 59H13L5 51V13Z" fill="url(#stone)" stroke="url(#brass)" stroke-width="1.5"/>'
        body+='<path d="M15 8H49L56 15V49L49 56H15L8 49V15ZM8 16L16 8M48 56L56 48" fill="none" stroke="#ac885d" stroke-width=".65"/>'
        body+='<g transform="translate(5 5) scale(.84)" fill="none" stroke="#eed7b2" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        body+='<path d="M30 54L32 52L34 54L32 56Z" fill="#c69ae5"/>'
    return '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>'+escape(label+' · Leviathan')+'</title>'+defs+body+'</svg>\n'

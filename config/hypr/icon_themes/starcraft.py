"""Original command-deck vectors: cobalt folders, armored crates and instruments."""
from xml.sax.saxutils import escape

CREST = '<path d="M32 5L39 19L58 14L51 28L41 31L46 38L36 35L32 57L28 35L18 38L23 31L13 28L6 14L25 19Z" fill="url(#silver)" stroke="#102335" stroke-width="1.5"/><path d="M32 16L36 27L32 38L28 27Z" fill="#27c7ff"/><path d="M12 19L24 23M15 25L23 27M52 19L40 23M49 25L41 27" stroke="#397da8" stroke-width="2"/>'
DEFS = '''<defs>
<linearGradient id="blue" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#58c3ff"/><stop offset=".18" stop-color="#248be2"/><stop offset=".52" stop-color="#1266b2"/><stop offset="1" stop-color="#06335e"/></linearGradient>
<linearGradient id="silver" x1="0" y1="0" x2=".8" y2="1"><stop stop-color="#f0f8ff"/><stop offset=".3" stop-color="#9fb6ca"/><stop offset=".48" stop-color="#e1edf6"/><stop offset=".6" stop-color="#71899e"/><stop offset="1" stop-color="#c3d8e8"/></linearGradient>
<linearGradient id="armor" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#4b5d6f"/><stop offset=".23" stop-color="#273a4e"/><stop offset=".5" stop-color="#121f2d"/><stop offset="1" stop-color="#263b50"/></linearGradient>
<radialGradient id="reactor"><stop stop-color="#edfcff"/><stop offset=".3" stop-color="#71e2ff"/><stop offset=".6" stop-color="#078acb"/><stop offset="1" stop-color="#0a2649"/></radialGradient>
</defs>'''


def svg(name,catalog,symbol):
    label,group,kind,_ = catalog[name]
    if kind == 'apps':
        body=CREST
    elif kind == 'folder' or group == 'Places' and name.startswith('folder-'):
        body='<path d="M7 21V13L10 10H26L32 17H54L58 21V51L54 55H10L6 51Z" fill="url(#blue)" stroke="#8dc7ee" stroke-width="1.2"/><path d="M7 23H57L54 50H10Z" fill="url(#blue)" stroke="#082d52"/><path d="M10 25H54M12 51H51" fill="none" stroke="#71bfff" stroke-width="1"/>'
        if kind!='folder':
            body+='<g transform="translate(10 13) scale(.68)" fill="none" stroke="#edf9ff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        else:
            body+='<path d="M13 45H24M13 48H19" stroke="#9cdfff" stroke-width="1.3"/>'
    elif kind=='home' or kind in ('archive','executable'):
        body='<path d="M7 17L29 7L56 18V50L33 58L7 48Z" fill="url(#armor)" stroke="url(#silver)" stroke-width="2"/><path d="M7 17L33 28L56 18M33 28V58" fill="none" stroke="#8ba1b8" stroke-width="1.5"/><path d="M13 16L35 25M24 10L49 21M13 21V44L19 47V24M43 24V51L49 49V22" fill="none" stroke="#b4a578" stroke-width="3"/><path d="M35 34L43 31V45L35 48Z" fill="url(#reactor)" stroke="#77d9ff"/><circle cx="14" cy="34" r="2" fill="#26caff"/>'
        if kind=='archive':body+='<path d="M25 21V50" stroke="#dfb971" stroke-width="3" stroke-dasharray="2 2"/>'
        if kind=='executable':body+='<path d="M19 26L25 36L20 45L14 35Z" fill="#59d4ff"/>'
    elif kind in ('computer','desktop','monitor','terminal'):
        body='<path d="M6 8H55L59 12V45L55 49H7L3 45V12Z" fill="url(#armor)" stroke="url(#silver)" stroke-width="2"/><path d="M10 14H51V40H10Z" fill="url(#blue)" stroke="#080e19" stroke-width="2"/><path d="M27 49V54H20L17 59H47L44 54H37V49" fill="url(#armor)" stroke="url(#silver)" stroke-width="1.5"/><path d="M20 44H38" stroke="#28caff" stroke-width="1.5"/><circle cx="51" cy="44" r="1.5" fill="#27c7ff"/>'
        if kind=='terminal':body+='<path d="M17 21L23 26L17 31M28 32H39" fill="none" stroke="#e4f9ff" stroke-width="2.5"/>'
        elif kind=='monitor':body+='<path d="M14 30H23L27 19L32 35L37 25H47" fill="none" stroke="#a5efff" stroke-width="2"/>'
        else:body+='<g transform="translate(17 13) scale(.45)">'+CREST+'</g>'
    elif kind=='network':
        body='<path d="M27 37L19 54H45L36 37M13 56H50" fill="url(#armor)" stroke="url(#silver)" stroke-width="3"/><path d="M12 13Q13 46 42 42L49 35Z" fill="url(#blue)" stroke="url(#silver)" stroke-width="2"/><path d="M13 13Q32 6 49 35Q30 42 13 13Z" fill="#1c4f72" stroke="#b5d8ed" stroke-width="1.5"/><path d="M28 27L41 13" stroke="#c3e4f6" stroke-width="2"/><circle cx="42" cy="12" r="3" fill="#6cddff"/><path d="M47 8Q56 15 52 25M50 4Q63 13 57 27" fill="none" stroke="#27c7ff" stroke-width="1.7"/>'
    elif kind in ('trash','trash-full'):
        body='<path d="M13 16H51L47 55H17Z" fill="url(#armor)" stroke="url(#silver)" stroke-width="2"/><ellipse cx="32" cy="16" rx="21" ry="6" fill="url(#silver)" stroke="#172c41"/><ellipse cx="32" cy="15" rx="15" ry="3.5" fill="#0b2339"/><path d="M21 23L23 48M43 23L41 48" stroke="#55738e" stroke-width="2"/><path d="M30 27L24 37H29M36 31L42 41H36M34 47H24L27 42" fill="none" stroke="#39c7ff" stroke-width="2.5"/>'
        if kind=='trash-full':body+='<path d="M22 15L19 5L29 8L32 17M33 16L38 4L46 10L43 17" fill="#b8d2e2" stroke="#40677d"/>'
    elif kind.startswith('file-'):
        body='<path d="M15 6H38L51 19V55L48 58H15Z" fill="#dceaf6" stroke="#6d93b3" stroke-width="1.5"/><path d="M38 6V20H51" fill="#99bddb" stroke="#6d93b3"/><path d="M16 51H50V56H16Z" fill="url(#blue)"/>'
        body+='<g transform="translate(6 10) scale(.78)" fill="none" stroke="#164f7b" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    else:
        body='<g fill="#0b1a29" stroke="#0b1a29" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        body+='<g fill="none" stroke="url(#silver)" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        if kind in ('gear','chip'):
            body+='<circle cx="32" cy="32" r="10" fill="url(#reactor)" stroke="#74d6ff" stroke-width="1.4"/><path d="M27 32H37M32 27V37" stroke="#c3f5ff" stroke-width="1"/>'
        else:body+='<path d="M25 56H39" stroke="#27c7ff" stroke-width="2"/>'
    return '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>'+escape(label+' · StarCraft II')+'</title>'+DEFS+body+'</svg>\n'

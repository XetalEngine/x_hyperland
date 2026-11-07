"""Original Blackwood icons: brass hardware, walnut cases and sage glass."""
from xml.sax.saxutils import escape


def svg(name,catalog,symbol):
    label,group,shape,_=catalog[name]
    defs='''<defs>
    <linearGradient id="brass" x2=".1" y2="1"><stop stop-color="#f5e3b7"/><stop offset=".3" stop-color="#c7ab72"/><stop offset=".5" stop-color="#8b7148"/><stop offset=".55" stop-color="#c2a46c"/><stop offset="1" stop-color="#e7d09a"/></linearGradient>
    <linearGradient id="wood" x2=".3" y2="1"><stop stop-color="#584631"/><stop offset=".3" stop-color="#362c22"/><stop offset="1" stop-color="#191e18"/></linearGradient>
    <linearGradient id="glass" x2=".5" y2="1"><stop stop-color="#72856e"/><stop offset=".48" stop-color="#3c5043"/><stop offset=".49" stop-color="#25362e"/><stop offset="1" stop-color="#445b47"/></linearGradient>
    </defs>'''
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>{escape(label)} · Blackwood</title>',defs]
    if shape=='folder' or group=='Places' and name.startswith('folder-'):
        parts+=['<path d="M5 18V12Q5 9 9 9H25L31 15H55Q59 15 59 20V52H5Z" fill="url(#brass)" stroke="#51442b"/>',
                '<path d="M7 19H57V25H7Z" fill="#ede1bb"/>',
                '<path d="M4 24Q4 21 8 21H56Q60 21 60 25L57 54Q57 57 53 57H10Q7 57 7 54Z" fill="url(#wood)" stroke="url(#brass)" stroke-width="2"/>',
                '<path d="M9 27H55M10 31Q25 33 53 30M11 52H53" fill="none" stroke="#bf9c63" stroke-opacity=".35" stroke-width=".8"/>',
                '<g fill="#d8bf87"><circle cx="11" cy="26" r="1"/><circle cx="53" cy="26" r="1"/><circle cx="12" cy="52" r="1"/><circle cx="52" cy="52" r="1"/></g>']
        if shape!='folder':parts+=['<g transform="translate(12 17) scale(.62)" fill="none" stroke="#e8d09a" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(shape)+'</g>']
        else:parts+=['<path d="M25 36H39V44H25Z" fill="url(#brass)" stroke="#7b653f"/><path d="M29 40H35" stroke="#382e20"/>']
    elif shape.startswith('file-'):
        parts+=['<path d="M13 5H39L53 20V56Q53 59 49 59H15Q12 59 12 55V9Z" fill="#ebdfbf" stroke="#86714c" stroke-width="1.2"/>',
                '<path d="M39 5V20H53" fill="url(#brass)" stroke="#9a8358"/>',
                '<path d="M17 25H47M17 52H47" stroke="#a88d5e"/>',
                '<g transform="translate(12 16) scale(.64)" fill="none" stroke="#4a563e" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(shape)+'</g>']
    elif shape=='home':
        parts+=['<path d="M10 29L32 8L54 29V56H10Z" fill="url(#wood)" stroke="url(#brass)" stroke-width="1.8"/>',
                '<path d="M5 29L32 4L59 29L55 33L32 12L9 33Z" fill="#3c4237" stroke="#d6bd88"/>',
                '<path d="M27 56V36H39V56" fill="url(#brass)" stroke="#8d754c"/><rect x="16" y="30" width="7" height="10" fill="#e6c77e" stroke="#342d20"/>',
                '<path d="M19.5 30V40M16 35H23M43 19V9H49V25" fill="none" stroke="#b8a176"/>']
    elif shape in ('computer','desktop'):
        parts+=['<rect x="5" y="8" width="54" height="38" rx="3" fill="url(#wood)" stroke="url(#brass)" stroke-width="2"/>',
                '<rect x="10" y="13" width="44" height="27" rx="1" fill="url(#glass)" stroke="#e0c897"/>',
                '<path d="M26 46H38V52H47L51 56H13L17 52H26Z" fill="url(#brass)" stroke="#7e6b49"/>',
                '<path d="M14 36L42 15" stroke="#dce4d5" stroke-width="4" stroke-opacity=".1"/>']
    elif shape in ('trash','trash-full'):
        parts+=['<path d="M14 18H50L46 57H18Z" fill="url(#wood)" stroke="url(#brass)" stroke-width="2"/>',
                '<path d="M22 24L24 51M32 24V52M42 24L40 51" stroke="url(#brass)" stroke-width="2.5"/>',
                '<path d="M24 12V7Q32 3 40 7V12" fill="none" stroke="#dbc38f" stroke-width="2.5"/>',
                '<ellipse cx="32" cy="16" rx="23" ry="5" fill="url(#brass)" stroke="#4b402d"/>']
        if shape=='trash-full':parts+=['<path d="M18 13L21 3L31 8L39 3L47 12" fill="#eee0b8" stroke="#958061"/>']
    elif shape=='network':
        parts+=['<circle cx="32" cy="31" r="24" fill="url(#wood)" stroke="url(#brass)" stroke-width="2.2"/>',
                '<g fill="none" stroke="#dec18a" stroke-width="1.5"><ellipse cx="32" cy="31" rx="11" ry="24"/><path d="M8 31H56M12 18Q32 29 52 18M12 44Q32 34 52 44M32 7V55"/></g>']
    else:
        parts+=['<path d="M12 6H52L58 12V52L52 58H12L6 52V12Z" fill="url(#wood)" stroke="url(#brass)" stroke-width="1.8"/>',
                '<path d="M13 10H51L54 13V51L51 54H13L10 51V13Z" fill="none" stroke="#9d875b" stroke-width=".7"/>',
                '<g fill="none" stroke="#ead4a1" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'+symbol(shape)+'</g>',
                '<g fill="#cdb581"><circle cx="12" cy="12" r="1"/><circle cx="52" cy="12" r="1"/><circle cx="12" cy="52" r="1"/><circle cx="52" cy="52" r="1"/></g>']
    return ''.join(parts)+'</svg>\n'

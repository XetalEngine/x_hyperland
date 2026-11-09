"""Neon outline silhouettes: cyan architecture and magenta interior symbols."""
from xml.sax.saxutils import escape


def svg(name,catalog,symbol):
    label,group,kind,_=catalog[name]
    folder=kind=='folder' or group=='Places' and name.startswith('folder-')
    doc=kind.startswith('file-')
    defs='''<defs><linearGradient id="metal" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#6bf5ff"/><stop offset=".5" stop-color="#32d2e6"/><stop offset="1" stop-color="#ed38b5"/></linearGradient><linearGradient id="glass" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#273447"/><stop offset="1" stop-color="#0c1420"/></linearGradient></defs>'''
    if folder:
        outline='M7 20V14Q7 10 12 10H25L31 17H52Q57 17 57 22V51Q57 55 53 55H11Q7 55 7 51Z'
        body=f'<path d="{outline}" fill="url(#glass)" stroke="url(#metal)" stroke-width="2.5"/><path d="M9 22V15Q9 13 12 13H24L30 20H53" fill="none" stroke="#42e5f5" stroke-width="4"/>'
        if kind!='folder':body+='<g transform="translate(9 12) scale(.73)" fill="none" stroke="#f15ac5" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        else:body+='<path d="M15 48H32" stroke="#ed38b5" stroke-width="1.5"/>'
    elif doc:
        body='<path d="M16 7H39L51 19V56H16Z" fill="url(#glass)" stroke="#57eaf6" stroke-width="2"/><path d="M39 7V20H51" fill="none" stroke="#ef53c1" stroke-width="2"/>'
        body+='<g transform="translate(7 13) scale(.76)" fill="none" stroke="#ef53c1" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    else:
        body='<g fill="#111b28" stroke="#080e16" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        body+='<g fill="none" stroke="url(#metal)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        body+='<path d="M20 57H44" stroke="#ed38b5" stroke-width="1.3" opacity=".75"/>'
    return '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>'+escape(label+' · Midnight Run')+'</title>'+defs+body+'</svg>\n'

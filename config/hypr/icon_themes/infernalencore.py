"""Original riveted brass silhouettes and crimson instrument symbols."""
from xml.sax.saxutils import escape


def svg(name,catalog,symbol):
    label,group,kind,_=catalog[name]
    folder=kind=='folder' or group=='Places' and name.startswith('folder-')
    doc=kind.startswith('file-')
    defs='''<defs><linearGradient id="brass" x1="0" y1="0" x2=".7" y2="1"><stop stop-color="#fff0d1"/><stop offset=".22" stop-color="#e6ad72"/><stop offset=".65" stop-color="#8c492c"/><stop offset="1" stop-color="#f0c493"/></linearGradient><linearGradient id="iron" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#392727"/><stop offset=".6" stop-color="#100c0d"/><stop offset="1" stop-color="#281a18"/></linearGradient></defs>'''
    if folder:
        body='<path d="M7 19V13L11 9H25L31 16H52L57 21V51L53 55H11L7 51Z" fill="url(#iron)" stroke="url(#brass)" stroke-width="2.4"/>'
        body+='<path d="M9 20V14L12 12H24L30 19H53M10 24H54" fill="none" stroke="#e6ad72" stroke-width="2"/>'
        body+='<path d="M8 29V23H14M50 23H56V29M8 45V51H14M50 51H56V45" fill="none" stroke="#f4dfbd" stroke-width="1.2"/>'
        if kind!='folder':body+='<g transform="translate(9 13) scale(.72)" fill="none" stroke="#ff472c" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        else:body+='<path d="M18 46H46" stroke="#a40815" stroke-width="2"/>'
        for x,y in ((11,26),(53,26),(11,48),(53,48)):body+=f'<circle cx="{x}" cy="{y}" r="1" fill="#c78e5b"/>'
    elif doc:
        body='<path d="M15 7H39L51 19V55H15Z" fill="url(#iron)" stroke="url(#brass)" stroke-width="2.1"/><path d="M39 7V20H51M18 10V52H48" fill="none" stroke="#b66d40" stroke-width="1"/>'
        body+='<g transform="translate(7 13) scale(.75)" fill="none" stroke="#ff583a" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    else:
        # Preserve each recognisable glyph; gear, sliders and CPU stay distinct.
        body='<g fill="#181414" stroke="#36150f" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        body+='<g fill="none" stroke="url(#brass)" stroke-width="3.3" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        body+='<g fill="none" stroke="#ff472c" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    return '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>'+escape(label+' · Infernal Encore')+'</title>'+defs+body+'</svg>\n'

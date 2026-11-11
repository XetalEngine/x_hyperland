"""Original comic silhouettes: orange folders, violet steel and dark ink edges."""
from xml.sax.saxutils import escape

DEFS = '''<defs>
<linearGradient id="orange" x2=".3" y2="1"><stop stop-color="#ffe080"/><stop offset=".2" stop-color="#ffbc2c"/><stop offset="1" stop-color="#e88609"/></linearGradient>
<linearGradient id="violet" x2="1" y2="1"><stop stop-color="#e6c8ff"/><stop offset=".35" stop-color="#bc74db"/><stop offset="1" stop-color="#783aa1"/></linearGradient>
<linearGradient id="steel" x2=".2" y2="1"><stop stop-color="#ded6e5"/><stop offset=".5" stop-color="#a59aaf"/><stop offset="1" stop-color="#61536d"/></linearGradient>
<linearGradient id="glass" x2="1" y2="1"><stop stop-color="#7a6ed5"/><stop offset=".5" stop-color="#41418c"/><stop offset="1" stop-color="#242044"/></linearGradient>
</defs>'''


def svg(name,catalog,symbol):
    label,group,kind,_=catalog[name]
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>{escape(label)} · Prison Break</title>',DEFS]
    folder=kind=='folder' or group=='Places' and name.startswith('folder-')
    if folder:
        out+=['<path d="M6 21V13Q6 9 11 9H25L31 16H53Q58 16 58 21V52Q58 56 53 56H10Q6 56 6 52Z" fill="url(#orange)" stroke="#1c1421" stroke-width="3"/>',
              '<path d="M6 26Q6 22 10 22H56Q60 22 59 27L56 51Q56 55 52 55H10Q6 55 6 51Z" fill="url(#orange)" stroke="#1c1421" stroke-width="2.6"/>',
              '<path d="M10 20V14H24L30 20M10 27H54" fill="none" stroke="#fff1ae" stroke-width="1.6"/>',
              '<path d="M13 48L25 36M20 49L30 39" stroke="#ffd674" stroke-width="2" opacity=".45"/>']
        if kind!='folder':out+=['<g transform="translate(11 14) scale(.65)" fill="none" stroke="#312018" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>']
    elif kind=='home':
        out+=['<path d="M13 28H51V56H13Z" fill="url(#orange)" stroke="#201522" stroke-width="3"/>',
              '<path d="M5 27L30 5Q32 3 34 5L59 27L53 33L32 15L11 33Z" fill="#ef653a" stroke="#201522" stroke-width="3"/>',
              '<path d="M26 56V37H40V56" fill="#593346" stroke="#201522" stroke-width="2.5"/>',
              '<path d="M20 28H25V34H20Z" fill="#ffeebc" stroke="#543033"/><path d="M14 23L31 9" stroke="#ffd790" stroke-width="2"/>']
    elif kind in ('computer','desktop','monitor'):
        out+=['<rect x="7" y="6" width="50" height="36" rx="4" fill="url(#violet)" stroke="#191121" stroke-width="3"/>',
              '<path d="M12 11H52V34H12Z" fill="url(#glass)" stroke="#241c32" stroke-width="2"/>',
              '<path d="M14 30L34 13H42L22 32Z" fill="#af8af1" opacity=".32"/>',
              '<path d="M27 42H37V50H27ZM19 50H45L49 56H15Z" fill="url(#violet)" stroke="#191121" stroke-width="2.5"/>',
              '<path d="M11 8H52M20 52H43" stroke="#efd7ff" stroke-width="1.2"/><circle cx="48" cy="38" r="1.2" fill="#ffbf39"/>']
    elif kind in ('trash','trash-full'):
        out+=['<path d="M12 17L17 54Q32 59 47 54L52 17" fill="url(#steel)" stroke="#211729" stroke-width="3"/>',
              '<path d="M22 25L24 49M32 25V51M42 25L40 49" stroke="#4b3b57" stroke-width="3" stroke-linecap="round"/>',
              '<path d="M15 23L19 49" stroke="#ece2f2" stroke-width="1.4"/>',
              '<ellipse cx="32" cy="16" rx="23" ry="6" fill="url(#steel)" stroke="#211729" stroke-width="2.5"/>',
              '<path d="M25 10V5H39V10" fill="none" stroke="#211729" stroke-width="3"/>']
        if kind=='trash-full':out+=['<path d="M20 14L17 5L27 8L33 2L41 11L48 7L46 17" fill="#eadcf5" stroke="#51405c" stroke-width="1.2"/>']
    elif kind=='network':
        out+=['<path d="M32 23V37M17 45L32 37L47 45" stroke="#211729" stroke-width="6" fill="none"/>',
              '<path d="M32 23V37M17 45L32 37L47 45" stroke="#cfaddf" stroke-width="2.5" fill="none"/>']
        for x,y in ((32,14),(15,48),(49,48)):
            out+=[f'<circle cx="{x}" cy="{y}" r="10" fill="url(#violet)" stroke="#211729" stroke-width="2.6"/><path d="M{x-6} {y-3}Q{x-4} {y-8} {x+2} {y-6}" stroke="#f1d6ff" stroke-width="1.5" fill="none"/>']
    elif kind.startswith('file-'):
        out+=['<path d="M14 5H38L52 19V58H14Z" fill="#e8dcef" stroke="#211729" stroke-width="2.6"/><path d="M38 5V19H52" fill="#b08bc5" stroke="#211729" stroke-width="2"/>',
              '<g transform="translate(6 11) scale(.79)" fill="none" stroke="#5d2c78" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>']
    else:
        # Keep each equipment silhouette distinct, with a thick comic outline.
        out+=['<g fill="#292031" stroke="#1a111e" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>',
              '<g fill="none" stroke="url(#violet)" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>']
    return ''.join(out)+'</svg>\n'

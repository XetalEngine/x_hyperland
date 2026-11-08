"""Original plum leather, mushroom caps, ivory roots and moss at 64px."""
from xml.sax.saxutils import escape

DEFS='''<defs>
<linearGradient id="metal" x2=".2" y2="1"><stop stop-color="#fff0d9"/><stop offset=".5" stop-color="#cdb39e"/><stop offset="1" stop-color="#89717e"/></linearGradient>
<linearGradient id="plum" x2=".2" y2="1"><stop stop-color="#94728f"/><stop offset=".35" stop-color="#60475f"/><stop offset="1" stop-color="#302333"/></linearGradient>
<linearGradient id="cap" x2=".2" y2="1"><stop stop-color="#dfb9ed"/><stop offset=".5" stop-color="#ad85bc"/><stop offset="1" stop-color="#68466e"/></linearGradient>
<linearGradient id="glow" x2="0" y2="1"><stop stop-color="#fff0cc"/><stop offset="1" stop-color="#c99c6f"/></linearGradient>
</defs>'''
ROOTS='<path d="M8 52Q18 54 23 49L29 52M13 53L10 46M18 52L17 48M23 49L22 43M29 52L33 48M48 12L51 17L58 19M51 17L54 10" fill="none" stroke="#d7bdc6" stroke-width=".85"/>'
MOSS='<g fill="#8b9465"><ellipse cx="12" cy="54" rx="5" ry="1.4"/><ellipse cx="51" cy="54" rx="5.5" ry="1.2"/><path d="M9 54L7 49L11 52L13 48L15 54M49 54L49 49L52 52L54 48L55 54"/></g>'


def cap(x,y,s=1):
    return f'''<g transform="translate({x} {y}) scale({s})">
    <path d="M-2 0Q0 12-4 17Q1 19 5 17Q1 9 3 0" fill="url(#metal)" stroke="#70526d" stroke-width=".8"/>
    <path d="M-17 1Q-11-11 0-11Q10-11 17 1Q0 8-17 1Z" fill="url(#cap)" stroke="#f0dfd2" stroke-width="1"/>
    <path d="M-14 2Q0 8 14 2Q0 2-14 2Z" fill="url(#glow)"/>
    <path d="M-11 2L-4 5M-6 2L-2 6M6 2L2 6M11 2L4 5" stroke="#c09b83" stroke-width=".7"/>
    <g fill="#efdfd4"><ellipse cx="-6" cy="-4" rx="2.2" ry="1"/><ellipse cx="5" cy="-5" rx="2.5" ry="1.2"/><circle cx="1" cy="-8" r=".8"/></g></g>'''


def svg(name,catalog,symbol):
    label,group,shape,_=catalog[name]
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>{escape(label)} · Mycelium</title>',DEFS]
    folder=shape=='folder' or group=='Places' and name.startswith('folder-')
    if folder:
        out+=['<path d="M5 21V15Q5 10 10 10H24L30 16H53Q59 16 59 22V50H5Z" fill="url(#metal)" stroke="#997c8f"/>',
              '<path d="M8 21H57V30H8Z" fill="#efddce"/>',
              '<path d="M6 26Q6 22 12 22H53Q59 22 58 28L55 52Q54 57 49 56H13Q7 56 7 51Z" fill="url(#plum)" stroke="url(#metal)" stroke-width="1.7"/>',
              '<path d="M9 26Q23 29 33 24T56 26" fill="none" stroke="#edd1dc" stroke-opacity=".7"/>']
        if shape=='folder':out+=[cap(32,37,.65)]
        else:out+=['<g transform="translate(10 14) scale(.68)" fill="none" stroke="#f2ddc5" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'+symbol(shape)+'</g>']
        out+=[ROOTS,MOSS]
    elif shape=='home':
        out+=['<path d="M17 29Q19 42 16 55Q31 60 47 55Q43 42 46 29Z" fill="url(#plum)" stroke="url(#metal)" stroke-width="1.5"/>',
              '<path d="M26 56V43Q32 33 38 43V56M19 35H24V42H19ZM40 34H44V42H40Z" fill="url(#glow)" stroke="#eed5b8"/>',
              '<path d="M32 40V56M27 48H37" stroke="#8e657b"/>',cap(32,24,1.65),MOSS]
    elif shape in ('computer','desktop','monitor'):
        out+=['<path d="M9 13Q8 10 14 10H51Q57 11 56 17L54 43Q54 47 49 47H13Q7 47 7 41Z" fill="url(#plum)" stroke="url(#metal)" stroke-width="1.8"/>',
              '<rect x="13" y="16" width="37" height="25" rx="3" fill="#35283e" stroke="#c1a2cd"/>',
              '<path d="M15 38L48 18V38Z" fill="#c9a1df" fill-opacity=".13"/>',
              '<path d="M27 47H36L39 53H48L52 57H12L17 53H25Z" fill="url(#metal)" stroke="#77596e"/>',cap(8,37,.36),ROOTS,MOSS]
    elif shape in ('trash','trash-full'):
        out+=['<path d="M12 20H52L46 53Q32 60 18 53Z" fill="url(#plum)" stroke="url(#metal)" stroke-width="1.7"/>']
        for x in (16,24,32,40,48):
            out+=[f'<path d="M{x} 23Q{64-x} 41 {x*.65+11:.1f} 54M{x} 23Q{x} 39 {64-(x*.65+11):.1f} 54" fill="none" stroke="#d3b8b9" stroke-width="1"/>']
        out+=['<ellipse cx="32" cy="20" rx="22" ry="6" fill="url(#metal)" stroke="#8d6c87"/><ellipse cx="32" cy="19" rx="17" ry="3" fill="#332236"/>',cap(25,14,.6),cap(41,18,.4)]
        if shape=='trash-full':out+=['<path d="M17 16L18 7L27 9L32 3L39 13L46 9L48 16" fill="#e6d8da" stroke="#b092bd"/>']
    elif shape=='network':
        out+=['<circle cx="32" cy="32" r="24" fill="url(#plum)" stroke="url(#metal)" stroke-width="1.5"/>',
              '<g fill="none" stroke="#e3c7d1" stroke-width="1.3"><ellipse cx="32" cy="32" rx="11" ry="24"/><ellipse cx="32" cy="32" rx="24" ry="10"/><path d="M12 18L49 45M15 49L49 15"/></g>']
        for x,y in ((32,8),(9,31),(54,32),(32,56),(18,18),(46,47)):
            out+=[f'<circle cx="{x}" cy="{y}" r="3.2" fill="url(#glow)" stroke="#b296b6"/>']
    elif shape=='apps':out+=[cap(32,30,1.6),ROOTS,MOSS]
    else:
        paper=shape.startswith('file-')
        contour='M15 6H38L51 19V56Q34 60 14 55Z' if paper else 'M15 8Q30 3 49 9Q58 12 57 29L55 49Q53 58 39 57L16 56Q7 54 7 41L8 20Q8 10 15 8Z'
        out+=[f'<path d="{contour}" fill="url(#plum)" stroke="url(#metal)" stroke-width="1.6"/>']
        if paper:out+=['<path d="M38 6V19H51" fill="#b18cb7" stroke="#e4cfda"/>']
        out+=['<g fill="none" stroke="#f1dfc8" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'+symbol(shape)+'</g>',ROOTS]
        if not paper:out+=[MOSS]
    return ''.join(out)+'</svg>'

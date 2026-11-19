"""Original editable 64px artwork for the four Killer Instinct 1994 variations."""
from xml.sax.saxutils import escape

PALETTES={
 'killerinstinct':('#efe8f6','#b5a7c1','#8a4eb5','#3c2055','#18121f','#ffbd6b'),
 'kitemple':('#fff0b7','#c9a75b','#3eb878','#115035','#071b13','#f3d77e'),
 'kiprimal':('#eee5ca','#ada98c','#798d54','#35462d','#171d12','#bc9eea'),
 'kifireice':('#f3faff','#98b8c9','#ffb34f','#9a4c10','#12212b','#70ddef')}


def svg(name,catalog,symbol,style='killerinstinct'):
    label,group,kind,_=catalog[name];light,metal,accent,shade,base,second=PALETTES[style]
    defs=f'''<defs><linearGradient id="metal" x2=".25" y2="1"><stop stop-color="{light}"/><stop offset=".33" stop-color="{metal}"/><stop offset=".5" stop-color="{light}"/><stop offset=".65" stop-color="{metal}"/><stop offset="1" stop-color="{shade}"/></linearGradient><linearGradient id="face" x2=".25" y2="1"><stop stop-color="{accent}"/><stop offset=".35" stop-color="{shade}"/><stop offset="1" stop-color="{base}"/></linearGradient><radialGradient id="light"><stop stop-color="{light}"/><stop offset=".3" stop-color="{second}"/><stop offset="1" stop-color="{shade}"/></radialGradient></defs>'''
    mark=f'<path d="M14 12L23 8V29L37 14L42 19L29 33L44 51L33 48L23 37V52L14 55ZM45 9L54 12V54L45 51Z" fill="url(#metal)" stroke="{base}" stroke-width="1.3"/>'
    if style=='killerinstinct':trim=f'<path d="M12 50H51M12 23H53" stroke="{light}" stroke-opacity=".65"/><path d="M14 53H25" stroke="{second}" stroke-width="1.4"/>'
    elif style=='kitemple':trim=f'<path d="M11 28V24H17M47 24H53V30M11 44V50H17M47 50H53V44" fill="none" stroke="{metal}" stroke-width="1.5"/>'
    elif style=='kiprimal':trim=f'<path d="M37 51L43 43M42 51L48 43M47 51L53 43" stroke="{second}" stroke-width="1.1"/><path d="M12 26H15M21 26H23M30 26H32" stroke="{metal}"/>'
    else:trim=f'<path d="M11 25H31M11 50H31" stroke="{accent}" stroke-width="1.3"/><path d="M33 25H53M33 50H53" stroke="{second}" stroke-width="1.3"/>'
    if kind=='apps':
        body=mark
    elif kind=='folder' or group=='Places' and name.startswith('folder-'):
        outline='M6 19V12L10 9H26L32 16H54L58 20V52L54 56H10L6 52Z'
        if style=='kiprimal':outline='M6 18Q6 10 12 10H25L33 17H53Q58 17 58 23V50Q58 56 52 56H12Q6 56 6 50Z'
        body=f'<path d="{outline}" fill="url(#metal)" stroke="{base}" stroke-width="1.5"/><path d="M7 22H57L54 53H10Z" fill="url(#face)" stroke="{metal}" stroke-width="1.4"/>'+trim
        if kind!='folder':body+=f'<g transform="translate(11 14) scale(.66)" fill="none" stroke="{light}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    elif kind in ('computer','desktop'):
        # Full-height 1994 upright silhouette, with marquee, CRT, joystick and coin slot.
        body=f'<path d="M15 4H47L51 17L46 21L45 34L54 40V59H11V40L18 34L17 21L12 17Z" fill="{base}" stroke="url(#metal)" stroke-width="2"/><path d="M17 7H46L47 15H15Z" fill="url(#face)" stroke="{metal}"/><path d="M21 20H42L44 34H19Z" fill="url(#light)" stroke="{metal}"/><path d="M18 36H46L51 41H13Z" fill="url(#metal)"/><path d="M21 39V34M37 39V34" stroke="{base}" stroke-width="1.5"/><circle cx="21" cy="33" r="2.3" fill="{accent}"/><circle cx="37" cy="33" r="2.3" fill="{second}"/><path d="M27 45H38V54H27Z" fill="{shade}" stroke="{metal}"/><path d="M30 48V51M35 48V51" stroke="{second}"/><path d="M23 11H40" stroke="{light}" stroke-width="1.5"/>'
    elif kind=='home':
        body=f'<path d="M11 28H53V56H11Z" fill="url(#face)" stroke="{metal}" stroke-width="1.5"/><path d="M5 29L32 7L59 29L54 34L32 16L10 34Z" fill="url(#metal)" stroke="{base}"/><path d="M26 35H38V56H26Z" fill="{base}" stroke="{metal}"/><path d="M14 34H21V43H14M43 34H50V43H43" fill="url(#light)" stroke="{metal}"/>'
    elif kind in ('trash','trash-full'):
        body=f'<path d="M14 19H50L46 56H18Z" fill="url(#face)" stroke="{metal}" stroke-width="2"/><path d="M10 14H54V21H10ZM25 8H39V14H25Z" fill="url(#metal)" stroke="{base}"/><path d="M23 27L25 49M32 27V49M41 27L39 49" stroke="{light}" stroke-width="2"/>'
        if kind=='trash-full':body+=f'<path d="M18 14L16 4L26 7L29 14M35 14L40 3L48 8L45 14" fill="{light}" stroke="{metal}"/>'
    elif kind.startswith('file-'):
        body=f'<path d="M14 5H39L52 18V58H14Z" fill="{light}" stroke="{metal}" stroke-width="1.5"/><path d="M39 5V19H52" fill="url(#metal)" stroke="{shade}"/><path d="M15 50H51V57H15Z" fill="url(#face)"/>'
        body+=f'<g transform="translate(6 10) scale(.78)" fill="none" stroke="{shade}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
    else:
        plate={'killerinstinct':'M10 7H54L59 12V52L54 57H10L5 52V12Z','kitemple':'M32 3L61 32L32 61L3 32Z','kiprimal':'M12 7Q3 8 5 20L7 48Q7 58 19 57L50 55Q59 55 58 44L56 16Q56 5 45 6Z','kifireice':'M13 5H51L59 13V51L51 59H13L5 51V13Z'}[style]
        body=f'<path d="{plate}" fill="url(#face)" stroke="url(#metal)" stroke-width="1.6"/>'
        body+=f'<g transform="translate(7 7) scale(.78)" fill="none" stroke="{light}" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round">'+symbol(kind)+'</g>'
        if style=='kifireice':body+=f'<path d="M13 54H30" stroke="{accent}"/><path d="M34 54H51" stroke="{second}"/>'
        elif style=='kiprimal':body+=f'<path d="M44 52L48 47M48 52L52 47" stroke="{second}"/>'
        else:body+=f'<circle cx="32" cy="55" r="1.4" fill="{second}"/>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><title>{escape(label+" · "+style)}</title>{defs}{body}</svg>\n'

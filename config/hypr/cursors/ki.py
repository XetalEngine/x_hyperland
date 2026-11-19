"""Distinct functional pointers and twelve-frame busy emblems for KI 1994."""
STYLES=('killerinstinct','kitemple','kiprimal','kifireice')


def arrow(style,fill,edge,accent):
    shapes={'killerinstinct':'M5 3L29 18L18 21L24 31L19 34L13 23L6 29Z','kitemple':'M5 3L7 29L14 21L20 32L24 28L18 18L29 17Z','kiprimal':'M5 3Q8 3 11 7L29 19L18 21L23 30L19 34L12 24L6 29Z','kifireice':'M5 3L29 16L19 20L24 30L19 34L13 22L6 28Z'}
    detail={'killerinstinct':f'<path d="M8 8L9 23L14 18L23 18" fill="none" stroke="{accent}" stroke-width="1.5"/><path d="M8 8L23 18" stroke="{fill}" stroke-width=".7"/>','kitemple':f'<path d="M9 11L11 21L15 17L23 17" fill="none" stroke="#c9a75b" stroke-width="1.3"/><path d="M13 13L16 16L13 19L10 16Z" fill="{accent}" stroke-width=".5"/>','kiprimal':f'<path d="M10 11L12 18M14 13L16 18M18 15L20 18" stroke="{accent}" stroke-width="1.4"/>','kifireice':f'<path d="M8 8L9 22L13 18" fill="none" stroke="{accent}" stroke-width="1.4"/><path d="M12 10L24 16L17 18L21 28" fill="none" stroke="#70ddef" stroke-width="1.4"/>'}[style]
    return '<path d="'+shapes[style]+'"/>'+detail


def busy(style,fill,edge,accent,frame):
    if style=='killerinstinct':
        body=f'<path d="M7 4H29L32 9V27L28 32H8L4 27V9Z" fill="{edge}" stroke="{fill}" stroke-width="1.4"/><path d="M9 9H27V18H9Z" fill="{accent}" fill-opacity=".35" stroke="{accent}" stroke-width=".8"/>'
        for i in range(6):body+=f'<circle cx="{11+(i%3)*7}" cy="{22+(i//3)*6}" r="2" fill="{accent if i==frame%6 else fill}" stroke="none"/>'
        return body
    if style=='kitemple':
        return f'<path d="M18 3L33 18L18 33L3 18Z" fill="{edge}" stroke="#d6b967" stroke-width="1.3"/><circle cx="18" cy="18" r="5" fill="{accent}" stroke="{fill}" stroke-width=".8"/><g transform="rotate({frame*30} 18 18)"><path d="M18 6L22 10L18 14L14 10Z" fill="#d6b967" stroke="none"/><path d="M18 22L22 26L18 30L14 26Z" fill="{accent}" stroke="none"/></g>'
    if style=='kiprimal':
        return f'<circle cx="18" cy="18" r="14" fill="{edge}" stroke="{fill}" stroke-width="1.3"/><g transform="rotate({frame*30} 18 18)"><path d="M8 23L16 9L13 22M15 25L23 11L20 24M22 27L29 16L27 26" fill="{accent}" stroke="none"/></g>'
    return f'<circle cx="18" cy="18" r="13" fill="{edge}" stroke="{fill}" stroke-width=".9"/><g transform="rotate({frame*30} 18 18)"><path d="M18 5A13 13 0 0 1 18 31" fill="none" stroke="{accent}" stroke-width="3"/><path d="M18 31A13 13 0 0 1 18 5" fill="none" stroke="#70ddef" stroke-width="3"/><path d="M18 11L22 18L18 25L14 18Z" fill="{fill}" stroke="none"/></g>'

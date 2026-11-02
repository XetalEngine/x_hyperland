"""Navigation and control shapes, independent of the desktop color palette."""
from pathlib import Path
LAYOUTS = {'classic': 'Classic tabs', 'modern': 'Modern icon rail',
           'sidebar': 'Gallery sidebar', 'ribbon': 'Studio ribbon'}
DESCRIPTIONS = {'classic': 'Compact tabs across the top · crisp controls',
    'modern': 'Minimal icon rail · soft cards and rounded buttons',
    'sidebar': 'Icons with labels · spacious sidebar and pill buttons',
    'ribbon': 'Icon toolbar across the top · precise, compact controls'}


def default(design): return 'sidebar' if design == 'tidalglass' else 'modern' if design == 'modern' else 'classic'


def widget_style(layout, design):
    if design == 'tidalglass': return design
    if layout in ('modern', 'sidebar'): return 'modern'
    if layout == 'ribbon': return 'binaryknife'
    return design if design in ('raw', 'breakpoint', 'binaryknife') else 'raw'


def stylesheet(p, layout, palette=''):
    radius = 19 if layout == 'sidebar' else 10 if layout == 'modern' else 4
    extra = f'QPushButton, QPushButton#primary, QToolButton {{border-radius:{radius}px;}}' if layout == 'sidebar' else ''
    bright=sum(int(p['HighlightedText'][i:i+2],16) for i in (1,3,5))>420
    check=Path(__file__).with_name('assets')/('check-'+palette+'.svg' if palette in ('breakpoint','binaryknife') else 'check-light.svg' if bright else 'check-dark.svg')
    shapes = extra + f'''
    QWidget#modernRail {{background:{p['AlternateBase']}; border-radius:{radius}px;}}
    QToolButton#railButton {{background:transparent; color:{p['Text']}; border:1px solid transparent;
        border-radius:{radius}px; padding:6px;}}
    QToolButton#railButton:hover {{background:{p['Mid']};}}
    QToolButton#railButton:checked {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    QFrame#presetCard {{background:{p['AlternateBase']}; border:1px solid {p['Midlight']}; border-radius:{radius}px;}}
    '''
    # Its glass surfaces already support every navigation layout.
    if palette == 'tidalglass': shapes = ''
    return shapes + f'''
    QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {{image:url("{check}");
        background:{p['Highlight']}; border:1px solid {p['Accent']}; width:16px; height:16px;}}
    '''

"""Independent selection edges for Fusion Files; the default is deliberately off."""
STYLES = {'none': 'Off', 'curve': 'Glass curve', 'line': 'Ink line'}
DEFAULT = 'none'


def validate(value):
    if not isinstance(value, str) or value not in STYLES:
        raise ValueError('Choose Off, Glass curve or Ink line for the selection marker.')
    return value


def stylesheet(colors, value=DEFAULT):
    validate(value)
    base = 'QTreeWidget#places::item {border-left:0px solid transparent;}\n'
    if value == 'none':
        return base+'QTreeWidget#places::item:selected {border-left:0px solid transparent;}\n'
    width = 3 if value == 'curve' else 2
    radius = 14 if value == 'curve' else 0
    return base+f'''QTreeWidget#places::item:selected {{
        border-left:{width}px solid {colors['Accent']};
        border-top-left-radius:{radius}px; border-bottom-left-radius:{radius}px;
    }}\n'''


def preview():
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
    tree = QTreeWidget();tree.setObjectName('places');tree.setHeaderHidden(True)
    tree.setRootIsDecorated(False);tree.setFixedHeight(82);tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    tree.setAccessibleName('Fusion Files selection marker preview')
    for title in ('Home', 'Desktop'):QTreeWidgetItem(tree, [title])
    tree.setCurrentItem(tree.topLevelItem(1))
    return tree


def style_preview(tree, value):
    import runtime
    p = runtime.colors()
    tree.setPalette(runtime.palette())
    tree.setStyleSheet(f'''QTreeWidget#places {{background:{p['Window']}; border:none; padding:2px;}}
        QTreeWidget#places::item {{height:30px; padding:2px 12px; color:{p['Text']}; border-radius:5px;}}
        QTreeWidget#places::item:selected {{background:{p['Highlight']}; color:{p['HighlightedText']};}}
    '''+stylesheet(p, value))

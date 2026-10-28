"""Global label preferences and balanced content in fixed-size Apps tiles."""
DEFAULTS = {'names': True, 'hotkeys': True}


def normalize(value, strict=False):
    if not isinstance(value, dict):
        if strict: raise ValueError('Choose whether to show shortcut names and hotkeys.')
        value = {}
    result = dict(DEFAULTS)
    for key in result:
        option = value.get(key, result[key])
        if isinstance(option, bool): result[key] = option
        elif strict: raise ValueError('Shortcut label options must be on or off.')
    return result


def positions(height, names=True, hotkeys=True, name_height=31):
    """Return icon, name and hotkey y offsets, without changing the tile grid."""
    if names and hotkeys: return 9, 51, 85
    total = 38 + (6 + name_height if names else 0) + (10 + 16 if hotkeys else 0)
    top = (height - total) / 2
    return top, top + 44 if names else None, top + 48 if hotkeys else None

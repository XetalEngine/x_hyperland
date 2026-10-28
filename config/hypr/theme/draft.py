"""Merge theme edits with concurrent changes without replacing unrelated choices."""
import copy
import runtime

FIELDS = ('design', 'mode', 'avatar', 'backdrop', 'background', 'surfaces', 'labels', 'visibility', 'launcher_style')
TITLES = {'design': 'Desktop theme', 'mode': 'Colors', 'avatar': 'Profile image',
          'backdrop': 'Show background image', 'background': 'Apps background',
          'surfaces': 'Apps tiles & groups', 'labels': 'Shortcut labels', 'visibility': 'Background visibility', 'launcher_style': 'Start menu style'}


def current():
    return (runtime.design(), runtime.mode(), runtime.state().get('avatar', 'assets/account.gif'),
            runtime.launcher_wallpaper(), runtime.launcher_background(), runtime.launcher_surfaces(),
            runtime.launcher_labels(), runtime.launcher_background_visibility(), runtime.launcher_style())


def merge(baseline, edited, saved, prefer='edited'):
    conflicts = []
    def field(old, ours, theirs, path):
        if ours == old: return copy.deepcopy(theirs)
        if theirs == old or ours == theirs: return copy.deepcopy(ours)
        if all(isinstance(value, dict) for value in (old, ours, theirs)) and old.keys() == ours.keys() == theirs.keys():
            return {key: field(old[key], ours[key], theirs[key], path + (key,)) for key in old}
        conflicts.append(' / '.join((TITLES[path[0]], *path[1:])))
        return copy.deepcopy(theirs if prefer == 'saved' else ours)
    return tuple(field(old, ours, theirs, (key,)) for key, old, ours, theirs in zip(FIELDS, baseline, edited, saved)), conflicts

"""Menu actions share the existing Applications hotkey editor and safeguards."""
import copy
from pathlib import Path
import shlex
import sys
import uuid
import menu_config

sys.path.insert(0, str(menu_config.ROOT/'control_center'))
import keys


def command(ident):
    return shlex.join(['python3', str(menu_config.ROOT/'desktop_menu/run.py'), '--item', ident]).replace('#', '##')


def item_id(binding, values):
    try:
        argv = shlex.split(keys.expand(binding.args, values).replace('##', '#'))
    except ValueError:
        return None
    if (binding.dispatcher == 'exec' and len(argv) == 4 and Path(argv[0]).name.startswith('python')
            and Path(argv[1]).expanduser() == menu_config.ROOT/'desktop_menu/run.py' and argv[2] == '--item'):
        return argv[3]
    return None


class Entry:
    def __init__(self, item): self.item = item; self.fields = {'icon': item['icon']}
    def get_display_name(self): return self.item['label']
    def get_id(self): return self.item['id']


def matches(entry, records, values):
    return [b for b in records if b.submap == 'reset' and item_id(b, values) == entry.get_id()]


def edited(records, entry, selected, mods, key, enabled=True, remove=False):
    result = copy.deepcopy(records)
    binding = next((b for b in result if b.id == selected), None)
    if selected and (binding is None or binding.protected):
        raise keys.ConfigError('That hotkey changed or is protected. Reload before editing it.')
    if remove:
        if binding: result.remove(binding)
        return result
    if binding is None:
        binding = keys.Binding(uuid.uuid4().hex, '', 'Applications', True, '', '', 'exec')
        result.append(binding)
    binding.label = entry.get_display_name(); binding.category = 'Applications'
    binding.mods = mods.strip(); binding.key = key.strip(); binding.enabled = enabled
    binding.dispatcher = 'exec'; binding.args = command(entry.get_id())
    return result


remove_message = 'This removes only the global hotkey. The desktop menu item is kept.'


def labels(store=None):
    store = store or keys.Store()
    records, _ = store.load(); values = keys.variables(store.main.read_text())
    result = {}
    for binding in records:
        ident = item_id(binding, values)
        if ident and binding.enabled and binding.submap == 'reset':
            result.setdefault(ident, []).append(binding.shortcut(values).replace('SUPER', 'Super'))
    return result


def save_menu(store, draft, expected, key_store=None):
    """Remove hotkeys for deleted items, compensating if their apply fails."""
    menu_config.validate(draft)
    previous, previous_hash = store.load()
    if previous_hash != expected:
        raise ValueError('The menu changed elsewhere. Reload before applying.')
    current_ids = {item['id'] for item, _ in menu_config.walk(draft['items']) if item['kind'] == 'action'}
    old_ids = {item['id'] for item, _ in menu_config.walk(previous['items']) if item['kind'] == 'action'}
    removed = old_ids-current_ids
    key_store = key_store or keys.Store()
    records = remaining = None
    if removed:
        records, key_hash = key_store.load()
        values = keys.variables(key_store.main.read_text())
        remaining = [b for b in records if item_id(b, values) not in removed]
    saved = store.save(draft, expected)
    if records != remaining:
        try:
            key_store.apply(remaining, key_hash)
        except Exception as error:
            try:
                store.save(previous, saved)
            except Exception as rollback:
                raise ValueError(f'Hotkeys could not be updated: {error}. Menu rollback failed: {rollback}') from error
            raise ValueError('Menu changes were rolled back: '+str(error)) from error
    return saved
